"""
Generates JavaScript code for execution via the PTBuilder extension.

PTBuilder (https://github.com/kimmknight/PTBuilder) provides a JS API
inside Packet Tracer for programmatic topology control.

All user-supplied strings are JSON-encoded before interpolation to prevent
JS injection.

Result reporting
----------------
The PT script engine has NO XMLHttpRequest/fetch. The only component with
network access is the hidden MCP Bridge webview (mcpbridge.html, installed
with Builder-MCP.pts) which polls GET /next. reportResult() — defined in
COMPAT_SHIM — injects an XHR POST into that webview via
`webview.evaluateJavaScriptAsync`, so every command can report its result
back to POST /result on the Python side.

Every command is additionally wrapped by wrap_with_result() in a try/catch
so PT-side errors are reported as data instead of reaching runCode()'s
modal error dialog (a modal popup freezes the webview polling loop).

NOTE: never use // comments in payload JS — some PTBuilder builds strip
newlines, which would swallow the rest of the line.
"""

import json
import re

# Local HTTP bridge port — single source of truth (pt_connection imports this).
BRIDGE_PORT = 54321

# Port name abbreviation → full name prefix
_PORT_PREFIXES = [
    (re.compile(r"^Gi(?=\d)"),   "GigabitEthernet"),
    (re.compile(r"^Fa(?=\d)"),   "FastEthernet"),
    (re.compile(r"^Se(?=\d)"),   "Serial"),
    (re.compile(r"^Et(?=\d)"),   "Ethernet"),
    (re.compile(r"^Te(?=\d)"),   "TenGigabitEthernet"),
]

# LogicalWorkspace IPC object, used by the delete/move primitives that
# PTBuilder does not expose as user functions.
_LW = "ipc.appWindow().getActiveWorkspace().getLogicalWorkspace()"


# Compat shim prepended to every script sent to PT.
#
# Some Packet Tracer builds do not expose device.skipBoot() (PC-PT and other
# device objects lack it), but PTBuilder's compiled addDevice / addModule call
# it unconditionally, raising "TypeError: Property 'skipBoot' of object
# [object Object] is not a function" and killing the polling loop. These shim
# re-implementations skip it. configureIosDevice additionally returns false
# when the device does not exist instead of throwing.
#
# reportResult() routes data back to the Python server through the hidden
# MCP Bridge webview (script engine has no XHR — see module docstring).
def _build_shim() -> str:
    core = (
        'var __ct={"1841":0,"1941":0,"2620XM":0,"2621XM":0,"2811":0,"2901":0,'
        '"2911":0,"ISR4321":0,"ISR4331":0,"Router-PT":0,"2950-24":1,"2950T-24":1,'
        '"2960-24TT":1,"Switch-PT":1,"3560-24PS":16,"3650-24PS":16,"IE-2000":16,'
        '"Cloud-PT":2,"Bridge-PT":3,"Hub-PT":4,"AccessPoint-PT":7,"PC-PT":8,'
        '"Server-PT":9,"Printer-PT":10,"Linksys-WRT300N":11,"7960":12,'
        '"Laptop-PT":18,"TabletPC-PT":19,"SMARTPHONE-PT":20,"TV-PT":23,'
        '"Home-VoIP-PT":24,"Analog-Phone-PT":25,"WLC-PT":41,"WLC-2504":41,'
        '"WLC-3504":41};'
        'addDevice=function(deviceName,deviceModel,x,y){var t=__ct[deviceModel];'
        'if(t===undefined){return false;}'
        'var on=ipc.appWindow().getActiveWorkspace().getLogicalWorkspace().'
        'addDevice(t,deviceModel,x,y);'
        'if(!on){return false;}'
        'ipc.network().getDevice(on).setName(deviceName);return true;};'
        'addModule=function(deviceName,slot,module){var d=ipc.network().'
        'getDevice(deviceName);var ps=d.getPower();d.setPower(false);'
        'var result=d.addModule(slot,module);if(ps){d.setPower(true);}return true;};'
        'configureIosDevice=function(deviceName,commands){var d=ipc.network().'
        'getDevice(deviceName);'
        'if(!d){return false;}'
        'var a=commands.split("\\n");'
        'd.enterCommand("!","global");'
        'for(var i=0;i<a.length;i++){d.enterCommand(a[i],"");}'
        'd.enterCommand("write memory","enable");return true;};'
    )
    report = (
        'reportResult=function(data){'
        'var wv=null;'
        'try{if(typeof mcpBridge!=="undefined"&&mcpBridge&&mcpBridge.webview){wv=mcpBridge.webview;}}catch(e){}'
        'if(!wv){try{if(typeof window!=="undefined"&&window&&window.webview){wv=window.webview;}}catch(e){}}'
        'if(!wv||typeof wv.evaluateJavaScriptAsync!=="function"){return false;}'
        'if(typeof data!=="string"){try{data=JSON.stringify(data);}catch(e){data=String(data);}}'
        # encodeURIComponent leaves "'" raw, and the payload is embedded in a
        # single-quoted JS string literal below — an apostrophe in any reported
        # text (device names, CLI output...) breaks the literal, PT shows
        # "SyntaxError: Parse error" and the polling webview freezes. Escape it.
        'var s=encodeURIComponent(data).replace(/\'/g,"%27");'
        'var js="var x=new XMLHttpRequest();x.open(\'POST\',\'http://127.0.0.1:'
        + str(BRIDGE_PORT) +
        '/result\',true);x.setRequestHeader(\'Content-Type\',\'text/plain\');'
        'x.send(decodeURIComponent(\'"+s+"\'));";'
        'try{wv.evaluateJavaScriptAsync(js);}catch(e){return false;}'
        'return true;};'
    )
    return core + report


