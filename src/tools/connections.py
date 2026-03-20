"""
MCP tools for managing cable connections between devices.
"""

import logging
from typing import Annotated, Literal

from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession
from pydantic import Field

from ..app import AppContext, mcp

logger = logging.getLogger(__name__)

CableTypeStr = Literal["auto", "straight", "crossover", "serial_dce", "serial_dte", "console", "fiber", "usb"]


@mcp.tool()
async def pt_connect(
    device1: Annotated[str, Field(description="Name of the first device (e.g. 'R1')")],
    port1: Annotated[str, Field(description="Port on the first device (e.g. 'GigabitEthernet0/0', 'Fa0/1')")],
    device2: Annotated[str, Field(description="Name of the second device (e.g. 'S1')")],
    port2: Annotated[str, Field(description="Port on the second device (e.g. 'GigabitEthernet0/1', 'Fa0/1')")],
    cable_type: Annotated[
        CableTypeStr,
        Field(
            default="auto",
            description=(
                "Cable type: 'auto' (detect from device types), 'straight' (PC↔switch, router↔switch), "
                "'crossover' (switch↔switch, router↔router), 'serial_dce' (WAN serial link), "
                "'console', 'fiber', 'usb'"
            ),
        ),
    ] = "auto",
    ctx: Context[ServerSession, AppContext] = None,
) -> str:
    """
    Connect two devices in Packet Tracer with a cable.

    Port name formats accepted:
    - Full: 'GigabitEthernet0/0', 'FastEthernet0/1', 'Serial0/0/0'
    - Short: 'Gi0/0', 'Fa0/1', 'Se0/0/0'

    Cable is auto-selected based on device types when cable_type='auto':
    - Same device type (switch-switch, router-router) → crossover
    - Different types → straight
    - Serial ports → serial_dce
    """
    queue = ctx.request_context.lifespan_context.queue

    # Look up categories from topology for auto-cable selection
    src_cat, dst_cat = await _get_categories(queue, device1, device2)

    result = await queue.add_link(
        device1, port1, device2, port2,
        cable_key=cable_type,
        src_category=src_cat,
        dst_category=dst_cat,
    )
    if result.success:
        cable_display = cable_type if cable_type != "auto" else f"auto→{_auto_label(src_cat, dst_cat, port1, port2)}"
        return f"✓ Connected {device1}:{port1} ↔ {device2}:{port2} [{cable_display}]"
    return f"✗ Failed to connect {device1}:{port1} ↔ {device2}:{port2}: {result.error}"


@mcp.tool()
async def pt_disconnect(
    device: Annotated[str, Field(description="Device name")],
    port: Annotated[str, Field(description="Port to disconnect (e.g. 'GigabitEthernet0/0')")],
    ctx: Context[ServerSession, AppContext] = None,
) -> str:
    """Disconnect the cable from a specific port on a device."""
    queue = ctx.request_context.lifespan_context.queue
    result = await queue.remove_link(device, port)
    if result.success:
        return f"✓ Disconnected {device}:{port}"
    return f"✗ Failed to disconnect {device}:{port}: {result.error}"


@mcp.tool()
async def pt_list_connections(
    ctx: Context[ServerSession, AppContext] = None,
) -> str:
    """List all cable connections in the current topology."""
    queue = ctx.request_context.lifespan_context.queue
    topology = await queue.get_topology()

    links = topology.get("links", [])
    if not links:
        return "No connections found (or Packet Tracer is disconnected)."

    lines = [f"Connections in topology ({len(links)} total):"]
    for link in links:
        dev1 = link.get("device1", "?")
        port1 = link.get("port1", "?")
        dev2 = link.get("device2", "?")
        port2 = link.get("port2", "?")
        cable = link.get("cable", "?")
        lines.append(f"  • {dev1}:{port1} ↔ {dev2}:{port2} [{cable}]")

    return "\n".join(lines)


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #

async def _get_categories(queue, device1: str, device2: str) -> tuple[str, str]:
    """Look up device categories from the live topology."""
    topology = await queue.get_topology()
    devices = {d.get("name"): d.get("category", "") for d in topology.get("devices", [])}
    return devices.get(device1, ""), devices.get(device2, "")


def _auto_label(src_cat: str, dst_cat: str, port1: str, port2: str) -> str:
    if "serial" in port1.lower() or "serial" in port2.lower():
        return "serial_dce"
    if src_cat == dst_cat and src_cat in ("router", "switch"):
        return "crossover"
    return "straight"
