# -*- coding: utf-8 -*-
"""
Offline regression tests for the PTBuilder bridge (no Packet Tracer needed).

A fake webview thread reproduces the behaviour of Builder-MCP.pts's hidden
mcpbridge.html: it polls GET /next, "executes" the received command and
reports results via POST /result — the same contract as the shim's
reportResult(). This exercises the full request-response round trip of
PTConnection.send_script without a live PT instance.

Run:  pytest tests/ -v
"""

import asyncio
import json
import re
import threading
import time
import urllib.request
from pathlib import Path

try:
    import pytest
except ImportError:  # allow running without pytest installed
    pytest = None

from src.bridge.command_queue import CommandQueue, looks_like_ios_error
from src.bridge.pt_connection import PTConnection, PTConnectionError, PTScriptError
from src.bridge.script_builder import COMPAT_SHIM, ScriptBuilder, wrap_with_result

TEST_PORT = 55321


def _check_no_line_comments(name: str, js: str) -> None:
    """PTBuilder builds may strip newlines — // comments would swallow code."""
    bad = re.search(r"(^|[^:\"'])//[^\"']*$", js, re.M)
    assert not bad, f"{name}: found // comment: {bad.group(0)[:60]!r}"


class FakePTWebview:
    """Mimics the hidden MCP Bridge webview polling loop."""

    def __init__(self, port: int):
        self.port = port
        self.answer = True
        self.fail_next = False

    def start(self) -> None:
        threading.Thread(target=self._loop, daemon=True).start()
        deadline = time.time() + 5
        while time.time() < deadline:
            if self._seen_poll:
                return
            time.sleep(0.05)
        raise RuntimeError("fake webview never polled /next")

    _seen_poll = False

    def _loop(self) -> None:
        while True:
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{self.port}/next", timeout=2
                ) as r:
                    body = r.read().decode("utf-8")
            except Exception:
                time.sleep(0.2)
                continue
            self._seen_poll = True
            if not body:
                time.sleep(0.2)
                continue
            if not self.answer:
                time.sleep(0.5)
                continue  # hold the command unanswered (timeout path)
            assert body.startswith(COMPAT_SHIM), "command must carry the shim"
            assert "(function(){" in body
            assert "reportResult(JSON.stringify({seq:" in body
            seq = int(re.search(r"\{seq:(\d+),result:__res\}", body).group(1))
            if self.fail_next:
                out = {"seq": seq, "result": {"ok": False,
                       "error": "Device 'ghost' not found in Packet Tracer"}}
            elif "getDeviceCount()" in body:
                out = {"seq": seq, "result": {"ok": True, "data": {
                    "devices": [{"name": "switchC", "type": "3560-24PS",
                                 "categoryId": 16, "x": 380, "y": 60, "ports": []}],
                    "links": [{"device1": "pc2", "port1": "FastEthernet0",
                               "device2": "switchA", "port2": "FastEthernet0/1"}],
                }}}
            elif "__out={results:__res};" in body:
                # configure_device payload → per-command {cmd, first, out} rows
                out = {"seq": seq, "result": {"ok": True, "data": {"results": [
                    {"cmd": "vlan 10", "first": 0, "out": ""},
                    {"cmd": "ip address 10.0.0.1 255.0.0.0", "first": 0,
                     "out": "% Invalid input detected at '^' marker."},
                ]}}}
            elif '{cmd:"write memory"' in body:
                # save_device_config payload → captured save confirmation
                out = {"seq": seq, "result": {"ok": True, "data": {"results": [
                    {"cmd": "write memory", "first": 0,
                     "out": "Building configuration...\n[OK]"},
                ]}}}
            elif "started:true" in body:
                # async_start payload (ping/traceroute phase 1)
                out = {"seq": seq, "result": {"ok": True,
                       "data": {"ok": True, "started": True}}}
            elif 'source:"pc-command-prompt-buffer"' in body and '"show ip arp"' not in body:
                # async_collect payload → ping transcript from the buffer
                # (the ios-fallback payload embeds the same PC strings but
                # only executes them for non-PC devices — match by the
                # fallback command's absence)
                out = {"seq": seq, "result": {"ok": True, "data": {
                    "ok": True, "source": "pc-command-prompt-buffer",
                    "output": "Pinging 10.0.0.9 with 32 bytes of data:\n"
                              "Reply from 10.0.0.9: bytes=32 time<1ms TTL=128",
                }}}
            elif '"show ip arp"' in body:
                out = {"seq": seq, "result": {"ok": True, "data": {
                    "ok": True, "source": "ios-fallback",
                    "output": "Internet  10.0.0.9  12  00d0.ba10.7f01  ARPA  Vlan10",
                }}}
            else:
                out = {"seq": seq, "result": {"ok": True,
                       "data": {"ok": True, "output": "Fa0/1  up  up"}}}
            req = urllib.request.Request(
                f"http://127.0.0.1:{self.port}/result",
                data=json.dumps(out).encode("utf-8"), method="POST")
            urllib.request.urlopen(req, timeout=2)


