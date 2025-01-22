"""Nexia Thermostat Sensor."""

import dataclasses
from typing import Optional, TypeVar


@dataclasses.dataclass
class NexiaSensor:
    """Data object representing details of a nexia sensor"""

    id: int
    name: str
    type: str
    serial_number: str
    weight: float
    temperature: int
    temperature_valid: bool
    humidity: int
    humidity_valid: bool
    has_online: bool
    connected: Optional[bool]
    has_battery: bool
    battery_level: Optional[int]
    battery_low: Optional[bool]
    battery_valid: Optional[bool]

    T = TypeVar("T", bound="NexiaSensor")

    @classmethod
    def from_json(cls: type[T], sensor_json) -> T:
        """Factory method for json data.
        :param sensor_json: json dict with some or all of our fields
        :return: a NexiaSensor instance
        """
        return cls(
            *[sensor_json.get(fld.name) for fld in dataclasses.fields(NexiaSensor)]
        )
