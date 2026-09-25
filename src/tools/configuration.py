"""
MCP tools for configuring devices via CLI commands.
"""

import logging
from typing import Annotated

from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession
from pydantic import Field

from ..app import AppContext, mcp
from ..bridge.script_builder import ScriptBuilder

logger = logging.getLogger(__name__)


def _format_config_rows(rows: list) -> tuple[list[str], list[str]]:
    """
    Render per-command results as display lines.

    Returns (lines, failed_lines): every executed command gets one line;
    rejected commands get an extra ✗ line carrying the IOS error text.
    """
    lines: list[str] = []
    failed: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        cmd = str(row.get("cmd") or "?")
        out = str(row.get("out") or "").strip()
        if row.get("failed"):
            err = str(row.get("error") or out or "rejected by IOS")
            failed.append(f"  ✗ {cmd}  →  {err}")
            if out and out.splitlines()[0] != err:
                failed.append(f"      {out.splitlines()[0]}")
        else:
            line = f"  ✓ {cmd}"
            if out:
                line += f"  →  {out.splitlines()[0][:150]}"
            lines.append(line)
    return lines, failed


@mcp.tool()
async def pt_send_commands(
    device_name: Annotated[str, Field(description="Target device name (e.g. 'R1', 'Switch1')")],
    commands: Annotated[
        list[str],
        Field(
            description=(
                "List of CLI commands to execute in order. "
                "Include mode-change commands if needed, e.g.: "
                "['enable', 'configure terminal', 'interface Gi0/0', 'ip address 192.168.1.1 255.255.255.0', 'no shutdown']"
            )
        ),
    ],
    ctx: Context[ServerSession, AppContext] = None,
) -> str:
    """
    Send a sequence of CLI commands to a device in Packet Tracer.

    Commands are sent in order and each one's result is confirmed by PT —
    the response lists every command with ✓/✗ plus any IOS error text.
    Mode-navigation commands (enable, conf t, end, exit) are handled by the
    bridge itself: the device is placed in global-config mode first, so you
    can pass configuration commands directly. Configs are NOT saved to
    NVRAM automatically — call pt_save_config afterwards.

    Common command sequences:
    - Interface IP: ['interface Gi0/0', 'ip address X.X.X.X M.M.M.M', 'no shutdown']
    - Hostname: ['hostname R1']
    - OSPF: ['router ospf 1', 'network X.X.X.X 0.0.0.X area 0']
    - VLAN: ['vlan 10', 'name Sales']
    """
    queue = ctx.request_context.lifespan_context.queue
    result = await queue.configure_device(device_name, commands)

    if not result.success:
        return f"✗ Failed to configure {device_name}: {result.error}"

    rows = result.data.get("results") if isinstance(result.data, dict) else None
    if not isinstance(rows, list):
        # Older bridge without per-command results — keep the legacy wording.
        output_lines = [f"✓ Commands executed on {device_name} (confirmed by PT):"]
        for cmd in commands:
            output_lines.append(f"  {cmd}")
        if result.output:
            output_lines.append(f"\nOutput:\n{result.output}")
        return "\n".join(output_lines)

    ok_lines, failed_lines = _format_config_rows(rows)
    skipped = [
        c.strip() for c in commands
        if c.strip().lower() in ScriptBuilder.CONFIG_SKIP_COMMANDS
    ]
    header = (
        f"⚠ {device_name}: {len(failed_lines)} of {len(rows)} commands rejected by IOS"
        if failed_lines
        else f"✓ Sent {len(rows)} command(s) to {device_name} — every command confirmed by PT:"
    )
    lines = [header, *ok_lines, *failed_lines]
    if skipped:
        lines.append(f"(skipped mode-navigation commands: {', '.join(skipped)})")
    return "\n".join(lines)


@mcp.tool()
async def pt_get_running_config(
    device_name: Annotated[str, Field(description="Device name to query")],
    ctx: Context[ServerSession, AppContext] = None,
) -> str:
    """
    Retrieve the running configuration of a device.

    Executes 'show running-config' on the device and returns the output.
    """
    queue = ctx.request_context.lifespan_context.queue
    result = await queue.exec_cli(device_name, ["show running-config"], timeout=30.0)

    if result.success:
        output = result.output.strip()
        if output:
            return f"Running config for {device_name}:\n\n{output}"
        return (
            f"Running config for {device_name}:\n\n"
            "(command executed in PT, but this PT build does not return console "
            "text — check the CLI inside Packet Tracer)"
        )
    return f"✗ Failed to get config for {device_name}: {result.error}"


