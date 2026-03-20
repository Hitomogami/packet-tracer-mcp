from enum import Enum
from pydantic import BaseModel, Field


class DeviceCategory(str, Enum):
    ROUTER = "router"
    SWITCH = "switch"
    END_DEVICE = "end_device"
    WIRELESS = "wireless"


class DevicePort(BaseModel):
    name: str
    connected: bool = False
    connected_to_device: str | None = None
    connected_to_port: str | None = None


class Device(BaseModel):
    name: str = Field(description="Unique label in the topology canvas")
    device_type: str = Field(description="PT device model (e.g. '2911', '2960-24TT', 'PC-PT')")
    category: DeviceCategory = Field(description="Device category")
    x: int = Field(default=100, description="Canvas X position in pixels")
    y: int = Field(default=100, description="Canvas Y position in pixels")
    ports: list[DevicePort] = Field(default_factory=list, description="Available ports")

    def get_available_ports(self) -> list[str]:
        return [p.name for p in self.ports if not p.connected]

    def get_port(self, port_name: str) -> DevicePort | None:
        for port in self.ports:
            if port.name == port_name:
                return port
        return None
