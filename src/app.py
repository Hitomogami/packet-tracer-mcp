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

# Session-level operational guidance, delivered to every client at initialize
# time (MCP InitializeResult.instructions). Distilled from the ops history in
# MCP故障现象报告.md (§6.2/§7.6/§8.6/§9.4) — deep detail lives in the
# pt://ops/manual resource; this digest must stay short (~15 lines).
OPERATIONS_DIGEST = """\
Packet Tracer MCP usage notes:
- Write tools (add/connect/send_commands/configure_pc) confirm every command \
with ✓/✗; read tools return live PT data. Empty reads mean PT is disconnected \
— not "device not configured".
- pt_ping / pt_traceroute are two-phase (async, ~15-20s per call). Pings from \
the SAME source must run serially: parallel same-source pings mix outputs in \
one console buffer. First-packet timeouts are usually ARP still settling — \
re-test after 15-30s before diagnosing a failure.
- pt_save_config only writes device NVRAM. To survive a Packet Tracer restart \
you must ALSO save the .pkt file in the PT GUI (File→Save).
- Across sessions, spot-check completion markers (hostname, SVI IP) via \
pt_get_device_info / pt_get_running_config before trusting prior-session \
state: reopening a .pkt restores whatever was last saved to disk.
- Do NOT bypass the tools by POSTing raw JS to the bridge HTTP endpoints; the \
PT script engine hangs on several legitimate-looking IPC calls (see resource \
pt://ops/manual for the full safety matrix).
"""


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
    instructions=OPERATIONS_DIGEST,
    lifespan=lifespan,
)
