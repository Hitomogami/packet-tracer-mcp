"""
MCP tools for device management in Packet Tracer.
"""

import json
import logging
from pathlib import Path
from typing import Annotated

from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession
from pydantic import Field

from ..app import AppContext, mcp
from ..models import Device, DeviceCategory

logger = logging.getLogger(__name__)

_CATALOG_PATH = Path(__file__).parent.parent / "catalog" / "devices.json"
_catalog: dict | None = None


def _load_catalog() -> dict:
    global _catalog
    if _catalog is None:
        _catalog = json.loads(_catalog_path().read_text(encoding="utf-8"))
    return _catalog


def _catalog_path() -> Path:
    return _CATALOG_PATH


def _resolve_device_type(device_type: str) -> tuple[str, str]:
    """
    Resolve an alias (e.g. 'router') or category name to a PT type string
    and category.  Returns (pt_type, category).
    """
    catalog = _load_catalog()
    dt = device_type.lower()

    # Direct alias lookup — resolve once, no recursion to avoid alias→alias loops
    if dt in catalog.get("aliases", {}):
        resolved = catalog["aliases"][dt]
        dt = resolved.lower()  # use resolved value for catalog search below

    # Search all categories
    for category, devices in catalog.items():
        if category in ("aliases",):
            continue
        if isinstance(devices, dict):
            # Check by key (e.g. "2911")
            if dt in devices:
                return devices[dt]["pt_type"], devices[dt]["category"]
            # Check by pt_type value
            for key, info in devices.items():
                if isinstance(info, dict) and info.get("pt_type", "").lower() == dt:
                    return info["pt_type"], info["category"]

    # Fallback: return as-is and guess category
    category = "end_device"
    if any(r in device_type.lower() for r in ("router", "29", "18", "19", "43")):
        category = "router"
    elif any(s in device_type.lower() for s in ("switch", "29", "35", "37")):
        category = "switch"
    return device_type, category


def _get_default_ports(device_type: str) -> list[str]:
    catalog = _load_catalog()
    for category, devices in catalog.items():
        if not isinstance(devices, dict):
            continue
        for key, info in devices.items():
            if not isinstance(info, dict):
                continue
            if info.get("pt_type", "").lower() == device_type.lower() or key.lower() == device_type.lower():
                return info.get("ports", [])
    return []


@mcp.tool()
async def pt_add_device(
    name: Annotated[str, Field(description="Unique device name in the topology (e.g. 'R1', 'Switch1', 'PC-Sales')")],
    device_type: Annotated[str, Field(description="Device type: use aliases like 'router', 'switch', 'pc', 'server', or specific models like '2911', '2960', '1941'")],
    x: Annotated[int, Field(default=100, description="Canvas X position (pixels)")] = 100,
    y: Annotated[int, Field(default=100, description="Canvas Y position (pixels)")] = 100,
    ctx: Context[ServerSession, AppContext] = None,
) -> str:
    """
    Add a networking device to the Packet Tracer canvas.

    Supports device aliases: 'router' → Cisco 2911, 'switch' → Cisco 2960-24TT,
    'pc' → PC-PT, 'server' → Server-PT, 'laptop' → Laptop-PT.
    You can also specify exact PT models: '2811', '1941', '4331', '3560', etc.
    """
    queue = ctx.request_context.lifespan_context.queue
    pt_type, category = _resolve_device_type(device_type)

    result = await queue.add_device(name, pt_type, x, y)
    if result.success:
        return f"✓ Added {name} ({pt_type}) at position ({x}, {y})"
    return f"✗ Failed to add {name}: {result.error}"


@mcp.tool()
async def pt_remove_device(
    name: Annotated[str, Field(description="Name of the device to remove")],
    ctx: Context[ServerSession, AppContext] = None,
) -> str:
    """Remove a device and all its connections from the Packet Tracer topology."""
    queue = ctx.request_context.lifespan_context.queue
    result = await queue.remove_device(name)
    if result.success:
        return f"✓ Removed device '{name}'"
    return f"✗ Failed to remove '{name}': {result.error}"


@mcp.tool()
async def pt_list_devices(
    ctx: Context[ServerSession, AppContext] = None,
) -> str:
    """List all devices currently placed in the Packet Tracer topology."""
    queue = ctx.request_context.lifespan_context.queue
    topology = await queue.get_topology()

    devices = topology.get("devices", [])
    if not devices:
        return "No devices found in topology (or Packet Tracer is disconnected)."

    lines = [f"Devices in topology ({len(devices)} total):"]
    for dev in devices:
        name = dev.get("name", "?")
        dtype = dev.get("type", "?")
        x = dev.get("x", 0)
        y = dev.get("y", 0)
        lines.append(f"  • {name} [{dtype}] @ ({x}, {y})")

    return "\n".join(lines)


@mcp.tool()
async def pt_get_device_info(
    name: Annotated[str, Field(description="Device name to query")],
    ctx: Context[ServerSession, AppContext] = None,
) -> str:
    """
    Get detailed information about a specific device in the topology.

    Reads the live topology from PT (ports, connection, IP and MAC state).
    Also the recommended spot-check for cross-session health: verify a known
    completion marker (e.g. an SVI IP, a PC's configured address or an
    interface MAC) before trusting that prior-session configuration
    survived — reopening a .pkt restores an old snapshot.
    """
    queue = ctx.request_context.lifespan_context.queue
    topology = await queue.get_topology()

    devices = topology.get("devices", [])
    device = next((d for d in devices if d.get("name") == name), None)

    if device is None:
        known = [d.get("name", "?") for d in devices]
        known_str = ", ".join(known) if known else "none"
        return f"Device '{name}' not found. Known devices: {known_str}"

    lines = [
        f"Device: {device.get('name')}",
        f"  Type:     {device.get('type', 'unknown')}",
        f"  Position: ({device.get('x', 0)}, {device.get('y', 0)})",
    ]

    ports = device.get("ports", [])
    if ports:
        lines.append(f"  Ports ({len(ports)}):")
        for port in ports:
            connected = port.get("connected", False)
            status = "connected" if connected else "free"
            ip = port.get("ip", "")
            mac = port.get("mac", "")
            ip_str = f", ip={ip}" if ip else ""
            mac_str = f", mac={mac}" if mac else ""
            lines.append(f"    - {port.get('name', port)}: {status}{ip_str}{mac_str}")

    return "\n".join(lines)