def test_js_payloads_use_real_ipc_primitives():
    b = ScriptBuilder()
    assert ".removeDevice(" in b.remove_device('we"ird')
    assert "deleteLink(" in b.remove_link("sw1", "Fa0/1")
    assert "moveToLocation(" in b.move_device("pc1", 5, 6)
    topo = b.get_topology()
    assert "getDeviceCount()" in topo and "getLinkCount()" in topo
    assert "__out={devices:__devices,links:__links};" in topo
    assert f"127.0.0.1:{54321}/result" in COMPAT_SHIM
    assert "reportResult=function" in COMPAT_SHIM
    # reportResult transport: encodeURIComponent leaves "'" raw and the
    # payload rides in a single-quoted JS literal — an apostrophe in any
    # reported text froze the webview with "SyntaxError: Parse error" (§八).
    assert "replace(/'/g,\"%27\")" in COMPAT_SHIM
    # exec_cli: PC-PT devices have NO enterCommand — the Command-Prompt
    # terminal (getCommandPrompt + one-arg enterCommand + buffer delta) is
    # the only working CLI path on PCs (§八).
    cli = b.exec_cli("pc1", ["ipconfig"])
    assert "getCommandPrompt()" in cli and "getOutput()" in cli
    assert b.async_start("pc2", "ping 10.0.0.9").count("enterCommand(") >= 1
    assert "lastIndexOf(" in b.async_collect("pc2", "ping 10.0.0.9")
    # configure_device: exec-style loop with mode-settle spin + per-command
    # results — never the PTBuilder configureIosDevice that swallowed the
    # first command, and no silent auto-save.
    cfg = b.configure_device("switchC", ["enable", "conf t", "vlan 10", "name Sales"])
    assert '"!","global"' in cfg
    assert "getTime()" in cfg
    assert "__out={results:__res};" in cfg
    assert "configureIosDevice(" not in cfg
    assert "write memory" not in cfg
    assert json.dumps(["vlan 10", "name Sales"]) in cfg  # navigation cmds filtered
    save = b.save_device_config("switchC")
    assert '"!","enable"' in save and "write memory" in save
    for js in (b.add_device("pc1", "PC-PT", 1, 2), b.add_link("a", "Fa0", "b", "Fa0/1", "cross"),
               b.configure_pc_ip("pc1", "1.1.1.1", "255.0.0.0", "", ""), b.exec_cli("r1", ["show run"]),
               cfg, save):
        _check_no_line_comments("payload", js)
    _check_no_line_comments("shim", COMPAT_SHIM)
    wrapped = wrap_with_result('addDevice("x","PC-PT",1,2);', 7)
    assert wrapped.startswith("(function(){") and wrapped.endswith("})();")
    assert "{seq:7,result:__res}" in wrapped


def test_ios_error_heuristics():
    assert looks_like_ios_error("% Invalid input detected at '^' marker.")
    assert looks_like_ios_error('% Ambiguous command:  "sho"')
    assert looks_like_ios_error("% Incomplete command.")
    assert looks_like_ios_error("sh\r\nTranslating ...domain server (255.255.255.255)")
    assert not looks_like_ios_error("")
    assert not looks_like_ios_error("Building configuration... [OK]")
    # syslog notices start with '%' too but are NOT command errors
    assert not looks_like_ios_error(
        "%SYS-5-CONFIG_I: Configured from console by console")
    assert not looks_like_ios_error(
        "%LINK-5-CHANGED: Interface FastEthernet0/1, changed state to up")


