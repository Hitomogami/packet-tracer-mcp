from enum import Enum
from pydantic import BaseModel, Field


class CableType(str, Enum):
    AUTO = "auto"
    STRAIGHT = "straight"
    CROSSOVER = "crossover"
    SERIAL_DCE = "serial_dce"
    SERIAL_DTE = "serial_dte"
    CONSOLE = "console"
    FIBER = "fiber"
    USB = "usb"


class Connection(BaseModel):
    device1: str = Field(description="Name of the first device")
    port1: str = Field(description="Port name on the first device")
    device2: str = Field(description="Name of the second device")
    port2: str = Field(description="Port name on the second device")
    cable_type: CableType = Field(default=CableType.AUTO, description="Cable type used")

    def __str__(self) -> str:
        return f"{self.device1}:{self.port1} <--{self.cable_type.value}--> {self.device2}:{self.port2}"
