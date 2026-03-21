"""
HTTP bridge between Python and Packet Tracer via PTBuilder.

Architecture:
  1. This module runs a local HTTP server on port 54321.
  2. PTBuilder (with MCP bridge) auto-polls GET /next every 500 ms on startup.
  3. When a JS command is queued, /next returns it and PTBuilder executes
     it via $se('runCode', cmd) in PT's Script Engine.
  4. Results come back via POST /result.

Based on the approach from https://github.com/deiviidsito/mcp_packet_tracer
"""

import asyncio
import http.server
import json
import logging
import threading
import time
from http.server import ThreadingHTTPServer
from queue import Empty, Queue
from typing import Any

logger = logging.getLogger(__name__)

BRIDGE_PORT = 54321


class PTConnectionError(Exception):
    """Raised when communication with Packet Tracer fails."""


class PTCommandBridge:
    """HTTP server that PTBuilder's webview polls for JS commands."""

    def __init__(self, port: int = BRIDGE_PORT):
        self.port = port
        self._queue: Queue[str] = Queue()
        self._results: Queue[str] = Queue()
        self._server = None
        self._thread = None
        self._last_poll: float = 0.0

    def _kill_stale_server(self) -> None:
        """Shut down any leftover bridge server from a previous MCP process."""
        import urllib.request
        try:
            urllib.request.urlopen(
                f"http://127.0.0.1:{self.port}/shutdown", timeout=2
            )
        except Exception:
            pass
        time.sleep(0.3)

    def start(self) -> None:
        self._kill_stale_server()
        bridge = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/next":
                    bridge._last_poll = time.time()
                    bridge._connected_flag = True
                    try:
                        cmd = bridge._queue.get_nowait()
                    except Empty:
                        cmd = ""
                    self._respond(200, cmd)
                elif self.path == "/ping":
                    self._respond(200, "pong")
                elif self.path == "/shutdown":
                    self._respond(200, "bye")
                    threading.Thread(target=bridge._server.shutdown, daemon=True).start()
                elif self.path == "/status":
                    ago = time.time() - bridge._last_poll
                    ok = bridge._last_poll > 0 and ago < 5.0
                    self._respond(200, json.dumps({"connected": ok, "last_poll_ago": round(ago, 1)}))
                elif self.path == "/result":
                    try:
                        result = bridge._results.get(timeout=9.0)
                        self._respond(200, result)
                    except Empty:
                        self._respond(204, "")
                else:
                    self._respond(404, "")

            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode("utf-8") if length else ""
                if self.path == "/result":
                    bridge._results.put(body)
                    self._respond(200, "ok")
                elif self.path == "/queue":
                    if body:
                        bridge._queue.put(body)
                    self._respond(200, "queued")
                else:
                    self._respond(404, "")

            def do_OPTIONS(self):
                self.send_response(200)
                self._cors()
                self.end_headers()

            def _respond(self, code, body):
                self.send_response(code)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self._cors()
                self.end_headers()
                self.wfile.write(body.encode("utf-8"))

            def _cors(self):
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")

            def log_message(self, *args):
                pass  # silence HTTP logs

        ThreadingHTTPServer.allow_reuse_address = False
        self._server = ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        logger.info("PT bridge HTTP server started on port %d", self.port)

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()

    @property
    def is_connected(self) -> bool:
        return self._last_poll > 0 and (time.time() - self._last_poll) < 5.0

    def enqueue(self, js: str) -> None:
        self._queue.put(js)


class PTConnection:
    """
    Async wrapper around PTCommandBridge used by the MCP tools.
    """

    def __init__(self, port: int = BRIDGE_PORT) -> None:
        self._bridge = PTCommandBridge(port)
        self._bridge._connected_flag = False
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect(self) -> bool:
        """Start the bridge server and check if PT is already polling."""
        if self._bridge._server is None:
            self._bridge.start()
        self._connected = self._bridge.is_connected
        if not self._connected:
            logger.warning(
                "PTBuilder is not polling yet. "
                "Make sure Packet Tracer is open with the MCP bridge PTBuilder module installed."
            )
        return self._connected

    async def disconnect(self) -> None:
        self._connected = False

    async def reconnect(self) -> bool:
        self._connected = self._bridge.is_connected
        return self._connected

    async def send_script(self, js_code: str) -> dict[str, Any]:
        """
        Queue a JS snippet for execution in PT.
        Fire-and-forget: no result returned (PTBuilder doesn't send responses
        unless the script explicitly calls reportResult()).
        """
        if not self._connected:
            # Auto-reconnect: PT may have started polling after MCP server started
            await self.reconnect()
        if not self._connected:
            raise PTConnectionError(
                "PTBuilder is not connected. "
                "Make sure Packet Tracer is open with the MCP bridge PTBuilder module installed."
            )
        self._bridge.enqueue(js_code)
        # Give PT time to pick it up
        await asyncio.sleep(0.6)
        # Confirm bridge is still alive
        if not self._bridge.is_connected:
            self._connected = False
            raise PTConnectionError("PT stopped polling — is Packet Tracer still open?")
        return {"status": "ok", "output": ""}

    async def send_command(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.send_script(payload.get("script", ""))

    async def get_topology_state(self) -> dict[str, Any]:
        if not self._connected:
            return {"state": "disconnected", "devices": [], "links": []}
        return {"state": "connected", "devices": [], "links": []}

    def __repr__(self) -> str:
        status = "connected" if self.connected else "disconnected"
        return f"PTConnection(http-bridge:{self._bridge.port}, {status})"
