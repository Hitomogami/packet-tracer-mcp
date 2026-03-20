"""
Serialised async command queue for PT IPC communication.

PT's IPC socket is not multiplexed — concurrent writes would corrupt the
framing. This queue serialises all send_command / send_script calls.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from .pt_connection import PTConnection, PTConnectionError
from .script_builder import ScriptBuilder

logger = logging.getLogger(__name__)


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
        return await self._exec(js, f"configure '{name}'")

    async def get_topology(self) -> dict[str, Any]:
        try:
            return await self._conn.get_topology_state()
        except PTConnectionError as exc:
            logger.warning("get_topology failed: %s", exc)
            return {"state": "disconnected", "devices": [], "links": []}

    async def apply_topology(self, devices: list[dict], connections: list[dict]) -> CommandResult:
        js = self._builder.build_topology(devices, connections)
        return await self._exec(js, "apply topology")

    async def clear_topology(self) -> CommandResult:
        js = self._builder.clear_topology()
        return await self._exec(js, "clear topology")

    async def save_config(self, device_name: str) -> CommandResult:
        js = self._builder.save_device_config(device_name)
        return await self._exec(js, f"save config '{device_name}'")

    # ------------------------------------------------------------------ #
    # Internal                                                             #
    # ------------------------------------------------------------------ #

    async def _exec(self, js: str, description: str) -> CommandResult:
        async with self._lock:
            if not self._conn.connected:
                logger.info("PT not connected; attempting reconnect")
                reconnected = await self._conn.reconnect()
                if not reconnected:
                    return CommandResult(
                        success=False,
                        error=(
                            "PTBuilder is not polling. "
                            "Paste the bootstrap script in Builder Code Editor and click Run."
                        ),
                    )
            try:
                logger.debug("Executing: %s\n%s", description, js)
                result = await self._conn.send_script(js)
                return CommandResult(success=True, output=result.get("output", ""), data=result)
            except PTConnectionError as exc:
                logger.error("Script failed (%s): %s", description, exc)
                return CommandResult(success=False, error=str(exc))
            except Exception as exc:
                logger.exception("Unexpected error: %s", description)
                return CommandResult(success=False, error=f"Unexpected error: {exc}")
