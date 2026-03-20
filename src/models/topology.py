from enum import Enum
from pydantic import BaseModel, Field

from .device import Device
from .connection import Connection


class TopologyState(str, Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    UNKNOWN = "unknown"


class Topology(BaseModel):
    state: TopologyState = Field(default=TopologyState.UNKNOWN)
    devices: list[Device] = Field(default_factory=list)
    connections: list[Connection] = Field(default_factory=list)

    def get_device(self, name: str) -> Device | None:
        for device in self.devices:
            if device.name == name:
                return device
        return None

    def device_names(self) -> list[str]:
        return [d.name for d in self.devices]

    def summary(self) -> str:
        return (
            f"Topology: {len(self.devices)} devices, "
            f"{len(self.connections)} connections [{self.state.value}]"
        )
