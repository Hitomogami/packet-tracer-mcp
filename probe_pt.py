# -*- coding: utf-8 -*-
"""
Live probe utility for the running PT MCP bridge (no MCP server restart needed).

Talks directly to the bridge HTTP server already started by the MCP server
(port 54321): POST /queue submits raw JS, GET /result collects values
reported by the shim's reportResult(). Used to explore the PT script-engine
IPC API interactively (device object methods, console-read primitives,
ping output capture).

Probes ending in "!" are sent RAW (no wrap_with_result) — they manage their
own reportResult() calls, possibly delayed via setTimeout.

Run:  python probe_pt.py <probe-name> [...]

⚠ ENGINE-HANG SAFETY MATRIX (a hung engine requires a Packet Tracer restart;
   symptom: GET /status still connected but no probe ever returns):

   SAFE on switches (3560/2960): device.enterCommand(cmd, mode), skipBoot(),
        getCommandLine().getOutput()/.getMode()/.getPrompt(),
        getIpcTerminalLine().getOutput()/.getMode()
   SAFE on PC-PT: ONLY device.enterCommand() and skipBoot() —
        getCommandLine()/getIpcTerminalLine() on a PC HANG the engine!
   DEADLY everywhere: cl.enterCommand(); ANY IPC call inside a setTimeout
        callback (bare reportResult-only callbacks are fine).

   Run `python probe_pt.py env` before risky probes to check liveness.
   Details + findings: MCP故障现象报告.md §六.
"""

import json
import sys
import time
import urllib.request

sys.path.insert(0, r"D:\packet-tracer-mcp")

from src.bridge.script_builder import BRIDGE_PORT, COMPAT_SHIM, wrap_with_result  # noqa: E402

BASE = f"http://127.0.0.1:{BRIDGE_PORT}"


def _drain() -> None:
    """Drop stale results via the non-holding endpoint.

    ⚠ Must NOT use a plain GET /result with a short client timeout: the
    server-side handler keeps blocking in Queue.get(timeout=9) after the
    client disconnects, and that orphaned handler then STEALS the next
    reported result into the dead socket — the probe times out while the
    command actually executed fine (this bug cost a whole debugging
    session; details in MCP故障现象报告.md §六).
    """
    try:
        urllib.request.urlopen(f"{BASE}/result?hold=0", timeout=3).read()
    except Exception:
        pass


def _matches_seq(body: str, seq: int) -> bool:
    """True when a reported payload belongs to the given seq (or is opaque)."""
    try:
        payload = json.loads(body)
    except Exception:
        return True  # non-JSON body — surface it as-is
    if isinstance(payload, dict) and payload.get("seq") not in (None, seq):
        return False
    return True


def send_wrapped(js: str, seq: int, timeout: float = 25.0) -> str:
    """Queue a wrapped JS snippet and fetch its reported result."""
    _drain()
    req = urllib.request.Request(
        f"{BASE}/queue",
        data=(COMPAT_SHIM + "\n" + wrap_with_result(js, seq)).encode("utf-8"),
        method="POST",
    )
    urllib.request.urlopen(req, timeout=5)

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{BASE}/result", timeout=12) as r:
                body = r.read().decode("utf-8")
                if body and _matches_seq(body, seq):
                    return body
        except Exception:
            pass
        time.sleep(0.3)
    return "<<TIMEOUT>>"


def send_raw(js: str, timeout: float = 40.0) -> str:
    """Queue RAW js (shim only) and return the first reported result.

    Run one raw probe per invocation: stale delayed results are drained
    before queuing, so the first result belongs to this probe.
    """
    _drain()
    req = urllib.request.Request(
        f"{BASE}/queue",
        data=(COMPAT_SHIM + "\n" + js).encode("utf-8"),
        method="POST",
    )
    urllib.request.urlopen(req, timeout=5)

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{BASE}/result", timeout=12) as r:
                body = r.read().decode("utf-8")
                if body:
                    return body
        except Exception:
            pass
        time.sleep(0.3)
    return "<<TIMEOUT>>"


REPORT = lambda seq, out: (
    'try{reportResult(JSON.stringify({seq:' + str(seq)
    + ',result:{ok:true,data:{output:' + json.dumps(out) + '}}}));}catch(e){}'
)

