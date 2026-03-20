"""
MCP tools for topology-level operations: templates, clear, validate, diagnostics.
"""

import json
import logging
from pathlib import Path
from typing import Annotated

from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession
from pydantic import Field

from ..app import AppContext, mcp

logger = logging.getLogger(__name__)

_TEMPLATES_PATH = Path(__file__).parent.parent / "catalog" / "templates.json"


def _load_templates() -> dict:
    return json.loads(_TEMPLATES_PATH.read_text(encoding="utf-8")).get("templates", {})


@mcp.tool()
async def pt_clear_topology(
    confirm: Annotated[bool, Field(description="Must be True to confirm clearing all devices and links")] = False,
    ctx: Context[ServerSession, AppContext] = None,
) -> str:
    """
    Remove all devices and connections from the Packet Tracer canvas.

    DESTRUCTIVE — set confirm=True to proceed.
    """
    if not confirm:
        return (
            "⚠ This will delete ALL devices and connections. "
            "Call again with confirm=True to proceed."
        )

    queue = ctx.request_context.lifespan_context.queue
    result = await queue.clear_topology()
    if result.success:
        return "✓ Topology cleared"
    return f"✗ Failed to clear topology: {result.error}"


@mcp.tool()
async def pt_list_templates(
    ctx: Context[ServerSession, AppContext] = None,
) -> str:
    """List all available topology templates that can be applied with pt_apply_template."""
    templates = _load_templates()
    if not templates:
        return "No templates found."

    lines = [f"Available templates ({len(templates)}):"]
    for key, tpl in templates.items():
        lines.append(f"\n  {key}")
        lines.append(f"    Name: {tpl.get('name', key)}")
        lines.append(f"    Desc: {tpl.get('description', '')}")
        params = tpl.get("params", {})
        if params:
            lines.append(f"    Params: {', '.join(params.keys())}")
    return "\n".join(lines)


@mcp.tool()
async def pt_apply_template(
    template_name: Annotated[str, Field(
        description="Template key to apply (e.g. 'simple_lan', 'wan_two_sites', 'triangle_routers', 'dmz_network')"
    )],
    params: Annotated[
        dict | None,
        Field(
            description=(
                "Template parameters as JSON object. "
                "Use pt_list_templates to see available params per template. "
                "Example: {\"num_pcs\": 4, \"network\": \"10.0.0.0/24\"}"
            ),
        ),
    ] = None,
    clear_first: Annotated[bool, Field(default=False, description="Clear existing topology before applying")] = False,
    ctx: Context[ServerSession, AppContext] = None,
) -> str:
    """
    Apply a predefined network topology template to Packet Tracer.

    Templates instantly create a complete topology with devices and cables.
    Available templates: simple_lan, wan_two_sites, triangle_routers, dmz_network.
    """
    if params is None:
        params = {}

    templates = _load_templates()
    if template_name not in templates:
        available = ", ".join(templates.keys())
        return f"✗ Template '{template_name}' not found. Available: {available}"

    template = templates[template_name]
    queue = ctx.request_context.lifespan_context.queue

    # Merge template defaults with user-provided params
    merged_params: dict = {}
    for key, spec in template.get("params", {}).items():
        if isinstance(spec, dict) and "default" in spec:
            merged_params[key] = spec["default"]
    merged_params.update(params or {})

    if clear_first:
        await queue.clear_topology()

    # Resolve template variables in device names
    resolved_devices = []
    for dev in template.get("devices", []):
        resolved = {
            "name": _resolve_param(dev["name"], merged_params),
            "type": dev["type"],
            "x": dev.get("x", 100),
            "y": dev.get("y", 100),
        }
        resolved_devices.append(resolved)

    # Resolve template variables in connections
    resolved_connections = []
    for conn in template.get("connections", []):
        resolved = {
            "from_device": _resolve_param(conn["from_device"], merged_params),
            "from_port": conn["from_port"],
            "to_device": _resolve_param(conn["to_device"], merged_params),
            "to_port": conn["to_port"],
            "cable": conn.get("cable", "straight"),
        }
        resolved_connections.append(resolved)

    # Handle dynamic PCs in simple_lan template
    if template_name == "simple_lan":
        num_pcs = int(merged_params.get("num_pcs", 3))
        switch_name = merged_params.get("switch_name", "S1")
        for i in range(1, num_pcs + 1):
            pc_name = f"PC{i}"
            resolved_devices.append({
                "name": pc_name,
                "type": "PC-PT",
                "x": 100 + (i - 1) * 150,
                "y": 400,
            })
            resolved_connections.append({
                "from_device": pc_name,
                "from_port": "FastEthernet0",
                "to_device": switch_name,
                "to_port": f"FastEthernet0/{i}",
                "cable": "straight",
            })

    result = await queue.apply_topology(resolved_devices, resolved_connections)

    if result.success:
        device_names = [d["name"] for d in resolved_devices]
        return (
            f"✓ Applied template '{template_name}' — "
            f"{len(resolved_devices)} devices, {len(resolved_connections)} connections\n"
            f"Devices: {', '.join(device_names)}"
        )
    return f"✗ Failed to apply template '{template_name}': {result.error}"


