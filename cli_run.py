# -*- coding: utf-8 -*-
"""Full-output CLI reader: runs ScriptBuilder.exec_cli() against the live
bridge (same JS the MCP tools use) but returns the COMPLETE output —
pt_send_commands truncates each row to its first line.

Usage: python cli_run.py <device> <command> [command...]
"""
import json
import sys
import time
import urllib.request

sys.path.insert(0, r"D:\packet-tracer-mcp")
from src.bridge.script_builder import BRIDGE_PORT, COMPAT_SHIM, ScriptBuilder, wrap_with_result

BASE = f"http://127.0.0.1:{BRIDGE_PORT}"

device = sys.argv[1]
commands = sys.argv[2:]
js = ScriptBuilder().exec_cli(device, commands)

try:
    urllib.request.urlopen(f"{BASE}/result?hold=0", timeout=3).read()
except Exception:
    pass

req = urllib.request.Request(
    f"{BASE}/queue",
    data=(COMPAT_SHIM + "\n" + wrap_with_result(js, 426000)).encode("utf-8"),
    method="POST",
)
urllib.request.urlopen(req, timeout=5)

t0 = time.time()
while time.time() - t0 < 30:
    try:
        with urllib.request.urlopen(f"{BASE}/result", timeout=15) as r:
            b = r.read().decode("utf-8")
        if b:
            p = json.loads(b)
            res = p.get("result", {})
            if isinstance(res.get("data"), dict):
                print(res["data"].get("output", b))
            else:
                print(b)
            break
    except Exception:
        pass
    time.sleep(0.2)
else:
    print("NO RESULT in 30s")