COMPAT_SHIM = _build_shim()


def wrap_with_result(js_code: str, seq: int) -> str:
    """
    Wrap a command in an IIFE with try/catch and force a reportResult() call.

    On success the payload is {"seq": n, "result": {"ok": true, "data": __out}};
    on failure {"seq": n, "result": {"ok": false, "error": "..."}}. Commands
    communicate their return values by assigning to __out.
    """
    head = '(function(){\nvar __out;\nvar __res=null;\ntry{\n'
    tail = (
        '\n__res={ok:true,data:(typeof __out==="undefined")?null:__out};\n}'
        'catch(e){__res={ok:false,error:String(e)};}\n'
        'reportResult(JSON.stringify({seq:' + str(seq) + ',result:__res}));\n'
        '})();'
    )
    return head + js_code + tail


# Shared enterCommand-return normaliser. device.enterCommand() returns a
# {first, second} pair whose .second holds the console text (verified live,
# PT 8.x); plain strings/null are accepted too for forward compatibility.
_CTEXT_JS = (
    'function __ctext(v){'
    'if(v===undefined||v===null){return "";}'
    'if(typeof v==="string"){return v;}'
    'try{if(v&&typeof v.second==="string"){return v.second;}}catch(e){}'
    'try{var j=JSON.stringify(v);if(j&&j!=="{}"&&j!=="null"){return j;}}catch(e){}'
    'return String(v);}\n'
)

# Busy-wait spin: the PT script engine has no sleep, but Date works (§6.1).
# Used after mode-switching enterCommand() calls because the very first
# command issued right after a mode switch is otherwise swallowed.
_SPIN_JS = (
    'var __t=(new Date()).getTime();'
    'while((new Date()).getTime()-__t<{ms}){{}}\n'
)

def _spin(ms: int) -> str:
    return _SPIN_JS.format(ms=ms)


def _js(value: str) -> str:
    """Safely encode a Python string as a JS string literal."""
    return json.dumps(value)


def _expand_port(name: str) -> str:
    """Expand abbreviated port names: Gi0/0 → GigabitEthernet0/0, Fa0 → FastEthernet0."""
    for pattern, full in _PORT_PREFIXES:
        if pattern.match(name):
            return pattern.sub(full, name)
    return name