PROBES: dict[str, str] = {
    # ---- wrapped probes (assign to __out) -------------------------------- #
    "env": r"""
var r=[];
r.push("setTimeout="+typeof setTimeout);
r.push("qt="+typeof qt);
r.push("print="+typeof print);
r.push("console="+typeof console);
r.push("JSON="+typeof JSON);
r.push("Promise="+typeof Promise);
__out=r.join(" , ");
""",
    "device": r"""
var d=null;try{d=ipc.network().getDevice("switchC");}catch(e){}
if(!d){__out="NO DEVICE";}else{
var ks=[];for(var k in d){ks.push(k);}
__out=ks.join("|");}
""",
    "network": r"""
var n=null;try{n=ipc.network();}catch(e){}
if(!n){__out="NO NETWORK";}else{
var ks=[];for(var k in n){ks.push(k);}
__out=ks.join("|");}
""",
    "appwin": r"""
var w=null;try{w=ipc.appWindow();}catch(e){__out="EXC:"+e;}
if(w){var ks=[];for(var k in w){ks.push(k);}__out=ks.join("|");}
""",
    "cmdline_obj": r"""
var d=null;try{d=ipc.network().getDevice("switchC");}catch(e){}
if(!d){__out="NO DEVICE";}else{
var o=null;try{o=d.getCommandLine();}catch(e){__out="EXC:"+e;}
var ks=[];try{for(var k in o){ks.push(k);}}catch(e){}
__out="keys="+ks.join("|");}
""",
    "output_tail": r"""
var d=null;try{d=ipc.network().getDevice("switchC");}catch(e){}
if(!d){__out="NO DEVICE";}else{
var cl=d.getCommandLine();
var o="";
try{o=String(cl.getOutput());}catch(e){__out="EXC:"+e;}
__out="len="+o.length+"\nTAIL>>>\n"+o.substring(Math.max(0,o.length-1200));}
""",
    # ---- raw probes (own reportResult) ----------------------------------- #
    "ping_hunt2!": r"""
(function(){
var SEQ=77703;
var d=null;
try{d=ipc.network().getDevice("switchC");}catch(e){}
try{if(d){d.skipBoot();}}catch(e){}
try{d.enterCommand("enable","enable");}catch(e){}
var cl=null;try{cl=d.getCommandLine();}catch(e){}
var tl=null;try{tl=d.getIpcTerminalLine();}catch(e){}
var base_cl="";
try{base_cl=String(cl.getOutput());}catch(e){base_cl="EXC:"+e;}
var s1="!no-ping";
try{var o1=d.enterCommand("ping 192.168.0.3","");s1=JSON.stringify(o1);}catch(e){s1="EXC:"+e;}
setTimeout(function(){
var r=[];
function add(n,f){try{r.push(n+"="+f());}catch(e){r.push(n+"_EXC:"+e);}}
add("immediate_second",function(){return s1;});
add("cl_len_before",function(){return base_cl.length;});
add("cl_len_after",function(){return String(cl.getOutput()).length;});
add("cl_tail",function(){var o=String(cl.getOutput());return o.substring(Math.max(0,o.length-600));});
add("tl_len",function(){return String(tl.getOutput()).length;});
add("tl_mode",function(){return String(tl.getMode());});
var msg="";
try{msg=r.join("\n");}catch(e){msg="join_EXC:"+e;}
""" + REPORT(77703, "REPLACE_OUT") + """
},12000);
})();
""",
    # Bare timer ladder: how long can a setTimeout delay be and still fire?
    "timer12!": r"""
setTimeout(function(){
""" + REPORT(77704, "TIMER12 FIRED") + """
},12000);
""",
    "timer5!": r"""
setTimeout(function(){
""" + REPORT(77705, "TIMER5 FIRED") + """
},5000);
""",
    # Log into the GUI console session (press RETURN at "Press RETURN to get started")
    "cl_login!": r"""
(function(){
var d=null;try{d=ipc.network().getDevice("switchC");}catch(e){}
var cl=null;try{cl=d.getCommandLine();}catch(e){}
var r=[];
try{var o=cl.enterCommand("","");r.push("enter_ret="+JSON.stringify(o));}catch(e){r.push("enter_EXC:"+e);}
try{r.push("mode="+String(cl.getMode()));}catch(e){r.push("mode_EXC:"+e);}
try{r.push("prompt="+String(cl.getPrompt()));}catch(e){r.push("prompt_EXC:"+e);}
try{r.push("cl_tail="+String(cl.getOutput()).substring(Math.max(0,String(cl.getOutput()).length-300)));}catch(e){r.push("tail_EXC:"+e);}
""" + "var msg=r.join('\\n');" + """
try{reportResult(JSON.stringify({seq:55501,result:{ok:true,data:{output:msg}}}));}catch(e){}
})();
""",
    # Send ping THROUGH the GUI console session
    "cl_ping!": r"""
(function(){
var d=null;try{d=ipc.network().getDevice("switchC");}catch(e){}
var cl=null;try{cl=d.getCommandLine();}catch(e){}
var r=[];
try{r.push("mode_before="+String(cl.getMode()));}catch(e){}
try{cl.enterCommand("enable","enable");}catch(e){r.push("en_EXC:"+e);}
try{r.push("mode_after_en="+String(cl.getMode()));}catch(e){}
var s="!none";
try{var o=cl.enterCommand("ping 192.168.0.3","");s=JSON.stringify(o);}catch(e){s="EXC:"+e;}
r.push("ping_ret="+s);
""" + "var msg=r.join('\\n');" + """
try{reportResult(JSON.stringify({seq:55502,result:{ok:true,data:{output:msg}}}));}catch(e){}
})();
""",
    # Read GUI console tail afterwards
    "cl_tail2!": r"""
(function(){
var d=null;try{d=ipc.network().getDevice("switchC");}catch(e){}
var cl=null;try{cl=d.getCommandLine();}catch(e){}
var o="";
try{o=String(cl.getOutput());}catch(e){o="EXC:"+e;}
""" + "var msg='len='+o.length+'\\nTAIL>>>\\n'+o.substring(Math.max(0,o.length-1500));" + """
try{reportResult(JSON.stringify({seq:55503,result:{ok:true,data:{output:msg}}}));}catch(e){}
})();
""",
    # TEST A1: pc2 ping — capture full enterCommand return + baselines
    "test_pc_ping1!": r"""
(function(){
var d=null;try{d=ipc.network().getDevice("pc2");}catch(e){}
var cl=null;try{cl=d.getCommandLine();}catch(e){}
var tl=null;try{tl=d.getIpcTerminalLine();}catch(e){}
var base=-1;try{base=String(cl.getOutput()).length;}catch(e){}
try{d.skipBoot();}catch(e){}
try{d.enterCommand("enable","enable");}catch(e){}
var s="!none";
try{var o=d.enterCommand("ping 192.168.0.3","");s=JSON.stringify(o);}catch(e){s="EXC:"+e;}
var r=[];
r.push("base_cl_len="+base);
r.push("ping_ret="+s);
try{r.push("tl_mode="+String(tl.getMode()));}catch(e){r.push("tl_EXC:"+e);}
try{r.push("cl_mode="+String(cl.getMode()));}catch(e){}
var msg=r.join("\n");
try{reportResult(JSON.stringify({seq:88801,result:{ok:true,data:{output:msg}}}));}catch(e){}
})();
""",
    # TEST A2: pc2 buffers 12s after the ping
    "test_pc_ping2!": r"""
(function(){
var d=null;try{d=ipc.network().getDevice("pc2");}catch(e){}
var cl=null;try{cl=d.getCommandLine();}catch(e){}
var tl=null;try{tl=d.getIpcTerminalLine();}catch(e){}
var o="";
try{o=String(cl.getOutput());}catch(e){o="EXC:"+e;}
var t="";
try{t=String(tl.getOutput());}catch(e){t="EXC:"+e;}
var msg="cl_len="+o.length+"\ncl_tail>>>\n"+o.substring(Math.max(0,o.length-800))+"\ntl_len="+t.length;
try{reportResult(JSON.stringify({seq:88802,result:{ok:true,data:{output:msg}}}));}catch(e){}
})();
""",
    # TEST B1: switchC ping — full enterCommand return + baselines
    "test_sw_ping1!": r"""
(function(){
var d=null;try{d=ipc.network().getDevice("switchC");}catch(e){}
var cl=null;try{cl=d.getCommandLine();}catch(e){}
var tl=null;try{tl=d.getIpcTerminalLine();}catch(e){}
var base=-1;try{base=String(cl.getOutput()).length;}catch(e){}
try{d.skipBoot();}catch(e){}
try{d.enterCommand("enable","enable");}catch(e){}
var s="!none";
try{var o=d.enterCommand("ping 192.168.0.3","");s=JSON.stringify(o);}catch(e){s="EXC:"+e;}
var r=[];
r.push("base_cl_len="+base);
r.push("ping_ret="+s);
try{r.push("tl_mode="+String(tl.getMode()));}catch(e){r.push("tl_EXC:"+e);}
try{r.push("cl_mode="+String(cl.getMode()));}catch(e){}
var msg=r.join("\n");
try{reportResult(JSON.stringify({seq:88803,result:{ok:true,data:{output:msg}}}));}catch(e){}
})();
""",
    # TEST B2: switchC buffers 12s after the ping
    "test_sw_ping2!": r"""
(function(){
var d=null;try{d=ipc.network().getDevice("switchC");}catch(e){}
var cl=null;try{cl=d.getCommandLine();}catch(e){}
var tl=null;try{tl=d.getIpcTerminalLine();}catch(e){}
var o="";
try{o=String(cl.getOutput());}catch(e){o="EXC:"+e;}
var t="";
try{t=String(tl.getOutput());}catch(e){t="EXC:"+e;}
var msg="cl_len="+o.length+"\ncl_tail>>>\n"+o.substring(Math.max(0,o.length-800))+"\ntl_len="+t.length;
try{reportResult(JSON.stringify({seq:88804,result:{ok:true,data:{output:msg}}}));}catch(e){}
})();
""",
    # Dump the IPC TerminalLine content (async ping output candidate).
    # SAFE on switches (getIpcTerminalLine reads); DEADLY on PC-PT!
    "tl_dump": r"""
var d=null;try{d=ipc.network().getDevice("switchC");}catch(e){}
if(!d){__out="NO DEVICE";}else{
var t="";var m="";var p="";
try{t=String(d.getIpcTerminalLine().getOutput());}catch(e){t="EXC:"+e;}
try{m=String(d.getIpcTerminalLine().getMode());}catch(e){m="EXC:"+e;}
try{p=String(d.getIpcTerminalLine().getPrompt());}catch(e){p="EXC:"+e;}
__out="mode="+m+"\nprompt="+p+"\ntl_len="+t.length+"\nTL>>>\n"+t;}
""",
    # §MAC: discover the MAC-address getter on port objects.
    # Read-only: for-in key enumeration (same pattern as the "device"/"network"
    # probes, verified hang-free) + candidate getter calls, all try/caught.
    # No enterCommand / getCommandLine / getIpcTerminalLine anywhere (safety matrix).
    "mac_hunt": r"""
var __res=[];
var __dc=0;try{__dc=ipc.network().getDeviceCount();}catch(e){}
var __cands=["getMacAddress","getMac","getPhysicalAddress","getHardwareAddress","getBia","getMacAddr","getHwAddress"];
for(var i=0;i<__dc;i++){
var __d=null;try{__d=ipc.network().getDeviceAt(i);}catch(e){}
if(!__d){continue;}
var __dn="?";try{__dn=__d.getName();}catch(e){}
var __pc=0;try{__pc=__d.getPortCount();}catch(e){}
var __entry={device:__dn,portCount:__pc};
if(__pc>0){
var __p=null;try{__p=__d.getPortAt(0);}catch(e){}
if(__p){
var __nm="";try{__nm=__p.getName();}catch(e){}
__entry.portName=__nm;
var __ks=[];
try{for(var k in __p){__ks.push(k);}}catch(e){__ks.push("ENUM_EXC:"+String(e).substring(0,60));}
__entry.keys=__ks;
var __got={};
for(var c=0;c<__cands.length;c++){
var __v=null;
try{__v=__p[__cands[c]]();}catch(e){__v="EXC:"+String(e).substring(0,60);}
__got[__cands[c]]=__v;
}
__entry.macTry=__got;
}
}
__res.push(__entry);
}
__out=JSON.stringify({deviceCount:__dc,devices:__res});
""",
    # §7.5 step 1: tl_dump WITHOUT getPrompt() (prime hang suspect) and with a
    # 60s client timeout — isolates whether getOutput() on a NON-EMPTY tl
    # buffer blocks, or whether getPrompt() was the blocker.
    "tl_dump2": r"""
var d=null;try{d=ipc.network().getDevice("switchC");}catch(e){}
if(!d){__out="NO DEVICE";}else{
var t="";var m="";
try{m=String(d.getIpcTerminalLine().getMode());}catch(e){m="EXC:"+e;}
try{t=String(d.getIpcTerminalLine().getOutput());}catch(e){t="EXC:"+e;}
__out="mode="+m+"\ntl_len="+t.length+"\nTL>>>\n"+t;}
""",
}


def main() -> None:
    names = sys.argv[1:] or ["env"]
    for i, name in enumerate(names, start=1):
        raw_probe = name.endswith("!")
        js = PROBES.get(name)
        if js is None:
            print(f"[{name}] unknown probe")
            continue
        if raw_probe:
            js = js.replace('"REPLACE_OUT"', 'msg')
            raw = send_raw(js, timeout=45)
        else:
            raw = send_wrapped(js, seq=9000 + i,
                               timeout=60.0 if name == "tl_dump2" else 25.0)
        try:
            payload = json.loads(raw)
            result = payload.get("result", {})
            data = result.get("data")
            out = data.get("output") if isinstance(data, dict) else data
            if not result.get("ok", True):
                out = "PT-ERROR: " + str(result.get("error"))
        except Exception:
            out = raw
        print(f"=== {name} ===\n{out}\n")


if __name__ == "__main__":
    main()
