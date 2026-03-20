"""
Generates JavaScript code for execution via the PTBuilder extension.

PTBuilder (https://github.com/kimmknight/PTBuilder) provides a JS API
inside Packet Tracer for programmatic topology control.

All user-supplied strings are JSON-encoded before interpolation to prevent
JS injection.
"""

import json


def _js(value: str) -> str:
    """Safely encode a Python string as a JS string literal."""
    return json.dumps(value)


class ScriptBuilder:
    """
    Translates MCP tool arguments into PTBuilder JavaScript snippets.

    Each method returns a self-contained JS statement or block that
    can be sent to PT via PTConnection.send_script().
    """

    # ------------------------------------------------------------------ #
    # Devices                                                               #
    # ------------------------------------------------------------------ #

    def add_device(self, name: str, device_type: str, x: int, y: int) -> str:
        """
        Add a device to the PT canvas.

        PTBuilder API: addDevice(name, type, x, y)
        """
        return (
            f"addDevice({_js(name)}, {_js(device_type)}, {int(x)}, {int(y)});"
        )

    def remove_device(self, name: str) -> str:
        """
        Remove a device from the canvas.

        PTBuilder API: removeDevice(name)
        """
        return f"removeDevice({_js(name)});"

    def move_device(self, name: str, x: int, y: int) -> str:
        """Move a device to a new canvas position."""
        return f"moveDevice({_js(name)}, {int(x)}, {int(y)});"

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
        return (
            f"addLink({_js(device1)}, {_js(port1)}, "
            f"{_js(device2)}, {_js(port2)}, {_js(cable_type)});"
        )

    def remove_link(self, device: str, port: str) -> str:
        """
        Disconnect a cable from a port.

        PTBuilder API: removeLink(device, port)
        """
        return f"removeLink({_js(device)}, {_js(port)});"

    # ------------------------------------------------------------------ #
    # Configuration (CLI)                                                  #
    # ------------------------------------------------------------------ #

    def configure_pc_ip(
        self, name: str, ip: str, mask: str, gateway: str, dns: str = "", dhcp: bool = False
    ) -> str:
        """PTBuilder: configurePcIp(deviceName, dhcpEnabled, ipaddress, subnetMask, defaultGateway, dnsServer)"""
        return (
            f"configurePcIp({_js(name)}, {str(dhcp).lower()}, "
            f"{_js(ip)}, {_js(mask)}, {_js(gateway)}, {_js(dns)});"
        )

    def configure_device(self, name: str, commands: list[str]) -> str:
        """PTBuilder API: configureIosDevice(name, commands) — newline-separated CLI."""
        skip = {"enable", "conf t", "configure terminal", "end", "exit", "write memory", "wr"}
        filtered = [c.strip() for c in commands if c.strip().lower() not in skip]
        return f"configureIosDevice({_js(name)}, {_js(chr(10).join(filtered))});"

    def save_device_config(self, name: str) -> str:
        """Issue 'copy run start' to persist config."""
        return self.configure_device(name, ["copy running-config startup-config"])

    # ------------------------------------------------------------------ #
    # Topology                                                             #
    # ------------------------------------------------------------------ #

    def clear_topology(self) -> str:
        """PTBuilder does not expose clearTopology — return no-op."""
        return "/* clearTopology not supported */"

    def get_topology(self) -> str:
        """Return a JSON string of the current topology state."""
        return "JSON.stringify(getTopology());"

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
            statements.append(
                self.add_link(
                    conn["from_device"],
                    conn["from_port"],
                    conn["to_device"],
                    conn["to_port"],
                    conn.get("cable", "Copper Straight-Through"),
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
