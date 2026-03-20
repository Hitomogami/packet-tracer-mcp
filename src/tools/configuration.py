"""
MCP tools for configuring devices via CLI commands.
"""

import logging
from typing import Annotated

from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession
from pydantic import Field

from ..app import AppContext, mcp

logger = logging.getLogger(__name__)


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

    Commands are sent in order. Include navigation commands (enable,
    configure terminal, exit) as needed. The device must be placed in
    the topology before configuring it.

    Common command sequences:
    - Interface IP: ['en', 'conf t', 'int Gi0/0', 'ip address X.X.X.X M.M.M.M', 'no shut']
    - Hostname: ['en', 'conf t', 'hostname R1']
    - OSPF: ['en', 'conf t', 'router ospf 1', 'network X.X.X.X 0.0.0.X area 0']
    - VLAN: ['en', 'conf t', 'vlan 10', 'name Sales', 'exit']
    """
    queue = ctx.request_context.lifespan_context.queue
    result = await queue.configure_device(device_name, commands)

    if result.success:
        output_lines = [f"✓ Commands sent to {device_name}:"]
        for cmd in commands:
            output_lines.append(f"  {cmd}")
        if result.output:
            output_lines.append(f"\nOutput:\n{result.output}")
        return "\n".join(output_lines)

    return f"✗ Failed to configure {device_name}: {result.error}"


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
    result = await queue.configure_device(device_name, ["show running-config"])

    if result.success:
        output = result.output or "(no output returned — PT may need more time)"
        return f"Running config for {device_name}:\n\n{output}"
    return f"✗ Failed to get config for {device_name}: {result.error}"


@mcp.tool()
async def pt_save_config(
    device_name: Annotated[str, Field(description="Device name to save")],
    ctx: Context[ServerSession, AppContext] = None,
) -> str:
    """
    Save the running configuration to startup-config on a device.

    Equivalent to 'copy running-config startup-config'.
    """
    queue = ctx.request_context.lifespan_context.queue
    result = await queue.save_config(device_name)

    if result.success:
        return f"✓ Configuration saved on {device_name}"
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

    if result.success:
        return (
            f"✓ Configured {device_name} {interface}: "
            f"{ip_address}/{subnet_mask}"
            + (" (up)" if no_shutdown else "")
        )
    return f"✗ Failed to configure {device_name} {interface}: {result.error}"
