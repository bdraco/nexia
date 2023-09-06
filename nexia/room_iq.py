"""Nexia Thermostat Room IQ Sensor."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .home import NexiaHome
    from .thermostat import NexiaThermostat


class NexiaThermostatRoomIq:
    """A nexia thermostat room IQ sensor."""

    def __init__(self, nexia_home, nexia_thermostat, iq_json):
        """Create a nexia room IQ sensor."""
        self._nexia_home: NexiaHome = nexia_home
        self._iq_json: dict[str, Any] = iq_json
        self.thermostat: NexiaThermostat = nexia_thermostat
        self.iq_id: int = iq_json["id"]

    def get_name(self) -> str:
        """
        Returns the Room IQ name
        :return: str
        """
        return str(self._get_iq_key("name"))

    def get_weight(self) -> float:
        """
        Returns the weight of this sensor.
        :return: float
        """
        return self._get_iq_key("weight")

    def get_temperature(self) -> int:
        """
        Returns the temperature reported by this sensor.
        :return: int
        """
        return self._get_conditional_value("temperature_valid", "temperature")

    def get_humidity(self) -> int:
        """
        Returns the humidity reported by this sensor.
        :return: int
        """
        return self._get_conditional_value("humidity_valid", "humidity")

    def get_battery_level(self) -> int:
        """
        Returns the battery level reported by this sensor.
        :return: int
        """
        return self._get_conditional_value("battery_valid", "battery_level")

    def _get_conditional_value(self, valid_key_name, key_name) -> Any:
        is_valid = self._get_iq_key_or_none(valid_key_name)
        if bool(is_valid):
            return self._get_iq_key(key_name)
        else:
            None

    def _get_iq_key(self, key: str) -> Any:
        if key in self._iq_json:
            return self._iq_json[key]

        raise KeyError(f'IQ key "{key}" invalid.')

    def _get_iq_key_or_none(self, key) -> Any:
        try:
            return self._get_iq_key(key)
        except KeyError:
            return None
