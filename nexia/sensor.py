"""Nexia Thermostat Sensor."""

from __future__ import annotations

import dataclasses
from typing import Any


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
    connected: bool | None
    has_battery: bool
    battery_level: int | None
    battery_low: bool | None
    battery_valid: bool | None

    @classmethod
    def from_json(cls, sensor_json: dict[str, Any]) -> NexiaSensor:
        """Factory method for json data.
        :param sensor_json: json dict with some or all of our fields
        :return: a NexiaSensor instance
        """
        return cls(
            *[sensor_json.get(fld.name) for fld in dataclasses.fields(NexiaSensor)]  # type: ignore[arg-type]
        )