@mcp.tool()
async def pt_save_config(
    device_name: Annotated[str, Field(description="Device name to save")],
    ctx: Context[ServerSession, AppContext] = None,
) -> str:
    """
    Save the running configuration to startup-config on a device.

    Equivalent to 'copy running-config startup-config'.

    NOTE: this writes device NVRAM only. Device configs still vanish if
    Packet Tracer closes without saving the .pkt — after finishing an
    experiment, also do File→Save in the PT GUI (configs in NVRAM are
    included when the .pkt is saved).
    """
    queue = ctx.request_context.lifespan_context.queue
    result = await queue.save_config(device_name)

    if result.success:
        rows = result.data.get("results") if isinstance(result.data, dict) else None
        if isinstance(rows, list) and rows and rows[0].get("failed"):
            out = str(rows[0].get("out") or "").strip()
            return f"✗ Save may have failed on {device_name}: {out or rows[0].get('error', 'no output')}"
        detail = ""
        if isinstance(rows, list) and rows:
            out = str(rows[0].get("out") or "").strip()
            if out:
                detail = f" ({out.splitlines()[0]})"
        return (
            f"✓ Configuration saved on {device_name}{detail}\n"
            "(NVRAM written. To persist across a PT restart, also save the "
            ".pkt file in the Packet Tracer GUI: File→Save)"
        )
    return f"✗ Failed to save config on {device_name}: {result.error}"


@mcp.tool()
async def pt_configure_pc(
    device_name: Annotated[str, Field(description="PC, Laptop or Server name (e.g. 'PC1', 'SRV-DNS')")],
    ip_address: Annotated[str, Field(description="Static IP address (e.g. '192.168.1.50')")] = "",
    subnet_mask: Annotated[str, Field(description="Subnet mask (e.g. '255.255.255.0')")] = "255.255.255.0",
    gateway: Annotated[str, Field(description="Default gateway (e.g. '192.168.1.1')")] = "",
    dns_server: Annotated[str, Field(description="DNS server IP (e.g. '192.168.1.10')")] = "",
    dhcp: Annotated[bool, Field(default=False, description="Use DHCP instead of static")] = False,
    ctx: Context[ServerSession, AppContext] = None,
) -> str:
    """
    Configure IP settings on a PC, Laptop or Server in Packet Tracer.
    Uses PTBuilder's configurePcIp() — works on PC-PT, Laptop-PT, Server-PT.
    """
    queue = ctx.request_context.lifespan_context.queue
    result = await queue.configure_pc_ip(device_name, ip_address, subnet_mask, gateway, dns_server, dhcp)
    if result.success:
        if dhcp:
            return f"✓ {device_name} configured for DHCP"
        return f"✓ {device_name}: {ip_address}/{subnet_mask} gw={gateway} dns={dns_server}"
    return f"✗ Failed to configure {device_name}: {result.error}"


@mcp.tool()
async def pt_configure_ip(
    device_name: Annotated[str, Field(description="Router or switch name")],
    interface: Annotated[str, Field(description="Interface name (e.g. 'GigabitEthernet0/0', 'Gi0/0')")],
    ip_address: Annotated[str, Field(description="IP address (e.g. '192.168.1.1')")],
    subnet_mask: Annotated[str, Field(description="Subnet mask (e.g. '255.255.255.0')")],
    no_shutdown: Annotated[bool, Field(default=True, description="Bring the interface up")] = True,
    ctx: Context[ServerSession, AppContext] = None,
) -> str:
    """
    Configure an IP address on a router or switch interface.

    Convenience shortcut — equivalent to manually sending the CLI commands:
    enable → configure terminal → interface X → ip address X M → no shutdown
    """
    commands = [
        "enable",
        "configure terminal",
        f"interface {interface}",
        f"ip address {ip_address} {subnet_mask}",
    ]
    if no_shutdown:
        commands.append("no shutdown")
    commands.append("end")

    queue = ctx.request_context.lifespan_context.queue
    result = await queue.configure_device(device_name, commands)

    if not result.success:
        return f"✗ Failed to configure {device_name} {interface}: {result.error}"

    rows = result.data.get("results") if isinstance(result.data, dict) else None
    if isinstance(rows, list):
        _, failed_lines = _format_config_rows(rows)
        if failed_lines:
            return (
                f"✗ {device_name} {interface}: IOS rejected part of the configuration\n"
                + "\n".join(failed_lines)
            )
    return (
        f"✓ Configured {device_name} {interface}: "
        f"{ip_address}/{subnet_mask}"
        + (" (up)" if no_shutdown else "")
    )