@mcp.tool()
async def pt_export_topology(
    ctx: Context[ServerSession, AppContext] = None,
) -> str:
    """
    Export the current topology as a JSON description.

    Returns device names, types, positions, and all connections.
    """
    queue = ctx.request_context.lifespan_context.queue
    topology = await queue.get_topology()

    if topology.get("state") == "disconnected":
        return "Cannot export: Packet Tracer is not connected."

    devices = topology.get("devices", [])
    links = topology.get("links", [])

    export = {
        "devices": devices,
        "connections": links,
        "summary": {
            "device_count": len(devices),
            "connection_count": len(links),
        },
    }
    return json.dumps(export, indent=2)


@mcp.tool()
async def pt_validate(
    ctx: Context[ServerSession, AppContext] = None,
) -> str:
    """
    Validate the current topology configuration.

    Checks for common issues:
    - Devices with no connections
    - Duplicate device names
    - Disconnected network segments
    """
    queue = ctx.request_context.lifespan_context.queue
    topology = await queue.get_topology()

    devices = topology.get("devices", [])
    links = topology.get("links", [])

    if not devices:
        return "⚠ Topology is empty — no devices found."

    issues: list[str] = []
    warnings: list[str] = []

    # Check for duplicate names
    names = [d.get("name", "") for d in devices]
    seen: set[str] = set()
    for name in names:
        if name in seen:
            issues.append(f"Duplicate device name: '{name}'")
        seen.add(name)

    # Check for isolated devices (no connections)
    connected_devices: set[str] = set()
    for link in links:
        connected_devices.add(link.get("device1", ""))
        connected_devices.add(link.get("device2", ""))

    for name in names:
        if name and name not in connected_devices:
            warnings.append(f"Device '{name}' has no connections")

    lines = [
        f"Topology Validation: {len(devices)} devices, {len(links)} connections",
        "",
    ]

    if issues:
        lines.append(f"ERRORS ({len(issues)}):")
        for issue in issues:
            lines.append(f"  ✗ {issue}")
    else:
        lines.append("✓ No errors found")

    if warnings:
        lines.append(f"\nWARNINGS ({len(warnings)}):")
        for warning in warnings:
            lines.append(f"  ⚠ {warning}")
    else:
        lines.append("✓ No warnings")

    return "\n".join(lines)


@mcp.tool()
async def pt_ping(
    source: Annotated[str, Field(description="Source device name")],
    destination: Annotated[str, Field(
        description="Destination IP address or device name (if using hostname resolution)"
    )],
    ctx: Context[ServerSession, AppContext] = None,
) -> str:
    """
    Execute a ping from a device to a destination IP address.

    Sends 'ping <destination>' via the device's CLI.
    The device must be configured with an IP address on the relevant interface.
    """
    queue = ctx.request_context.lifespan_context.queue
    commands = ["enable", f"ping {destination}"]
    result = await queue.configure_device(source, commands)

    if result.success:
        output = result.output or "(waiting for ping response...)"
        return f"Ping from {source} to {destination}:\n{output}"
    return f"✗ Ping failed: {result.error}"


@mcp.tool()
async def pt_traceroute(
    source: Annotated[str, Field(description="Source device name")],
    destination: Annotated[str, Field(description="Destination IP address")],
    ctx: Context[ServerSession, AppContext] = None,
) -> str:
    """
    Execute a traceroute from a device to a destination IP address.

    Sends 'traceroute <destination>' via the device's CLI.
    """
    queue = ctx.request_context.lifespan_context.queue
    commands = ["enable", f"traceroute {destination}"]
    result = await queue.configure_device(source, commands)

    if result.success:
        output = result.output or "(waiting for traceroute...)"
        return f"Traceroute from {source} to {destination}:\n{output}"
    return f"✗ Traceroute failed: {result.error}"


@mcp.tool()
async def pt_show_interfaces(
    device_name: Annotated[str, Field(description="Device name to query")],
    ctx: Context[ServerSession, AppContext] = None,
) -> str:
    """
    Show interface status and IP configuration for a device.

    Executes 'show ip interface brief' to display a summary of all interfaces.
    """
    queue = ctx.request_context.lifespan_context.queue
    result = await queue.configure_device(device_name, ["enable", "show ip interface brief"])

    if result.success:
        output = result.output or "(no output — ensure device is configured)"
        return f"Interfaces on {device_name}:\n{output}"
    return f"✗ Failed to get interfaces for {device_name}: {result.error}"


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #

def _resolve_param(value: str, params: dict) -> str:
    """Replace {key} placeholders in a string with params values."""
    for key, val in params.items():
        value = value.replace(f"{{{key}}}", str(val))
    return value
