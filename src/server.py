"""
Packet Tracer MCP Server — entry point.

Supports two transports:
  stdio             — default, used by Claude Desktop / Claude Code
  http              — HTTP/SSE, used by OpenCode, Cursor, Continue, and any
                      MCP-compatible client that connects via URL
"""

import argparse
import json
import logging
from pathlib import Path

from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession

from .app import AppContext, mcp

# Register tools by importing their modules (decorators fire at import time)
from .tools import devices        # noqa: F401
from .tools import connections    # noqa: F401
from .tools import configuration  # noqa: F401
from .tools import topology       # noqa: F401

logger = logging.getLogger(__name__)

_CATALOG_DIR = Path(__file__).parent / "catalog"

# ------------------------------------------------------------------ #
# Resources                                                            #
# ------------------------------------------------------------------ #


@mcp.resource("pt://catalog/devices")
def catalog_devices() -> str:
    """
    Full catalog of devices available in Packet Tracer.
    Includes routers, switches, PCs, servers, and wireless devices with their port lists.
    """
    return (_CATALOG_DIR / "devices.json").read_text(encoding="utf-8")


@mcp.resource("pt://catalog/cables")
def catalog_cables() -> str:
    """
    Cable types supported by Packet Tracer with auto-selection rules.
    """
    return (_CATALOG_DIR / "cables.json").read_text(encoding="utf-8")


@mcp.resource("pt://catalog/templates")
def catalog_templates() -> str:
    """
    Predefined network topology templates.
    Use pt_apply_template to instantly deploy them.
    """
    return (_CATALOG_DIR / "templates.json").read_text(encoding="utf-8")


@mcp.resource("pt://ops/manual")
def ops_manual() -> str:
    """
    PT script-engine safety matrix and operational discipline, distilled
    from the debugging history (MCP故障现象报告.md §6.2/§7.6/§8.6/§9.4).

    Read this BEFORE bypassing the MCP tools to talk to the bridge or the
    PT script engine directly (probes, raw JS): several legitimate-looking
    IPC calls permanently hang the PT engine. Also covers cross-session
    state rules (.pkt vs NVRAM, same-source ping serialization, ARP
    settle-time retests).
    """
    return (_CATALOG_DIR / "ops_manual.md").read_text(encoding="utf-8")


@mcp.resource("pt://topology/current")
async def topology_current(ctx: Context[ServerSession, AppContext]) -> str:
    """
    Current live topology state from Packet Tracer.
    Returns devices, connections, and connection status.
    """
    queue = ctx.request_context.lifespan_context.queue
    topology = await queue.get_topology()
    return json.dumps(topology, indent=2)


# ------------------------------------------------------------------ #
# Entry point                                                          #
# ------------------------------------------------------------------ #

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Packet Tracer MCP Server",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="Transport mode. Use 'stdio' for Claude Desktop/Code; 'http' for all other clients.",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind when using HTTP transport.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=3000,
        help="Port to listen on when using HTTP transport.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if args.transport == "http":
        logger.info("Starting Packet Tracer MCP server — HTTP/SSE on %s:%d", args.host, args.port)
        mcp.run(transport="sse", host=args.host, port=args.port)
    else:
        logger.info("Starting Packet Tracer MCP server — stdio")
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
