# Packet Tracer MCP Server

> ⚠️ **Beta** — Active development. Some features may be incomplete or change in future versions.

Control Cisco Packet Tracer in real time using natural language through Claude.

Write prompts like *"create a WAN network with OSPF between two sites"* and watch the topology build itself live inside Packet Tracer.

## How it works

```
You (Claude Desktop / Claude Code)
        │
        ▼  natural language prompt
  MCP Server (Python)  ← stdio transport
        │
        ▼  generates JavaScript (PTBuilder API)
  Local HTTP server :54321
        │
        ▼  PTBuilder webview polls /next every 500ms
  PTBuilder (extension running inside PT)
        │
        ▼  executes live
  Cisco Packet Tracer
```

## Requirements

- Python 3.11+
- Cisco Packet Tracer 8.x
- PTBuilder loaded in PT ([github.com/kimmknight/PTBuilder](https://github.com/kimmknight/PTBuilder))
- Claude Desktop or Claude Code

## Installation

```bash
git clone https://github.com/YOUR_USER/packet-tracer-mcp
cd packet-tracer-mcp
pip install -e .
```

## Configuration

Most AI coding tools run MCP servers as a subprocess via `stdio` — no extra setup, just point them at the command. Replace `C:/path/to/packet-tracer-mcp` with your actual path.

---

### Claude Code

```bash
cd C:/path/to/packet-tracer-mcp
claude mcp add packet-tracer -- python -m src.server
```

---

### Claude Desktop

```bash
# No CLI — edit the config file manually
# Windows: %APPDATA%\Claude\claude_desktop_config.json
# macOS:   ~/Library/Application Support/Claude/claude_desktop_config.json
```

```json
{
  "mcpServers": {
    "packet-tracer": {
      "command": "python",
      "args": ["-m", "src.server"],
      "cwd": "C:/path/to/packet-tracer-mcp"
    }
  }
}
```

---

### OpenCode

```bash
# No CLI — edit the config file manually
# Windows: %APPDATA%\opencode\config.json
# macOS/Linux: ~/.config/opencode/config.json
```

```json
{
  "mcp": {
    "packet-tracer": {
      "type": "local",
      "command": ["python", "-m", "src.server"],
      "cwd": "C:/path/to/packet-tracer-mcp"
    }
  }
}
```

---

### Cursor

```bash
# No CLI — edit the config file manually
# Project-level: .cursor/mcp.json
# Global: ~/.cursor/mcp.json
```

```json
{
  "mcpServers": {
    "packet-tracer": {
      "command": "python",
      "args": ["-m", "src.server"],
      "cwd": "C:/path/to/packet-tracer-mcp"
    }
  }
}
```

---

### Cline (VS Code)

```bash
# No CLI — use the UI
# Cline sidebar → Settings (⚙) → MCP Servers → Edit MCP Settings
```

```json
{
  "mcpServers": {
    "packet-tracer": {
      "command": "python",
      "args": ["-m", "src.server"],
      "cwd": "C:/path/to/packet-tracer-mcp"
    }
  }
}
```

---

### Continue

```bash
# No CLI — edit the config file manually
# ~/.continue/config.json
```

```json
{
  "experimental": {
    "modelContextProtocolServers": [
      {
        "transport": {
          "type": "stdio",
          "command": "python",
          "args": ["-m", "src.server"],
          "cwd": "C:/path/to/packet-tracer-mcp"
        }
      }
    ]
  }
}
```

---

### HTTP mode (advanced)

If you want the server running independently so multiple clients can share it, or if your client only supports HTTP/SSE:

```bash
python -m src.server --transport http --port 3000
# Server available at http://127.0.0.1:3000/sse
```

---

### Not on the list?

This server follows the [MCP specification](https://modelcontextprotocol.io) — it should work with any MCP-compatible client.

Check your client's documentation for how to add a `stdio` MCP server with a custom command. If you get it working with a client not listed here, feel free to **[open a PR or issue](../../issues)** to add it to this list.

## Packet Tracer setup (once per session)

Every time you open PT and Claude Code, activate the bridge:

**1.** In PT open **Extensions → Builder Code Editor**

**2.** Paste this script in the editor and click **Run**:

```javascript
window.webview.evaluateJavaScriptAsync("setInterval(function(){var x=new XMLHttpRequest();x.open('GET','http://127.0.0.1:54321/next',true);x.onload=function(){if(x.status===200&&x.responseText){$se('runCode',x.responseText)}};x.onerror=function(){};x.send()},500)");
```

**3.** Done. PTBuilder starts polling the MCP server and executes commands in real time.

> You only need to paste the bootstrap once per session. If you restart Claude Code, repeat this step.

## Usage

With PT open and the bridge active, write in Claude:

```
Create a network with router R1, switch SW1 and two PCs.
Connect them and configure the 192.168.1.0/24 network.
```

```
Add a DNS server with IP 192.168.1.10 connected to the switch.
Configure all PCs to use that DNS server.
```

```
Create a WAN topology: two routers with a serial link, each with
its own LAN, and configure OSPF area 0 between them.
```

## Available tools

### Devices
| Tool | Description |
|------|-------------|
| `pt_add_device` | Add a device to the canvas |
| `pt_list_devices` | List devices in the topology |
| `pt_get_device_info` | Get detailed info about a device |

### Connections
| Tool | Description |
|------|-------------|
| `pt_connect` | Connect two devices with a cable |
| `pt_disconnect` | Remove a cable from a port |
| `pt_list_connections` | List all connections |

### Configuration
| Tool | Description |
|------|-------------|
| `pt_send_commands` | Send CLI commands to a router/switch |
| `pt_configure_ip` | Configure IP on an interface (shortcut) |
| `pt_configure_pc` | Configure IP/DNS on a PC, Laptop or Server |
| `pt_save_config` | Save running-config to startup-config |

### Topology
| Tool | Description |
|------|-------------|
| `pt_apply_template` | Apply a predefined topology template |
| `pt_export_topology` | Export topology as JSON |
| `pt_validate` | Validate network configuration |

## Device aliases

| Alias | Model |
|-------|-------|
| `router` | Cisco 2911 |
| `switch` | Cisco 2960-24TT |
| `switch-l3` | Cisco 3560-24PS |
| `pc` | PC-PT |
| `server` | Server-PT |
| `laptop` | Laptop-PT |
| `phone` | Cisco 7960 |
| `ap` | AccessPoint-PT |
| `firewall` | ASA5506 |
| `cloud` | Cloud-PT |

## Project structure

```
packet-tracer-mcp/
├── src/
│   ├── server.py              # MCP entry point + resources
│   ├── app.py                 # FastMCP instance + lifespan
│   ├── tools/
│   │   ├── devices.py         # Device tools
│   │   ├── connections.py     # Connection tools
│   │   ├── configuration.py   # CLI configuration tools
│   │   └── topology.py        # Topology and diagnostics
│   ├── bridge/
│   │   ├── pt_connection.py   # HTTP bridge server :54321
│   │   ├── script_builder.py  # PTBuilder JS code generator
│   │   └── command_queue.py   # Serialized async queue
│   └── catalog/
│       ├── devices.json        # Device catalog
│       ├── cables.json         # Cable types
│       └── templates.json      # Topology templates
├── pt_mcp_bridge.js            # Bootstrap script for PTBuilder
├── pyproject.toml
└── LICENSE
```

## Troubleshooting

**"PTBuilder is not polling"**
- Make sure you pasted the bootstrap script in the Builder Code Editor and clicked Run
- If you restarted Claude Code, paste the bootstrap again
- Verify PTBuilder is loaded: Extensions → Configure PT Extension Modules

**Error "Invalid arguments for IPC call"**
- Check the device type is valid (use the aliases from the table above)
- Make sure port names match the model (e.g. Gi0/0 on 2911, Fa0/1 on 2960)

**Error "getPort of null"**
- The device was not added successfully before trying to configure it
- Verify `pt_add_device` succeeded before calling `pt_configure_pc`

## License

MIT