def test_bridge_request_response_roundtrip():
    async def run():
        conn = PTConnection(port=TEST_PORT)
        await conn.connect()
        fake = FakePTWebview(TEST_PORT)
        fake.start()
        time.sleep(0.2)
        b = ScriptBuilder()

        # 1) CLI read with captured output
        res = await conn.send_script(b.exec_cli("switchC", ["show running-config"]), timeout=10)
        assert res["status"] == "ok"
        assert res["data"]["output"] == "Fa0/1  up  up"

        # 2) topology read
        res = await conn.send_script(b.get_topology(), timeout=10)
        assert res["data"]["devices"][0]["name"] == "switchC"
        assert res["data"]["links"][0]["device1"] == "pc2"

        # 3) PT-side errors surface as PTScriptError — no more fake success
        fake.fail_next = True
        with raises(PTScriptError, "not found"):
            await conn.send_script(b.remove_device("ghost"), timeout=10)
        fake.fail_next = False

        # 4) withheld answer → actionable timeout error
        fake.answer = False
        with raises(PTConnectionError, "never reported a result"):
            await conn.send_script(b.add_device("pc1", "PC-PT", 1, 2), timeout=2)
        fake.answer = True

        # 5) configure_device round trip: per-command rows + IOS-error flagging
        queue = CommandQueue(conn)
        res = await queue.configure_device(
            "switchC", ["enable", "vlan 10", "ip address 10.0.0.1 255.0.0.0"])
        assert res.success
        rows = res.data["results"]
        assert [r["cmd"] for r in rows] == ["vlan 10", "ip address 10.0.0.1 255.0.0.0"]
        assert rows[0]["failed"] is False
        assert rows[1]["failed"] is True
        assert "Invalid input" in rows[1]["error"]

        # 6) save_config returns the captured 'write memory' confirmation
        res = await queue.save_config("switchC")
        assert res.success
        assert res.data["results"][0]["cmd"] == "write memory"
        assert res.data["results"][0]["failed"] is False

        # 7) two-phase async ping: PC transcript via the Command-Prompt buffer
        res = await queue.async_cli("pc2", "ping 10.0.0.9", settle=0.1)
        assert res.success
        assert res.data["source"] == "pc-command-prompt-buffer"
        assert "Reply from 10.0.0.9" in res.data["output"]

        # 8) IOS source: ping falls back to the post-ping ARP table
        queue.PING_SETTLE_SECONDS = 0.1  # instance shadow; keep the test fast
        res = await queue.ping("switchC", "10.0.0.9")
        assert res.success
        assert res.data["source"] == "ios-fallback"
        assert "10.0.0.9" in res.data["output"]

    asyncio.run(run())


def test_drain_endpoint_is_non_blocking():
    """/result?hold=0 must return instantly — a holding GET whose client
    times out early leaves an orphaned handler that steals the next result
    (the silent-loss bug fixed here)."""
    async def run():
        # Own port: the roundtrip test's server lingers (Windows TIME_WAIT /
        # bind error 10048) when both tests share TEST_PORT.
        drain_port = TEST_PORT + 1
        conn = PTConnection(port=drain_port)
        await conn.connect()
        fake = FakePTWebview(drain_port)
        fake.start()
        time.sleep(0.2)
        base = f"http://127.0.0.1:{drain_port}/result"

        # queued result → returned immediately by hold=0
        req = urllib.request.Request(
            base,
            data=json.dumps({"seq": 1, "result": {"ok": True, "data": "stale"}}).encode(),
            method="POST",
        )
        urllib.request.urlopen(req, timeout=5)
        t0 = time.time()
        with urllib.request.urlopen(f"{base}?hold=0", timeout=5) as r:
            body = r.read().decode()
        assert "stale" in body
        assert time.time() - t0 < 3, "hold=0 must not block for the 9s hold window"

        # empty queue → immediate 204, no hold
        t0 = time.time()
        with urllib.request.urlopen(f"{base}?hold=0", timeout=5) as r:
            assert r.read() == b""
        assert time.time() - t0 < 3, "hold=0 on an empty queue must not block ~9s"

    asyncio.run(run())


def test_server_instructions_digest_is_set():
    """The session-level instructions (MCP InitializeResult) must carry the
    operational digest — it is the always-on replacement for re-reading the
    full fault report in every new session."""
    from src.app import OPERATIONS_DIGEST, mcp

    assert mcp.instructions == OPERATIONS_DIGEST
    for needle in (
        "serially",          # same-source ping discipline
        "15-30s",            # ARP settle retest window
        "File→Save",         # NVRAM ≠ .pkt on disk
        "pt://ops/manual",   # pointer to the deep manual
    ):
        assert needle in OPERATIONS_DIGEST, f"digest missing: {needle}"


def test_ops_manual_resource_covers_safety_matrix():
    """pt://ops/manual must contain the hard-won engine-safety facts so a
    probing agent cannot repeat the engine-hang history."""
    manual = (
        Path(__file__).resolve().parent.parent / "src" / "catalog" / "ops_manual.md"
    ).read_text(encoding="utf-8")
    for needle in (
        "getCommandPrompt",        # PC-PT only CLI path
        "enterCommand(cmd, mode)", # IOS two-arg form
        "show ip arp",             # IOS ping fallback
        "setTimeout",              # IPC-in-callback hang rule
        "hold=0",                  # orphan-handler drain fix
        "File→Save",               # .pkt persistence discipline
        "lastIndexOf",             # same-source ping buffer mixing
        "%27",                     # shim apostrophe escape
    ):
        assert needle in manual, f"ops manual missing: {needle}"


def raises(exc_type, match):
    """pytest.raises, with a fallback when pytest is not installed."""
    if pytest is not None:
        return pytest.raises(exc_type, match=match)
    return _raises(exc_type, match)


class _raises:
    """Minimal stand-in for pytest.raises when pytest is unavailable."""

    def __init__(self, exc_type, match):
        self._exc_type = exc_type
        self._match = match

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        assert issubclass(exc_type, self._exc_type), f"expected {self._exc_type.__name__}, got {exc_type}"
        assert re.search(self._match, str(exc)), f"message {str(exc)!r} does not match {self._match!r}"
        return True
