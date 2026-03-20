"""
Packet Tracer MCP Server — entry point.

Registers all tools and resources, then starts the stdio transport.
"""

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
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger.info("Starting Packet Tracer MCP server")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
