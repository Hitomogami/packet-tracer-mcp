"""
Serialised async command queue for PT IPC communication.

All commands flow through the PTBuilder HTTP bridge and wait for the
PT-side result (request-response). This queue serialises all
send_script / exec_cli calls — PT executes one command at a time.
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from .pt_connection import PTConnection, PTConnectionError, RESULT_TIMEOUT
from .script_builder import ScriptBuilder

logger = logging.getLogger(__name__)

# device.getType() ID → category label (from PTBuilder userfunctions deviceTypes)
_CATEGORY_BY_TYPE: dict[int, str] = {
    0: "router", 1: "switch", 2: "cloud", 3: "bridge", 4: "hub",
    5: "repeater", 6: "coaxialsplitter", 7: "accesspoint", 8: "pc",
    9: "server", 10: "printer", 11: "wirelessrouter", 12: "ipphone",
    13: "dslmodem", 14: "cablemodem", 15: "remotenetwork", 16: "switch",
    17: "laptop", 18: "tabletpc", 19: "pda", 20: "wirelessenddevice",
    21: "wiredenddevice", 22: "tv", 23: "homevoip", 24: "analogphone",
    26: "asa", 33: "sniffer", 34: "mcu", 35: "sbc",
}

# Syslog lines ("%LINK-5-CHANGED: ...") are informational, not command errors.
_SYSLOG_LINE = re.compile(r"^%[A-Z0-9_]+-\d", re.M)

# Substrings that mark an IOS command as rejected.
_IOS_ERROR_HINTS = (
    "% invalid", "% ambiguous", "% incomplete", "% unknown", "% error",
    "invalid input detected", "translating ", "unrecognized",
    "is not a valid", "can not be", "cannot be changed",
)


def looks_like_ios_error(text: str) -> bool:
    """
    Heuristically decide whether an IOS command output signals rejection.

    Distinguishes real IOS errors ("% Invalid input detected") from syslog
    notices ("%SYS-5-CONFIG_I: ...") that merely start with '%'.
    """
    if not text:
        return False
    low = text.lower()
    if any(hint in low for hint in _IOS_ERROR_HINTS):
        return True
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("%") and not _SYSLOG_LINE.match(stripped):
            return True
    return False


def _annotate_config_results(result: "CommandResult") -> "CommandResult":
    """
    Add a per-command `failed`/`error` verdict to configure_device output.

    The JS payload returns [{cmd, first, out}, ...]; this flags rows whose
    output looks like an IOS rejection so tools can report per-command
    success instead of a blanket fake success.
    """
    if not (result.success and isinstance(result.data, dict)):
        return result
    rows = result.data.get("results")
    if not isinstance(rows, list):
        return result
    annotated: list[Any] = []
    for row in rows:
        if not isinstance(row, dict):
            annotated.append(row)
            continue
        out = str(row.get("out") or "")
        failed = looks_like_ios_error(out)
        entry = dict(row)
        entry["failed"] = failed
        if failed:
            first_line = out.strip().splitlines()[0] if out.strip() else "IOS rejected the command (no output)"
            entry["error"] = first_line[:160]
        annotated.append(entry)
    result.data["results"] = annotated
    return result


@dataclass
class CommandResult:
    success: bool
    output: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    error: str = ""


class CommandQueue:
    """
    Wraps PTConnection with a serialisation lock and higher-level helpers.

    All public methods are safe to call from concurrent async tasks.
    """

    def __init__(self, connection: PTConnection) -> None:
        self._conn = connection
        self._builder = ScriptBuilder()
        self._lock = asyncio.Lock()

    @property
    def connected(self) -> bool:
        return self._conn.connected

    async def add_device(
        self, name: str, device_type: str, x: int = 100, y: int = 100
    ) -> CommandResult:
        js = self._builder.add_device(name, device_type, x, y)
        return await self._exec(js, f"add device '{name}'")

    async def remove_device(self, name: str) -> CommandResult:
        js = self._builder.remove_device(name)
        return await self._exec(js, f"remove device '{name}'")

    async def add_link(
        self,
        device1: str,
        port1: str,
        device2: str,
        port2: str,
        cable_key: str = "auto",
        src_category: str = "",
        dst_category: str = "",
    ) -> CommandResult:
        cable_type = ScriptBuilder.resolve_cable_type(cable_key, src_category, dst_category)
        js = self._builder.add_link(device1, port1, device2, port2, cable_type)
        return await self._exec(js, f"connect {device1}:{port1} to {device2}:{port2}")

    async def remove_link(self, device: str, port: str) -> CommandResult:
        js = self._builder.remove_link(device, port)
        return await self._exec(js, f"disconnect {device}:{port}")

    async def configure_pc_ip(
        self, name: str, ip: str, mask: str, gateway: str, dns: str = "", dhcp: bool = False
    ) -> CommandResult:
        js = self._builder.configure_pc_ip(name, ip, mask, gateway, dns, dhcp)
        return await self._exec(js, f"configure PC IP '{name}'")

    async def configure_device(self, name: str, commands: list[str]) -> CommandResult:
        js = self._builder.configure_device(name, commands)
        result = await self._exec(js, f"configure '{name}'")
        return _annotate_config_results(result)

    async def exec_cli(
        self, name: str, commands: list[str], timeout: float = RESULT_TIMEOUT
    ) -> CommandResult:
        """Run CLI commands and capture their console output (read path)."""
        js = self._builder.exec_cli(name, commands)
        return await self._exec(js, f"exec CLI on '{name}'", timeout=timeout)

    # A PT ping/traceroute completes asynchronously (its text reaches a
    # console buffer only after the last reply/timeout), so the read happens
    # in a second request after this delay. Live-measured: a LAN ping's
    # transcript was not yet in the buffer at +8s and fully present by ~+30s.
    PING_SETTLE_SECONDS = 15.0

    async def async_cli(
        self, name: str, command: str, fallback_cmd: str = "", settle: float = 0.0,
    ) -> CommandResult:
        """Two-phase async CLI: start the command, settle, collect its output.

        PC-PT sources return the full transcript from the Command-Prompt
        buffer; IOS sources return fallback_cmd's synchronous output when
        given (e.g. the post-ping ARP table), because this PT build does not
        expose async console text for switches/routers — §八.
        A settle of 0 (tests) skips the wait entirely.
        """
        start = await self._exec(
            self._builder.async_start(name, command), f"async start on '{name}': {command}"
        )
        if not start.success:
            return start
        if settle:
            await asyncio.sleep(settle)
        return await self._exec(
            self._builder.async_collect(name, command, fallback_cmd),
            f"async collect on '{name}': {command}",
        )

    async def ping(self, name: str, destination: str) -> CommandResult:
        """Two-phase ping; on IOS the post-ping ARP table backs the result."""
        return await self.async_cli(
            name, f"ping {destination}", fallback_cmd="show ip arp",
            settle=self.PING_SETTLE_SECONDS,
        )

    async def get_topology(self) -> dict[str, Any]:
        """Read the live topology from PT (devices, links, per-port state)."""
        result = await self._exec(self._builder.get_topology(), "read topology")
        if not result.success:
            return {
                "state": "disconnected",
                "devices": [],
                "links": [],
                "error": result.error,
            }

        data = result.data if isinstance(result.data, dict) else {}
        devices = data.get("devices") or []
        links = data.get("links") or []

        for dev in devices:
            dev["category"] = _CATEGORY_BY_TYPE.get(dev.get("categoryId"), "")

        return {"state": "connected", "devices": devices, "links": links}

    async def apply_topology(self, devices: list[dict], connections: list[dict]) -> CommandResult:
        js = self._builder.build_topology(devices, connections)
        return await self._exec(js, "apply topology")

    async def clear_topology(self) -> CommandResult:
        js = self._builder.clear_topology()
        return await self._exec(js, "clear topology")

    async def save_config(self, device_name: str) -> CommandResult:
        js = self._builder.save_device_config(device_name)
        result = await self._exec(js, f"save config '{device_name}'")
        return _annotate_config_results(result)

    async def save_file_as(self, path: str) -> CommandResult:
        """Save the whole live PT state to a .pkt path (true File→Save As)."""
        js = self._builder.save_file_as(path)
        return await self._exec(js, f"save file as '{path}'")

    async def get_active_file(self) -> CommandResult:
        """Read the .pkt path PT currently has open (may lag after save-as)."""
        js = self._builder.get_active_file()
        return await self._exec(js, "get active file")

    # ------------------------------------------------------------------ #
    # Internal                                                             #
    # ------------------------------------------------------------------ #

    async def _exec(
        self, js: str, description: str, timeout: float = RESULT_TIMEOUT
    ) -> CommandResult:
        async with self._lock:
            if not self._conn.connected:
                logger.info("PT not connected; attempting reconnect")
                reconnected = await self._conn.reconnect()
                if not reconnected:
                    return CommandResult(
                        success=False,
                        error=(
                            "PTBuilder is not polling. "
                            "Make sure Packet Tracer is open with the MCP bridge PTBuilder module installed."
                        ),
                    )
            try:
                logger.debug("Executing: %s\n%s", description, js)
                result = await self._conn.send_script(js, timeout=timeout)
                output = result.get("output", "") or ""
                data = result.get("data")
                # exec_cli reports its captured console text inside data.output
                if isinstance(data, dict) and data.get("output"):
                    output = str(data["output"])
                return CommandResult(success=True, output=output, data=data)
            except PTConnectionError as exc:
                logger.error("Script failed (%s): %s", description, exc)
                return CommandResult(success=False, error=str(exc))
            except Exception as exc:
                logger.exception("Unexpected error: %s", description)
                return CommandResult(success=False, error=f"Unexpected error: {exc}")
