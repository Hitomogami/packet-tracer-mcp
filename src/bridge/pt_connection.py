"""
HTTP bridge between Python and Packet Tracer via PTBuilder.

Architecture:
  1. This module runs a local HTTP server on port 54321.
  2. PTBuilder (with MCP bridge) auto-polls GET /next every 500 ms on startup.
  3. When a JS command is queued, /next returns it and PTBuilder executes
     it via $se('runCode', cmd) in PT's Script Engine.
  4. The command (wrapped by script_builder.wrap_with_result) calls
     reportResult(), which injects an XHR into the hidden MCP Bridge webview
     (the script engine itself has no HTTP access) and POSTs the result to
     /result. send_script() blocks on the result queue, turning the channel
     into a synchronous request-response.

Based on the approach from https://github.com/deiviidsito/mcp_packet_tracer
"""

import asyncio
import http.server
import itertools
import json
import logging
import threading
import time
from http.server import ThreadingHTTPServer
from queue import Empty, Queue
from typing import Any
from urllib.parse import parse_qs, urlparse

from .script_builder import BRIDGE_PORT, COMPAT_SHIM, wrap_with_result

logger = logging.getLogger(__name__)

# Default round-trip budget: PT polls every 500 ms, then executes the command
# in its emulated IOS (a "show run" on a 3560 can take a few seconds).
RESULT_TIMEOUT = 15.0


class PTConnectionError(Exception):
    """Raised when communication with Packet Tracer fails."""


class PTScriptError(PTConnectionError):
    """The command reached PT but the JS raised on the PT side."""


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
                # Query-string aware: /result?hold=0 must not lose the param.
                route = urlparse(self.path).path
                query = parse_qs(urlparse(self.path).query)
                if route == "/next":
                    bridge._last_poll = time.time()
                    bridge._connected_flag = True
                    try:
                        cmd = bridge._queue.get_nowait()
                    except Empty:
                        cmd = ""
                    self._respond(200, cmd)
                elif route == "/ping":
                    self._respond(200, "pong")
                elif route == "/shutdown":
                    self._respond(200, "bye")
                    threading.Thread(target=bridge._server.shutdown, daemon=True).start()
                elif route == "/status":
                    ago = time.time() - bridge._last_poll
                    ok = bridge._last_poll > 0 and ago < 5.0
                    self._respond(200, json.dumps({"connected": ok, "last_poll_ago": round(ago, 1)}))
                elif route == "/result":
                    # hold=1 (default): long-poll up to 9s for external probes.
                    # hold=0: non-blocking get_nowait — safe queue draining.
                    #
                    # ⚠ NEVER drain via a holding GET with a short client
                    # timeout: the handler keeps blocking in Queue.get after
                    # the client disconnects and steals the NEXT reported
                    # result into the dead socket (silent result loss —
                    # this cost a full debugging session, see MCP报告 §六).
                    if query.get("hold", ["1"])[0] == "0":
                        try:
                            self._respond(200, bridge._results.get_nowait())
                        except Empty:
                            self._respond(204, "")
                    else:
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

    def drain_results(self) -> None:
        """Drop any stale results left over from previous commands."""
        while True:
            try:
                self._results.get_nowait()
            except Empty:
                return

    def wait_result(self, timeout: float) -> str | None:
        """Block for the next reported result, or None on timeout."""
        try:
            return self._results.get(timeout=timeout)
        except Empty:
            return None


class PTConnection:
    """
    Async wrapper around PTCommandBridge used by the MCP tools.
    """

    def __init__(self, port: int = BRIDGE_PORT) -> None:
        self._bridge = PTCommandBridge(port)
        self._bridge._connected_flag = False
        self._connected = False
        self._seq = itertools.count(1)

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

    async def send_script(
        self, js_code: str, timeout: float = RESULT_TIMEOUT
    ) -> dict[str, Any]:
        """
        Execute a JS snippet in PT and wait for its reported result.

        Returns {"status": "ok", "output": str, "data": Any}. Raises
        PTScriptError when the JS raised on the PT side and
        PTConnectionError when no result came back (bridge down or a
        Builder-MCP.pts build without result-reporting support).
        """
        if not self._connected:
            # Auto-reconnect: PT may have started polling after MCP server started
            await self.reconnect()
        if not self._connected:
            raise PTConnectionError(
                "PTBuilder is not connected. "
                "Make sure Packet Tracer is open with the MCP bridge PTBuilder module installed."
            )

        seq = next(self._seq)
        self._bridge.drain_results()
        self._bridge.enqueue(COMPAT_SHIM + "\n" + wrap_with_result(js_code, seq))

        # Blocking Queue.get must not freeze the event loop.
        raw = await asyncio.to_thread(self._bridge.wait_result, timeout)

        if raw is None:
            if not self._bridge.is_connected:
                self._connected = False
                raise PTConnectionError(
                    "PT stopped polling — is Packet Tracer still open?"
                )
            raise PTConnectionError(
                f"PT accepted command #{seq} but never reported a result within "
                f"{timeout:.0f}s. If this happens on every call, the installed "
                "Builder-MCP.pts bridge is too old to report results — reinstall "
                "the latest module via Extensions > Scripting > Configure PT "
                "Script Modules."
            )

        return self._parse_result(raw, seq)

    @staticmethod
    def _parse_result(raw: str, seq: int) -> dict[str, Any]:
        raw = (raw or "").strip()
        if not raw:
            raise PTConnectionError("PT reported an empty result payload.")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            # Non-JSON body: treat it as raw text output.
            return {"status": "ok", "output": raw, "data": None}

        if not isinstance(payload, dict) or "result" not in payload:
            return {"status": "ok", "output": raw, "data": payload}

        if payload.get("seq") not in (None, seq):
            logger.warning(
                "Received result seq=%s while waiting for seq=%s", payload.get("seq"), seq
            )

        result = payload.get("result") or {}
        if result.get("ok") is False:
            raise PTScriptError(f"PT-side script error: {result.get('error', 'unknown')}")
        return {
            "status": "ok",
            "output": str(result.get("output", "") or ""),
            "data": result.get("data"),
        }

    async def send_command(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.send_script(payload.get("script", ""))

    def __repr__(self) -> str:
        status = "connected" if self.connected else "disconnected"
        return f"PTConnection(http-bridge:{self._bridge.port}, {status})"