class ScriptBuilder:
    """
    Translates MCP tool arguments into PTBuilder JavaScript snippets.

    Each method returns a self-contained JS statement or block that
    can be sent to PT via PTConnection.send_script(). Every method
    reports failure by throwing inside the wrap_with_result() wrapper
    so the Python side sees a real error instead of a fake success.
    """

    # ------------------------------------------------------------------ #
    # Devices                                                               #
    # ------------------------------------------------------------------ #

    def add_device(self, name: str, device_type: str, x: int, y: int) -> str:
        """
        Add a device to the PT canvas.

        PTBuilder API: addDevice(name, type, x, y) — returns false on failure.
        """
        return (
            'if(addDevice(' + _js(name) + ', ' + _js(device_type) + ', '
            + str(int(x)) + ', ' + str(int(y)) + ')===false){'
            'throw new Error(' + _js(f"addDevice failed for '{name}' — unknown model '{device_type}' or invalid position") + ');} '
        )

    def remove_device(self, name: str) -> str:
        """
        Remove a device from the canvas.

        PTBuilder has no removeDevice() user function — use the IPC
        LogicalWorkspace.removeDevice(name) directly (verified PT 8.x API).
        """
        return (
            'var __dv=null;try{__dv=ipc.network().getDevice(' + _js(name) + ');}catch(e){}\n'
            'if(!__dv){throw new Error(' + _js(f"Device '{name}' not found in Packet Tracer") + ');}\n'
            + _LW + '.removeDevice(' + _js(name) + ');'
        )

    def move_device(self, name: str, x: int, y: int) -> str:
        """Move a device to a new canvas position (device.moveToLocation)."""
        return (
            'var __dv=null;try{__dv=ipc.network().getDevice(' + _js(name) + ');}catch(e){}\n'
            'if(!__dv){throw new Error(' + _js(f"Device '{name}' not found in Packet Tracer") + ');}\n'
            '__dv.moveToLocation(' + str(int(x)) + ', ' + str(int(y)) + ');'
        )

    # ------------------------------------------------------------------ #
    # Connections                                                           #
    # ------------------------------------------------------------------ #

    def add_link(
        self,
        device1: str,
        port1: str,
        device2: str,
        port2: str,
        cable_type: str,
    ) -> str:
        """
        Connect two devices with a cable.

        PTBuilder API: addLink(dev1, port1, dev2, port2, cableType)
        """
        port1 = _expand_port(port1)
        port2 = _expand_port(port2)
        return (
            'if(addLink(' + _js(device1) + ', ' + _js(port1) + ', '
            + _js(device2) + ', ' + _js(port2) + ', ' + _js(cable_type) + ')===false){'
            'throw new Error('
            + _js(f"addLink failed: {device1}:{port1} ↔ {device2}:{port2} ({cable_type}) — check device/port names") + ');} '
        )

    def remove_link(self, device: str, port: str) -> str:
        """
        Disconnect a cable from a port.

        PTBuilder has no removeLink() user function — use the IPC
        LogicalWorkspace.deleteLink(device, port) directly.
        """
        port = _expand_port(port)
        return (
            'var __dv=null;try{__dv=ipc.network().getDevice(' + _js(device) + ');}catch(e){}\n'
            'if(!__dv){throw new Error(' + _js(f"Device '{device}' not found in Packet Tracer") + ');}\n'
            + _LW + '.deleteLink(' + _js(device) + ', ' + _js(port) + ');'
        )

    # ------------------------------------------------------------------ #
    # Configuration (CLI)                                                  #
    # ------------------------------------------------------------------ #

    def configure_pc_ip(
        self, name: str, ip: str, mask: str, gateway: str, dns: str = "", dhcp: bool = False
    ) -> str:
        """PTBuilder: configurePcIp(deviceName, dhcpEnabled, ipaddress, subnetMask, defaultGateway, dnsServer)"""
        return (
            'var __dv=null;try{__dv=ipc.network().getDevice(' + _js(name) + ');}catch(e){}\n'
            'if(!__dv){throw new Error(' + _js(f"Device '{name}' not found in Packet Tracer") + ');}\n'
            'configurePcIp(' + _js(name) + ', ' + str(bool(dhcp)).lower() + ', '
            + _js(ip) + ', ' + _js(mask) + ', ' + _js(gateway) + ', ' + _js(dns) + ');'
        )

    # Mode-navigation commands handled by the payload itself (it forces
    # privileged-exec → global-config before running the user commands).
    CONFIG_SKIP_COMMANDS = {
        "enable", "conf t", "configure terminal", "end", "exit",
        "write memory", "wr",
    }

    def configure_device(self, name: str, commands: list[str]) -> str:
        """
        Configure an IOS device command-by-command, capturing every result.

        Replaces PTBuilder's configureIosDevice(): that swallows the first
        command issued right after its ("!","global") mode switch (verified:
        'hostname' never applied while every later command did — §5.4). This
        exec-style loop spins ~400ms after the mode switch, then runs each
        command via device.enterCommand(cmd, "") and collects its
        {first, second} return so the tool layer can report per-command
        success/failure instead of a fake blanket success.

        Note: unlike configureIosDevice this does NOT auto-append
        "write memory" — persisting is an explicit pt_save_config call.
        """
        skip = self.CONFIG_SKIP_COMMANDS
        filtered = [c.strip() for c in commands if c.strip().lower() not in skip]
        return (
            _CTEXT_JS
            + 'var __dv=null;try{__dv=ipc.network().getDevice(' + _js(name) + ');}catch(e){}\n'
            'if(!__dv){throw new Error(' + _js(f"Device '{name}' not found in Packet Tracer") + ');}\n'
            'try{__dv.skipBoot();}catch(e){}\n'
            '__dv.enterCommand("enable","enable");\n'
            '__dv.enterCommand("!","global");\n'
            + _spin(400)
            + 'var __cmds=' + json.dumps(filtered) + ';\n'
            'var __res=[];\n'
            'for(var i=0;i<__cmds.length;i++){'
            'var __o=null;'
            'try{__o=__dv.enterCommand(__cmds[i],"");}'
            'catch(e){__o={first:-1,second:"JS error: "+String(e)};}'
            '__res.push({cmd:__cmds[i],'
            'first:(__o&&typeof __o.first!=="undefined")?__o.first:null,'
            'out:__ctext(__o)});}\n'
            '__out={results:__res};'
        )

    def exec_cli(self, name: str, commands: list[str]) -> str:
        """
        Execute CLI commands and capture their output (read path).

        Two device families, detected inside the JS payload:

        - IOS (switches/routers): device.enterCommand(cmd, mode) returns a
          {first, second} pair whose .second holds the console text
          (verified live, PT 8.x). PC-PT device objects have NO enterCommand
          at all (TypeError — §八), so the IOS path only runs when
          getCommandPrompt() is unavailable.
        - PC-PT: device.getCommandPrompt() returns the Command-Prompt
          TerminalLine. enterCommand there takes a SINGLE argument, returns
          undefined, and the console text accumulates in getOutput()
          (verified live: ipconfig round-trip, §八). Each command's output is
          collected as the buffer delta after a short Date spin.
        """
        skip = {"enable"}
        cmds = [c.strip() for c in commands if c.strip().lower() not in skip]
        return (
            _CTEXT_JS
            + 'var __dv=null;try{__dv=ipc.network().getDevice(' + _js(name) + ');}catch(e){}\n'
            'if(!__dv){throw new Error(' + _js(f"Device '{name}' not found in Packet Tracer") + ');}\n'
            'var __cp=null;try{if(typeof __dv.getCommandPrompt==="function"){__cp=__dv.getCommandPrompt();}}catch(e){}\n'
            'var __cmds=' + json.dumps(cmds) + ';\n'
            'if(__cp){\n'
            # PC path: one-arg enterCommand; output lands in the buffer.
            'var __lines=[];\n'
            'for(var i=0;i<__cmds.length;i++){'
            'var __before="";try{__before=String(__cp.getOutput());}catch(e){}\n'
            'try{__cp.enterCommand(__cmds[i]);}catch(e){__lines.push("! error: "+String(e));continue;}\n'
            + _spin(500)
            + 'var __after="";try{__after=String(__cp.getOutput());}catch(e){}\n'
            'var __delta=(__after.length>=__before.length)?__after.substring(__before.length):__after;\n'
            '__lines.push(__delta);}\n'
            '__out={ok:true,output:__lines.join("\\n")};\n'
            '}else{\n'
            # IOS path: two-arg enterCommand, sync .second output.
            'try{__dv.skipBoot();}catch(e){}\n'
            '__dv.enterCommand("enable","enable");\n'
            'var __lines=[];\n'
            'for(var i=0;i<__cmds.length;i++){'
            'var __o=null;'
            'try{__o=__dv.enterCommand(__cmds[i],"");}catch(e){__o="! error: "+String(e);}'
            '__lines.push(__ctext(__o));}\n'
            '__out={ok:true,output:__lines.join("\\n")};\n'
            '}'
        )

    # Asynchronous CLI commands (ping / traceroute): PT runs them in the
    # background — their text never appears in the enterCommand() return,
    # only in a console buffer seconds later. The queue layer therefore runs
    # async_start(), sleeps, then async_collect(). See §八 for the full
    # investigation of where (and where not) that output can be found.

    def async_start(self, name: str, command: str) -> str:
        """Phase 1: fire an async CLI command on a PC or IOS device."""
        return (
            'var __dv=null;try{__dv=ipc.network().getDevice(' + _js(name) + ');}catch(e){}\n'
            'if(!__dv){throw new Error(' + _js(f"Device '{name}' not found in Packet Tracer") + ');}\n'
            'var __cp=null;try{if(typeof __dv.getCommandPrompt==="function"){__cp=__dv.getCommandPrompt();}}catch(e){}\n'
            'if(__cp){try{__cp.enterCommand(' + _js(command) + ');}catch(e){throw new Error("PC CLI failed: "+String(e));}}\n'
            'else{try{__dv.skipBoot();}catch(e){}\n'
            '__dv.enterCommand("enable","enable");\n'
            + _spin(400)
            + '__dv.enterCommand(' + _js(command) + ',"");}\n'
            '__out={ok:true,started:true};'
        )

    def async_collect(self, name: str, command: str, fallback_cmd: str = "") -> str:
        """Phase 2 (run after a settle delay): gather the command's output.

        PC: the Command-Prompt buffer holds the full transcript — extract
        everything from the last "<command>" echo onward.
        IOS: the async command text is NOT exposed by any script API on this
        build (getCommandLine buffer, getIpcTerminalLine, telnet sessions all
        checked — §八). When fallback_cmd is given (e.g. "show ip arp" after
        a ping) its synchronous output is returned as indirect evidence.
        """
        return (
            'var __dv=null;try{__dv=ipc.network().getDevice(' + _js(name) + ');}catch(e){}\n'
            'if(!__dv){throw new Error(' + _js(f"Device '{name}' not found in Packet Tracer") + ');}\n'
            'var __cp=null;try{if(typeof __dv.getCommandPrompt==="function"){__cp=__dv.getCommandPrompt();}}catch(e){}\n'
            'if(__cp){'
            'var __buf="";try{__buf=String(__cp.getOutput());}catch(e){__buf="";}\n'
            'var __anchor=__buf.lastIndexOf(' + _js(command) + ');\n'
            'var __txt=(__anchor>=0)?__buf.substring(__anchor):"(command output not found in buffer)";\n'
            '__out={ok:true,output:__txt,source:"pc-command-prompt-buffer"};\n'
            '}else{'
            'try{__dv.skipBoot();}catch(e){}\n'
            '__dv.enterCommand("enable","enable");\n'
            + _spin(400)
            + 'var __fb=' + _js(fallback_cmd) + ';\n'
            'var __txt="";\n'
            'if(__fb){__txt=__ctext(__dv.enterCommand(__fb,""));}\n'
            'else{__txt="(this PT build does not expose the async output of \'" + ' + _js(command) + ' + "\' for IOS devices)";}\n'
            '__out={ok:true,output:__txt,source:"ios-fallback"};\n'
            '}'
        )

    def save_device_config(self, name: str) -> str:
        """
        Issue 'write memory' from privileged exec and capture the result.

        Uses the same ("!","enable") + spin pattern as configure_device —
        enterCommand() with an explicit mode arg navigates the IOS session,
        so this is safe from any current CLI mode.
        """
        return (
            _CTEXT_JS
            + 'var __dv=null;try{__dv=ipc.network().getDevice(' + _js(name) + ');}catch(e){}\n'
            'if(!__dv){throw new Error(' + _js(f"Device '{name}' not found in Packet Tracer") + ');}\n'
            'try{__dv.skipBoot();}catch(e){}\n'
            '__dv.enterCommand("!","enable");\n'
            + _spin(400)
            + 'var __o=null;'
            'try{__o=__dv.enterCommand("write memory","");}'
            'catch(e){__o={first:-1,second:"JS error: "+String(e)};}\n'
            '__out={results:[{cmd:"write memory",'
            'first:(__o&&typeof __o.first!=="undefined")?__o.first:null,'
            'out:__ctext(__o)}]};'
        )

    # ------------------------------------------------------------------ #
    # Topology                                                             #
    # ------------------------------------------------------------------ #

    def clear_topology(self) -> str:
        """PTBuilder does not expose clearTopology — return no-op."""
        return "/* clearTopology not supported */"

    def get_topology(self) -> str:
        """
        Enumerate the full live topology and assign it to __out.

        Devices: ipc.network().getDeviceCount()/getDeviceAt() with getName(),
        getModel(), getType(), getXCoordinate()/getYCoordinate() (NOT getX()!),
        and per-port getName()/getLink()/getIpAddress().

        Links: ipc.network().getLinkCount()/getLinkAt() with getPort1()/
        getPort2(). Port objects carry no parent-device reference, so a
        port-UUID → (device, port) map is built first and link endpoints are
        resolved through it.
        """
        return (
            'var __byU={};\n'
            'var __devices=[];\n'
            'var __dc=ipc.network().getDeviceCount();\n'
            'for(var i=0;i<__dc;i++){\n'
            'var __d=null;try{__d=ipc.network().getDeviceAt(i);}catch(e){}\n'
            'if(!__d){continue;}\n'
            'var __ports=[];\n'
            'var __pc=0;try{__pc=__d.getPortCount();}catch(e){}\n'
            'for(var j=0;j<__pc;j++){\n'
            'var __p=null;try{__p=__d.getPortAt(j);}catch(e){}\n'
            'if(!__p){continue;}\n'
            'var __pu="";try{__pu=__p.getObjectUuid();}catch(e){}\n'
            'if(__pu){__byU[__pu]={d:__d.getName(),p:__p.getName()};}\n'
            'var __lk=false;try{__lk=!!__p.getLink();}catch(e){}\n'
            'var __ip="";try{__ip=__p.getIpAddress()||"";}catch(e){}\n'
            '__ports.push({name:__p.getName(),connected:__lk,ip:__ip});}\n'
            'var __x=0;var __y=0;try{__x=__d.getXCoordinate();__y=__d.getYCoordinate();}catch(e){}\n'
            'var __t=null;try{__t=__d.getType();}catch(e){}\n'
            '__devices.push({name:__d.getName(),type:__d.getModel(),categoryId:__t,x:__x,y:__y,ports:__ports});}\n'
            'var __links=[];\n'
            'var __lc=0;try{__lc=ipc.network().getLinkCount();}catch(e){}\n'
            'for(var k=0;k<__lc;k++){\n'
            'var __L=null;try{__L=ipc.network().getLinkAt(k);}catch(e){}\n'
            'if(!__L){continue;}\n'
            'var __q1=null;var __q2=null;try{__q1=__L.getPort1();__q2=__L.getPort2();}catch(e){}\n'
            'var __u1="";try{__u1=__q1.getObjectUuid();}catch(e){}\n'
            'var __u2="";try{__u2=__q2.getObjectUuid();}catch(e){}\n'
            'var __e1=__byU[__u1]||{d:"?",p:"?"};\n'
            'var __e2=__byU[__u2]||{d:"?",p:"?"};\n'
            '__links.push({device1:__e1.d,port1:__e1.p,device2:__e2.d,port2:__e2.p});}\n'
            '__out={devices:__devices,links:__links};'
        )

    # ------------------------------------------------------------------ #
    # Composite builders                                                   #
    # ------------------------------------------------------------------ #

    def build_topology(
        self,
        devices: list[dict],
        connections: list[dict],
    ) -> str:
        """
        Generate a full topology script from device and connection lists.

        devices: [{"name": str, "type": str, "x": int, "y": int}, ...]
        connections: [
            {
              "from_device": str, "from_port": str,
              "to_device": str,   "to_port": str,
              "cable": str
            }, ...
        ]
        """
        statements: list[str] = []

        for dev in devices:
            statements.append(
                self.add_device(dev["name"], dev["type"], dev.get("x", 100), dev.get("y", 100))
            )

        for conn in connections:
            cable_key = conn.get("cable", "straight")
            cable = self.resolve_cable_type(cable_key)
            statements.append(
                self.add_link(
                    conn["from_device"],
                    conn["from_port"],
                    conn["to_device"],
                    conn["to_port"],
                    cable,
                )
            )

        return "\n".join(statements)

    # ------------------------------------------------------------------ #
    # Cable type helpers                                                   #
    # ------------------------------------------------------------------ #

    # Maps our internal cable keys to the PTBuilder string PT expects
    # PTBuilder allLinkTypes keys (from links.js)
    CABLE_TYPE_MAP: dict[str, str] = {
        "auto":       "straight",
        "straight":   "straight",
        "crossover":  "cross",
        "cross":      "cross",
        "serial_dce": "serial",
        "serial_dte": "serial",
        "serial":     "serial",
        "console":    "console",
        "fiber":      "fiber",
        "usb":        "usb",
        "wireless":   "wireless",
        "coaxial":    "coaxial",
    }

    # Auto cable rules by device category pair
    _CABLE_RULES: dict[tuple[str, str], str] = {
        ("router",      "switch"):      "straight",
        ("switch",      "router"):      "straight",
        ("switch",      "pc"):          "straight",
        ("pc",          "switch"):      "straight",
        ("switch",      "server"):      "straight",
        ("server",      "switch"):      "straight",
        ("switch",      "laptop"):      "straight",
        ("laptop",      "switch"):      "straight",
        ("switch",      "accesspoint"): "straight",
        ("accesspoint", "switch"):      "straight",
        ("switch",      "phone"):       "straight",
        ("phone",       "switch"):      "straight",
        ("router",      "router"):      "cross",
        ("switch",      "switch"):      "cross",
        ("router",      "pc"):          "cross",
        ("pc",          "router"):      "cross",
        ("router",      "server"):      "cross",
        ("server",      "router"):      "cross",
        ("router",      "cloud"):       "straight",
        ("cloud",       "router"):      "straight",
    }

    @classmethod
    def resolve_cable_type(
        cls,
        cable_key: str,
        src_category: str = "",
        dst_category: str = "",
    ) -> str:
        if cable_key != "auto":
            return cls.CABLE_TYPE_MAP.get(cable_key, "straight")
        return cls._CABLE_RULES.get((src_category, dst_category), "straight")
