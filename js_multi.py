# -*- coding: utf-8 -*-
"""Multi-report raw probe runner: collects EVERY result reported for N seconds.

Usage: python js_multi.py <js-file> <collect-seconds>
The JS file is sent RAW (shim only) — it must call reportResult() itself.
Prints every received payload with its arrival timestamp.
"""
import sys
import time
import urllib.request

sys.path.insert(0, r"D:\packet-tracer-mcp")
from src.bridge.script_builder import COMPAT_SHIM

BASE = "http://127.0.0.1:54321"

path = sys.argv[1]
collect = float(sys.argv[2]) if len(sys.argv) > 2 else 20.0
with open(path, "r", encoding="utf-8") as f:
    js = f.read()

try:
    urllib.request.urlopen(f"{BASE}/result?hold=0", timeout=3).read()
except Exception:
    pass

req = urllib.request.Request(
    f"{BASE}/queue", data=(COMPAT_SHIM + "\n" + js).encode("utf-8"), method="POST"
)
urllib.request.urlopen(req, timeout=5)
print("queued; collecting ...")

t0 = time.time()
deadline = t0 + collect
seen = 0
while time.time() < deadline:
    try:
        with urllib.request.urlopen(f"{BASE}/result", timeout=15) as r:
            b = r.read().decode("utf-8")
        if b:
            seen += 1
            print(f"[{time.time()-t0:6.1f}s] #{seen}: {b[:600]}")
            continue
    except Exception:
        pass
    time.sleep(0.1)
print(f"done, {seen} report(s)")
