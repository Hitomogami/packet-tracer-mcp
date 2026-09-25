# -*- coding: utf-8 -*-
"""Generic one-shot JS probe runner: reads JS from a file, wraps, reports.

Usage: python js_run.py <js-file> [timeout]
The JS assigns __out; wrap_with_result handles errors + reporting.
Prints the decoded data payload (or the raw body on parse failure).
"""
import json
import sys
import time
import urllib.request

sys.path.insert(0, r"D:\packet-tracer-mcp")
from src.bridge.script_builder import COMPAT_SHIM, wrap_with_result

BASE = "http://127.0.0.1:54321"

path = sys.argv[1]
timeout = float(sys.argv[2]) if len(sys.argv) > 2 else 45.0
with open(path, "r", encoding="utf-8") as f:
    js = f.read()

try:
    urllib.request.urlopen(f"{BASE}/result?hold=0", timeout=3).read()
except Exception:
    pass

req = urllib.request.Request(
    f"{BASE}/queue",
    data=(COMPAT_SHIM + "\n" + wrap_with_result(js, 425000)).encode("utf-8"),
    method="POST",
)
urllib.request.urlopen(req, timeout=5)

t0 = time.time()
while time.time() - t0 < timeout:
    try:
        with urllib.request.urlopen(f"{BASE}/result", timeout=15) as r:
            b = r.read().decode("utf-8")
        if b:
            print(f"t={time.time()-t0:.1f}s")
            try:
                p = json.loads(b)
                res = p.get("result", {})
                print(res if not isinstance(res, dict) else json.dumps(res, ensure_ascii=False))
            except Exception:
                print(b)
            break
    except Exception:
        pass
    time.sleep(0.2)
else:
    print(f"NO RESULT in {timeout}s")
