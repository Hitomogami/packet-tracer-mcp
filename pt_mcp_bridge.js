// ============================================================
// MCP Bridge for Packet Tracer
// ============================================================
// Paste this entire script into PTBuilder's Debug console and press Enter.
// It starts a polling loop that reads commands written by the MCP server
// and executes them using PTBuilder's API.
//
// Files used:
//   C:\temp\pt_cmd.json   — Python writes commands here
//   C:\temp\pt_resp.json  — PT writes responses here
// ============================================================

var MCP_CMD_FILE  = "C:\\temp\\pt_cmd.json";
var MCP_RESP_FILE = "C:\\temp\\pt_resp.json";
var MCP_POLL_MS   = 150;

function mcpExec(cmd) {
    var action = cmd.action;
    try {
        if (action === "addDevice") {
            addDevice(cmd.name, cmd.type, cmd.x || 200, cmd.y || 200);
            return { status: "ok", result: "Added " + cmd.name };

        } else if (action === "addLink") {
            addLink(cmd.device1, cmd.port1, cmd.device2, cmd.port2,
                    cmd.cable || "Copper Straight-Through");
            return { status: "ok", result: "Linked " + cmd.device1 + " <-> " + cmd.device2 };

        } else if (action === "addModule") {
            addModule(cmd.device, cmd.slot, cmd.module);
            return { status: "ok", result: "Module added" };

        } else if (action === "configureIosDevice") {
            configureIosDevice(cmd.name, cmd.commands);
            return { status: "ok", result: "Configured " + cmd.name };

        } else if (action === "configurePcIp") {
            configurePcIp(cmd.name, cmd.dhcp || false,
                          cmd.ip || "", cmd.mask || "", cmd.gateway || "");
            return { status: "ok", result: "IP set on " + cmd.name };

        } else if (action === "getDevices") {
            var devs = getDevices(cmd.types || []);
            return { status: "ok", result: JSON.stringify(devs) };

        } else if (action === "ping") {
            return { status: "ok", result: "pong" };

        } else {
            return { status: "error", result: "Unknown action: " + action };
        }
    } catch (e) {
        return { status: "error", result: "" + e };
    }
}

function mcpPoll() {
    var raw = "";
    try { raw = _ScriptModule.getFileContents(MCP_CMD_FILE); } catch(e) { return; }

    if (!raw || raw.length < 3) return;   // empty or no file

    var cmd;
    try { cmd = JSON.parse(raw); } catch(e) {
        _ScriptModule.writeTextToFile(MCP_RESP_FILE,
            JSON.stringify({ status: "error", result: "Bad JSON: " + e }));
        _ScriptModule.writeTextToFile(MCP_CMD_FILE, "");
        return;
    }

    // Clear command file BEFORE executing so Python can pipeline next command
    _ScriptModule.writeTextToFile(MCP_CMD_FILE, "");

    var resp = mcpExec(cmd);
    resp.id = cmd.id || 0;
    _ScriptModule.writeTextToFile(MCP_RESP_FILE, JSON.stringify(resp));
}

// Stop any previous bridge interval
if (typeof _mcpInterval !== "undefined") {
    try { _ScriptModule.clearInterval(_mcpInterval); } catch(e) {}
}
var _mcpInterval = _ScriptModule.setInterval(mcpPoll, MCP_POLL_MS);
console.log("[MCP Bridge] Started — polling every " + MCP_POLL_MS + "ms");
console.log("[MCP Bridge] Waiting for commands in " + MCP_CMD_FILE);
