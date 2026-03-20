# Packet Tracer MCP Server

Control Cisco Packet Tracer in real time using natural language through Claude.

Write prompts like *"create a WAN network with OSPF between two sites"* and watch
the topology build itself live inside Packet Tracer.

## How it works

```
You (Claude Desktop/Code)
        │
        ▼  natural language prompt
  MCP Server (Python)
        │
        ▼  generates JavaScript
  PTBuilder Extension (inside PT)
        │
        ▼  executes live
  Packet Tracer (topology updates in real time)
```

## Prerequisites

- Python 3.11+
- Cisco Packet Tracer 8.x (with IPC enabled)
- PTBuilder extension installed in PT
- Claude Desktop or Claude Code

## Installation

### 1. Install the MCP server

```bash
cd packet-tracer-mcp
pip install -e .
```

Or with `uv`:

```bash
uv pip install -e .
```

### 2. Enable IPC in Packet Tracer

1. Open Packet Tracer
2. Go to **Extensions → IPC → Options**
3. Check **"Always Listen On Start"**
4. Set port to `39000` (default)
5. Restart Packet Tracer

### 3. Install PTBuilder extension

PTBuilder is a JavaScript extension that lets the MCP server inject devices
and connections into Packet Tracer programmatically.

1. Download PTBuilder from https://github.com/kimmknight/PTBuilder
2. In Packet Tracer, go to **Extensions → PT Activity Wizard**
3. Load the PTBuilder JavaScript files as an extension
4. Verify it loads without errors in the PT console

### 4. Configure Claude Desktop

Add to your `claude_desktop_config.json`:

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

The config file is located at:
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`

### 5. Configure Claude Code

Run from the project root:

```bash
claude mcp add packet-tracer -- python -m src.server
```

Or add to your `.claude/settings.json`:

```json
{
  "mcpServers": {
    "packet-tracer": {
      "command": "python",
      "args": ["-m", "src.server"],
      "cwd": "/path/to/packet-tracer-mcp"
    }
  }
}
```

## Usage

With Packet Tracer open and IPC enabled, ask Claude:

### Build topologies from scratch

> "Create a simple LAN with a router, switch, and 3 PCs. Use the 192.168.1.0/24 network."

> "Build a WAN network with two sites connected via serial and configure OSPF."

> "Set up a DMZ network with a firewall, web server, and internal LAN."

### Use templates

> "Apply the simple_lan template with 5 PCs"

> "Apply the wan_two_sites template with EIGRP routing"

### Configure devices

> "Configure IP 10.0.0.1/30 on R1's Serial0/0/0 interface"

> "Set up OSPF area 0 on R1 to advertise all directly connected networks"

> "Create VLANs 10 (Sales), 20 (Engineering), and 30 (Management) on Switch1"

### Diagnose connectivity

> "Ping from PC1 to the default gateway"

> "Show the routing table on R1"

> "Run traceroute from PC1 to 192.168.2.10"

## Available tools

### Devices

| Tool | Description |
|------|-------------|
| `pt_add_device` | Add a device to the canvas |
| `pt_remove_device` | Remove a device |
| `pt_list_devices` | List all devices in the topology |
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
| `pt_send_commands` | Send CLI commands to a device |
| `pt_configure_ip` | Configure IP on an interface (shortcut) |
| `pt_get_running_config` | Get running configuration |
| `pt_save_config` | Save running config to startup |

### Topology

| Tool | Description |
|------|-------------|
| `pt_clear_topology` | Clear all devices and connections |
| `pt_list_templates` | List available templates |
| `pt_apply_template` | Apply a predefined topology template |
| `pt_export_topology` | Export topology as JSON |
| `pt_validate` | Check topology for issues |

### Diagnostics

| Tool | Description |
|------|-------------|
| `pt_ping` | Execute ping from a device |
| `pt_traceroute` | Execute traceroute from a device |
| `pt_show_interfaces` | Show interface status |

## Device aliases

You can use short names instead of model numbers:

| Alias | Resolves to |
|-------|-------------|
| `router` | Cisco 2911 |
| `switch` | Cisco 2960-24TT |
| `pc` | PC-PT |
| `server` | Server-PT |
| `laptop` | Laptop-PT |
| `ap` | AccessPoint-PT |
| `wifi` | Linksys WRT300N |

## Cable auto-selection

When `cable_type="auto"` (the default), the correct cable is selected automatically:

- **Same device type** (switch↔switch, router↔router) → Crossover
- **Different types** (router↔switch, PC↔switch) → Straight-through
- **Serial ports** → Serial DCE

## Available resources

Resources provide catalog data to Claude:

| URI | Contents |
|-----|----------|
| `pt://catalog/devices` | All device models and their ports |
| `pt://catalog/cables` | Cable types and auto-selection rules |
| `pt://catalog/templates` | Template definitions |
| `pt://topology/current` | Live topology state from PT |

## Running tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

Tests run without Packet Tracer — they use mocked connections.

## Troubleshooting

### "Not connected to Packet Tracer"

- Verify PT is open
- Check IPC is enabled: **Extensions → IPC → Options → Always Listen On Start**
- Confirm the port is 39000 (or update `PTConnection` default)
- Check firewall is not blocking localhost:39000

### "PTBuilder function not found"

- Verify PTBuilder extension is loaded in PT
- Check the PT console (Extensions → Script Console) for JS errors
- Try running `addDevice("test", "PC-PT", 100, 100);` manually in the console

### Server not appearing in Claude

- Verify the path in `cwd` is correct and uses forward slashes or escaped backslashes
- Run `python -m src.server` manually to check for import errors
- Check Claude Desktop logs: **Help → Open Logs Folder**

### Commands not executing

- Some PT versions have different CLI command syntax
- Try `pt_get_running_config` first to verify CLI access works
- Check the PT IPC docs for your version's supported commands

## Project structure

```
packet-tracer-mcp/
├── src/
│   ├── app.py              # FastMCP instance + lifespan
│   ├── server.py           # Resources + entry point
│   ├── tools/
│   │   ├── devices.py      # Device tools
│   │   ├── connections.py  # Connection tools
│   │   ├── configuration.py # CLI config tools
│   │   └── topology.py     # Topology + diagnostic tools
│   ├── bridge/
│   │   ├── pt_connection.py  # TCP IPC bridge
│   │   ├── script_builder.py # JS code generator
│   │   └── command_queue.py  # Serialised async queue
│   ├── catalog/
│   │   ├── devices.json    # Device catalog
│   │   ├── cables.json     # Cable types
│   │   └── templates.json  # Topology templates
│   └── models/             # Pydantic models
├── tests/
├── examples/
└── pyproject.toml
```

## License

MIT
