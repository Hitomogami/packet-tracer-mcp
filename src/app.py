"""
Central FastMCP instance and lifespan context.

All tool/resource modules import `mcp` from here to register against
the same server instance. server.py imports mcp and triggers tool
registration by importing the tool modules.
"""

import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from dataclasses import dataclass

from mcp.server.fastmcp import FastMCP

from .bridge.pt_connection import PTConnection
from .bridge.command_queue import CommandQueue

logger = logging.getLogger(__name__)


@dataclass
class AppContext:
    """Shared state injected into every tool via ctx.request_context.lifespan_context."""
    queue: CommandQueue
    connection: PTConnection


@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncIterator[AppContext]:  # noqa: ARG001
    """
    Server lifespan: connect to PT on startup, disconnect on shutdown.
    Connection failure does NOT crash the server — tools will report
    the error gracefully when invoked.
    """
    pt = PTConnection()
    connected = await pt.connect()
    if not connected:
        logger.warning(
            "Packet Tracer is not reachable at startup. "
            "Tools will attempt reconnection on first use."
        )

    queue = CommandQueue(pt)
    try:
        yield AppContext(queue=queue, connection=pt)
    finally:
        await pt.disconnect()


mcp = FastMCP(
    "packet-tracer-mcp",
    lifespan=lifespan,
)
