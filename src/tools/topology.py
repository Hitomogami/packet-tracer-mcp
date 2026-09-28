"""
MCP tools for topology-level operations: templates, clear, validate, diagnostics.
"""

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Annotated

from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession
from pydantic import Field

from ..app import AppContext, mcp
from .devices import _resolve_device_type

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
        pt_type, _ = _resolve_device_type(dev["type"])
        resolved = {
            "name": _resolve_param(dev["name"], merged_params),
            "type": pt_type,
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
        detail = topology.get("error", "")
        return "Cannot export: Packet Tracer is not connected." + (f" ({detail})" if detail else "")

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
async def pt_get_active_file(
    ctx: Context[ServerSession, AppContext] = None,
) -> str:
    """
    Return the .pkt file path Packet Tracer currently has open/active.

    Empty result means the topology has never been saved to disk.
    Note: after pt_save_file_as, PT can take a few seconds to report the
    new active file — re-check after a short wait.
    """
    queue = ctx.request_context.lifespan_context.queue
    result = await queue.get_active_file()
    if result.success:
        data = result.data if isinstance(result.data, dict) else {}
        file = str(data.get("file") or "").strip()
        if file:
            return f"Active file: {file}"
        return "No active file — the topology has never been saved to disk."
    return f"✗ Failed to read active file: {result.error}"


@mcp.tool()
async def pt_save_file_as(
    file_path: Annotated[str, Field(
        description=(
            "Destination .pkt path, e.g. D:/labs/topology_v2.pkt. "
            "Overwrites an existing file silently. '.pkt' is appended when missing."
        )
    )],
    ctx: Context[ServerSession, AppContext] = None,
) -> str:
    """
    Save the current Packet Tracer architecture to a .pkt file — a true
    File→Save As performed by PT itself, capturing the complete live state
    (devices, cables, per-port IPs, NVRAM configs, PT-internal state),
    including changes not yet saved in the GUI.

    Standard Save-As semantics: PT switches its active working file to the
    new path (pt_get_active_file may need a few seconds to reflect it).
    Verify the result by the returned on-disk size/mtime, never by comparing
    .pkt bytes — PT serialises volatile runtime state (uptime counters,
    syslog timestamps), so every save differs even with no changes.

    Device config changes should be committed first with pt_save_config so
    the saved file contains the final startup-configs.
    """
    queue = ctx.request_context.lifespan_context.queue

    # PT (Qt) accepts both slash styles; forward slashes match what its own
    # APIs (getSavedFilename) return, so normalise to those.
    normalized = str(file_path).replace("\\", "/").strip()
    if not normalized:
        return "✗ file_path is empty"
    if not normalized.lower().endswith(".pkt"):
        normalized += ".pkt"

    result = await queue.save_file_as(normalized)
    if not result.success:
        return f"✗ Failed to save as '{normalized}': {result.error}"

    # PT-side success is silent (no exception even for bad directories?) —
    # anchor the verdict in the real file on disk instead of trusting it.
    target = Path(normalized)
    if target.exists():
        stat = target.stat()
        stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime))
        return (
            f"✓ Saved current PT architecture to {normalized}\n"
            f"On disk: {stat.st_size} bytes, mtime {stamp}\n"
            "(PT switched its active file to the new path — standard "
            "Save-As semantics; reopen the previous file if you want to "
            "keep working on it. Bytes always differ between saves due to "
            "volatile runtime state — size/mtime are the anchor, not content.)"
        )
    return (
        f"⚠ PT reported success but '{normalized}' was not found on disk — "
        "check the directory exists and the path is writable."
    )


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
    Execute a ping from a device to a destination IP address and return the
    result text.

    PT runs pings asynchronously, so the tool starts the ping, waits for it
    to settle, then collects the output. PC sources return the full ping
    transcript (Command-Prompt buffer); IOS sources fall back to the
    post-ping ARP table, because this PT build does not expose the ping
    console text for switches/routers through any script API.

    Timing rules (hard-won — see pt://ops/manual):
    - Run pings from the SAME source serially. Two parallel pings from one
      PC share a single console buffer and the transcripts get mixed.
    - First-packet timeouts usually mean ARP is still settling, not that the
      path is broken — re-test after 15-30 s before diagnosing.
    """
    queue = ctx.request_context.lifespan_context.queue
    result = await queue.ping(source, destination)

    if result.success:
        data = result.data if isinstance(result.data, dict) else {}
        output = str(data.get("output") or result.output or "").strip()
        if output:
            text = f"Ping from {source} to {destination}:\n{output}"
            lowered = output.lower()
            if "timed out" in lowered or "100% loss" in lowered:
                text += (
                    "\n\n(note: some timeouts may just be ARP settling — re-test "
                    "after 15-30 s; also make sure no other ping from this same "
                    "source is running in parallel)"
                )
            return text
        return (
            f"Ping from {source} to {destination}:\n"
            "(command executed in PT, but no console text was returned — "
            "check the result on the device CLI inside Packet Tracer)"
        )
    return f"✗ Ping failed: {result.error}"


@mcp.tool()
async def pt_traceroute(
    source: Annotated[str, Field(description="Source device name")],
    destination: Annotated[str, Field(description="Destination IP address")],
    ctx: Context[ServerSession, AppContext] = None,
) -> str:
    """
    Execute a traceroute from a device to a destination IP address and return
    the console output.

    Uses the same two-phase collection as pt_ping: the trace runs
    asynchronously and its text only appears in a console buffer afterwards.
    """
    queue = ctx.request_context.lifespan_context.queue
    result = await queue.async_cli(source, f"traceroute {destination}")

    if result.success:
        output = result.output.strip()
        if output:
            return f"Traceroute from {source} to {destination}:\n{output}"
        return (
            f"Traceroute from {source} to {destination}:\n"
            "(command executed in PT, but this PT build does not return console "
            "text — check the result on the device CLI inside Packet Tracer)"
        )
    return f"✗ Traceroute failed: {result.error}"


@mcp.tool()
async def pt_show_interfaces(
    device_name: Annotated[str, Field(description="Device name to query")],
    ctx: Context[ServerSession, AppContext] = None,
) -> str:
    """
    Show interface status and IP configuration for a device.

    Executes 'show ip interface brief' and returns the console output.
    """
    queue = ctx.request_context.lifespan_context.queue
    result = await queue.exec_cli(device_name, ["show ip interface brief"], timeout=20.0)

    if result.success:
        output = result.output.strip()
        if output:
            return f"Interfaces on {device_name}:\n{output}"
        return (
            f"Interfaces on {device_name}:\n"
            "(command executed in PT, but this PT build does not return console "
            "text — check the CLI inside Packet Tracer)"
        )
    return f"✗ Failed to get interfaces for {device_name}: {result.error}"


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #

def _resolve_param(value: str, params: dict) -> str:
    """Replace {key} placeholders in a string with params values."""
    for key, val in params.items():
        value = value.replace(f"{{{key}}}", str(val))
    return value
