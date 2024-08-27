"""Nexia Themostat."""

from __future__ import annotations

import logging
import asyncio
from typing import TYPE_CHECKING, Any

from .const import AIR_CLEANER_MODES, BLOWER_OFF_STATUSES, HUMIDITY_MAX, HUMIDITY_MIN
from .util import find_dict_with_keyvalue_in_json, find_humidity_setpoint, is_number
from .zone import NexiaThermostatZone

_LOGGER = logging.getLogger(__name__)


if TYPE_CHECKING:
    from .home import NexiaHome


class NexiaThermostat:
    """A nexia Thermostat.

    Represents a nexia thermostat.
    """

    def __init__(self, nexia_home, thermostat_json):
        """Init nexia Thermostat."""
        self._nexia_home: NexiaHome = nexia_home
        self.thermostat_id: int = thermostat_json["id"]
        self._thermostat_json: dict[str, Any] = thermostat_json
        self.zones: list[NexiaThermostatZone] = []
        if self.has_zones():
            for zone in thermostat_json["zones"]:
                self.zones.append(NexiaThermostatZone(nexia_home, self, zone))

    @property
    def API_MOBILE_THERMOSTAT_URL(self):  # pylint: disable=invalid-name
        _url = (
            self._nexia_home.mobile_url + "/xxl_thermostats/{thermostat_id}/{end_point}"
        )

        return _url

    @property
    def is_online(self):
        """
        Returns whether the thermostat is online or not.
        :return: bool
        """
        return self.get_system_status().upper() != "NOT CONNECTED"

    def _get_thermostat_advanced_info_label(self, label):
        """
        Lookup advanced_info in the thermostat features and find the value of the
        requested label.
        """
        advanced_info = self._get_thermostat_features_key("advanced_info")

        try:
            return find_dict_with_keyvalue_in_json(
                advanced_info["items"], "label", label
            )["value"]
        except KeyError:
            return None

    def get_model(self):
        """
        Returns the thermostat model
        :return: string
        """
        return self._get_thermostat_advanced_info_label("Model")

    def get_firmware(self):
        """
        Returns the thermostat firmware version
        :return: string
        """
        return self._get_thermostat_advanced_info_label(
            "Firmware Version"
        ) or self._get_thermostat_advanced_info_label("Main Firmware Version")

    def get_dev_build_number(self):
        """
        Returns the thermostat development build number.
        :return: string
        """
        return self._get_thermostat_advanced_info_label(
            "Firmware Build Number"
        ) or self._get_thermostat_advanced_info_label("Version")

    def get_device_id(self):
        """
        Returns the device id
        :return: string
        """
        return self._get_thermostat_advanced_info_label("AUID")

    def get_type(self):
        """
        Returns the thermostat type, such as TraneXl1050
        :return: str
        """
        return self.get_model()

    def get_name(self):
        """
        Returns the name of the thermostat. This is not the zone name.
        :return: str
        """
        return self._get_thermostat_key("name")

    ########################################################################
    # Supported Features

    def has_outdoor_temperature(self):
        """
        Capability indication of whether the thermostat has an outdoor
        temperature sensor
        :return: bool
        """
        return self._get_thermostat_key_or_none("has_outdoor_temperature")

    def has_relative_humidity(self):
        """
        Capability indication of whether the thermostat has an relative
        humidity sensor
        :return: bool
        """
        return bool(self._get_thermostat_key_or_none("indoor_humidity"))

    def has_variable_speed_compressor(self):
        """
        Capability indication of whether the thermostat has a variable speed
        compressor
        :return: bool
        """
        # This only shows up if its running on mobile
        return True

    def has_emergency_heat(self):
        """
        Capability indication of whether the thermostat has emergency/aux heat.
        :return: bool
        """
        return bool(self.get_thermostat_settings_key_or_none("emergency_heat"))

    def has_variable_fan_speed(self):
        """
        Capability indication of whether the thermostat has a variable speed
        blower
        :return: bool
        """
        return bool(self.get_thermostat_settings_key_or_none("fan_speed"))

    def has_zones(self):
        """
        Indication of whether zoning is enabled or not on the thermostat.
        :return: bool
        """
        return bool(self._get_thermostat_key_or_none("zones"))

    def has_dehumidify_support(self):
        """
        Indiciation of whether dehumidifying support is available.
        :return: bool
        """
        return bool(self.get_thermostat_settings_key_or_none("dehumidify"))

    def has_humidify_support(self):
        """
        Indiciation of whether humidifying support is available.
        :return: bool
        """
        return bool(self.get_thermostat_settings_key_or_none("humidify"))

    ########################################################################
    # System Attributes

    def get_deadband(self):
        """
        Returns the deadband of the thermostat. This is the minimum number of
        degrees between the heat and cool setpoints in the number of degrees in
        the temperature unit selected by the
        thermostat.
        :return: int
        """
        return self._get_thermostat_features_key("thermostat")["setpoint_delta"]

    def get_setpoint_limits(self):
        """
        Returns a tuple of the minimum and maximum temperature that can be set
        on any zone. This is in the temperature unit selected by the
        thermostat.
        :return: (int, int)
        """
        return (
            self._get_thermostat_features_key("thermostat")["setpoint_heat_min"],
            self._get_thermostat_features_key("thermostat")["setpoint_cool_max"],
        )

    def get_variable_fan_speed_limits(self):
        """
        Returns the variable fan speed setpoint limits of the thermostat.
        :return: (float, float)
        """
        if self.has_variable_fan_speed():
            possible_values = self.get_thermostat_settings_key("fan_speed")["values"]
            return (possible_values[0], possible_values[-1])
        raise AttributeError("This thermostat does not support fan speeds")

    def get_unit(self):
        """
        Returns the temperature unit used by this system, either C or F.
        :return: str
        """
        return self._get_thermostat_features_key("thermostat")["scale"].upper()

    def get_humidity_setpoint_limits(self):
        """
        Returns the humidity setpoint limits of the thermostat.

        This is a hard-set limit in this code that I believe is universal to
        all TraneXl thermostats.
        but kept for consistency)
        :return: (float, float)
        """
        return HUMIDITY_MIN, HUMIDITY_MAX

    ########################################################################
    # System Universal Boolean Get Methods

    def is_blower_active(self):
        """
        Returns True if the blower is active
        :return: bool
        """
        return self.get_system_status() not in BLOWER_OFF_STATUSES

    def is_emergency_heat_active(self):
        """
        Returns True if the emergency/aux heat is active
        :return: bool
        """
        if self.has_emergency_heat():
            return self.get_thermostat_settings_key("emergency_heat")["current_value"]
        raise RuntimeError("This system does not support emergency heat")

    ########################################################################
    # System Universal Get Methods

    def get_fan_modes(self):
        """
        Returns the list of fan modes the device supports

        :return:
        """
        options = self.get_thermostat_settings_key("fan_mode")["options"]
        return [opt["label"] for opt in options]

    def get_fan_mode(self):
        """
        Returns the current fan mode. See get_fan_modes for the available options.
        :return: str
        """
        fan_mode = self.get_thermostat_settings_key("fan_mode")
        current_value = fan_mode["current_value"]
        options = fan_mode["options"]
        for opt in options:
            if opt["value"] == current_value:
                return opt["label"]
        return None

    def get_outdoor_temperature(self):
        """
        Returns the outdoor temperature.
        :return: float - the temperature, returns nan if invalid
        """
        if self.has_outdoor_temperature():
            outdoor_temp = self._get_thermostat_key("outdoor_temperature")
            if is_number(outdoor_temp):
                return float(outdoor_temp)
            return float("Nan")
        raise RuntimeError("This system does not have an outdoor temperature sensor")

    def get_relative_humidity(self):
        """
        Returns the indoor relative humidity as a percent (0-1)
        :return: float
        """
        if self.has_relative_humidity():
            try:
                return float(self._get_thermostat_key("indoor_humidity")) / 100
            except ValueError:
                # this has the value "--" when data is unavailable
                return None

        raise RuntimeError("This system does not have a relative humidity sensor.")

    def get_current_compressor_speed(self):
        """
        Returns the variable compressor speed, if supported, as a percent (0-1)
        :return: float
        """
        thermostat_compressor_speed = self._get_thermostat_features_key_or_none(
            "thermostat_compressor_speed"
        )
        if thermostat_compressor_speed is None:
            return 0
        return float(thermostat_compressor_speed["compressor_speed"])

    def get_requested_compressor_speed(self):
        """
        Returns the variable compressor's requested speed, if supported, as a
        percent (0-1)
        :return: float
        """
        # mobile api does not have a requested speed
        return self.get_current_compressor_speed()

    def get_fan_speed_setpoint(self):
        """
        Returns the current variable fan speed setpoint from 0-1.
        :return: float
        """
        if self.has_variable_fan_speed():
            return self.get_thermostat_settings_key("fan_speed")["current_value"]
        raise AttributeError("This system does not have variable fan speed.")

    def get_dehumidify_setpoint(self):
        """
        Returns the dehumidify setpoint from 0-1
        :return: float
        """
        if self.has_dehumidify_support():
            return self.get_thermostat_settings_key("dehumidify")["current_value"]

        raise AttributeError("This system does not support dehumidification")

    def get_humidify_setpoint(self):
        """
        Returns the dehumidify setpoint from 0-1
        :return: float
        """
        if self.has_humidify_support():
            return self.get_thermostat_settings_key("humidify")["current_value"]

        raise AttributeError("This system does not support humidification")

    def get_system_status(self):
        """
        Returns the system status such as "System Idle" or "Cooling"
        :return: str
        """
        return (
            self._get_thermostat_key_or_none("system_status")
            or self._get_thermostat_key_or_none("operating_state")
            or self._get_thermostat_features_key("thermostat")["status"]
        )

    def has_air_cleaner(self):
        """
        Returns if the system has an air cleaner.
        :return: bool
        """
        return bool(self.get_thermostat_settings_key_or_none("air_cleaner_mode"))

    def get_air_cleaner_mode(self):
        """
        Returns the system's air cleaner mode
        :return: str
        """
        _air_cleaner_mode = self.get_thermostat_settings_key_or_none("air_cleaner_mode")
        if _air_cleaner_mode == None:
            return AIR_CLEANER_MODES[0]
        else:
            return _air_cleaner_mode["current_value"]

    ########################################################################
    # System Universal Set Methods

    async def set_fan_mode(self, fan_mode: str):
        """
        Sets the fan mode.
        :param fan_mode: string that must be in self.get_fan_modes()
        :return: None
        """
        fan_mode_data = self.get_thermostat_settings_key("fan_mode")
        options = fan_mode_data["options"]
        for opt in options:
            if opt["label"] == fan_mode:
                fan_mode = opt["value"]
                break

        await self._post_and_update_thermostat_json("fan_mode", {"value": fan_mode})

    async def set_fan_setpoint(self, fan_setpoint: float):
        """
        Sets the fan's setpoint speed as a percent in range. You can see the
        limits by calling Nexia.get_variable_fan_speed_limits()
        :param fan_setpoint: float
        :return: None
        """

        # This call will get the limits, as well as check if this system has
        # a variable speed fan
        min_speed, max_speed = self.get_variable_fan_speed_limits()

        if min_speed <= fan_setpoint <= max_speed:
            await self._post_and_update_thermostat_json(
                "fan_speed", {"value": fan_setpoint}
            )
        else:
            raise ValueError(
                f"The fan setpoint, {fan_setpoint} is not "
                f"between {min_speed} and {max_speed}."
            )

    async def set_air_cleaner(self, air_cleaner_mode: str):
        """
        Sets the air cleaner mode.
        :param air_cleaner_mode: string that must be in
        AIR_CLEANER_MODES
        :return: None
        """
        air_cleaner_mode = air_cleaner_mode.lower()
        if air_cleaner_mode in AIR_CLEANER_MODES:
            if air_cleaner_mode != self.get_air_cleaner_mode():
                await self._post_and_update_thermostat_json(
                    "air_cleaner_mode", {"value": air_cleaner_mode}
                )
        else:
            raise KeyError("Invalid air cleaner mode specified")

    async def set_follow_schedule(self, follow_schedule):
        """
        Enables or disables scheduled operation
        :param follow_schedule: bool - True for follow schedule, False for hold
        current setpoints
        :return: None
        """
        await self._post_and_update_thermostat_json(
            "scheduling_enabled", {"value": "true" if follow_schedule else "false"}
        )

    async def set_emergency_heat(self, emergency_heat_on):
        """
        Enables or disables emergency / auxiliary heat.
        :param emergency_heat_on: bool - True for enabled, False for Disabled
        :return: None
        """
        if self.has_emergency_heat():
            await self._post_and_update_thermostat_json(
                "emergency_heat", {"value": "true" if emergency_heat_on else "false"}
            )
        else:
            raise RuntimeError("This thermostat does not support emergency heat.")

    async def set_humidity_setpoints(self, **kwargs):
        """

        :param dehumidify_setpoint: float - The dehumidify_setpoint, 0-1, disable: None
        :param humidify_setpoint: float - The humidify setpoint, 0-1, disable: None
        :return:
        """

        dehumidify_setpoint = kwargs.get("dehumidify_setpoint", None)
        humidify_setpoint = kwargs.get("humidify_setpoint", None)

        if dehumidify_setpoint is None and humidify_setpoint is None:
            # Do nothing
            return

        if not self.has_relative_humidity():
            raise RuntimeError(
                "Setting target humidity is not supported on this thermostat."
            )
        (min_humidity, max_humidity) = self.get_humidity_setpoint_limits()
        if self.has_humidify_support():
            humidify_supported = True
            if humidify_setpoint is None:
                humidify_setpoint = self.get_humidify_setpoint()
        else:
            if humidify_setpoint is not None:
                raise RuntimeError("This thermostat does not support humidifying.")
            humidify_supported = False
            humidify_setpoint = 0

        if self.has_dehumidify_support():
            dehumidify_supported = True
            if dehumidify_setpoint is None:
                dehumidify_setpoint = self.get_dehumidify_setpoint()
        else:
            if dehumidify_setpoint is not None:
                raise RuntimeError("This thermostat does not support dehumidifying.")
            dehumidify_supported = False
            dehumidify_setpoint = 0

        # Clean up input
        dehumidify_setpoint = find_humidity_setpoint(dehumidify_setpoint)
        humidify_setpoint = find_humidity_setpoint(humidify_setpoint)

        # Check inputs
        if (dehumidify_supported and humidify_supported) and not (
            min_humidity <= humidify_setpoint <= dehumidify_setpoint <= max_humidity
        ):
            raise ValueError(
                f"Setpoints must be between ({min_humidity} -"
                f" {max_humidity}) and humdiify_setpoint must"
                f" be <= dehumidify_setpoint"
            )
        if (dehumidify_supported) and not (
            min_humidity <= dehumidify_setpoint <= max_humidity
        ):
            raise ValueError(
                f"dehumidify_setpoint must be between "
                f"({min_humidity} - {max_humidity})"
            )
        if (humidify_supported) and not (
            min_humidity <= humidify_setpoint <= max_humidity
        ):
            raise ValueError(
                f"humidify_setpoint must be between "
                f"({min_humidity} - {max_humidity})"
            )

        if dehumidify_supported:
            await self._post_and_update_thermostat_json(
                "dehumidify", {"value": str(dehumidify_setpoint)}
            )
        if humidify_supported:
            await self._post_and_update_thermostat_json(
                "humidify", {"value": str(humidify_setpoint)}
            )

    async def set_dehumidify_setpoint(self, dehumidify_setpoint):
        """
        Sets the overall system's dehumidify setpoint as a percent (0-1).

        The system must support
        :param dehumidify_setpoint: float
        :return: None
        """
        await self.set_humidity_setpoints(dehumidify_setpoint=dehumidify_setpoint)

    async def set_humidify_setpoint(self, humidify_setpoint):
        """
        Sets the overall system's humidify setpoint as a percent (0-1).

        The system must support
        :param humidify_setpoint: float
        :return: None
        """
        await self.set_humidity_setpoints(humidify_setpoint=humidify_setpoint)

    ########################################################################
    # Zone Get Methods

    def get_zone_ids(self):
        """
        Returns a list of available zone IDs with a starting index of 0.
        :return: list(int)
        """
        # The zones are in a list, so there are no keys to pull out. I have to
        # create a new list of IDs.
        zone_list = []
        for zone in self.zones:
            zone_list.append(zone.zone_id)

        return zone_list

    def get_zone_by_id(self, zone_id):
        """Get a zone by its nexia id."""
        for zone in self.zones:
            if zone.zone_id == zone_id:
                return zone
        raise KeyError

    def _get_thermostat_deep_key(
        self, area: str, area_primary_key: str, key: str
    ) -> Any:
        """
        Returns the thermostat value from deep inside the thermostat's
        JSON.
        :param area: The area of the json to look i.e. "settings", "features", etc
        :param area_primary_key: The name of the primary key such as "name" or "key"
        :param key: str
        :return: value
        """
        data = find_dict_with_keyvalue_in_json(
            self._thermostat_json[area], area_primary_key, key
        )

        if not data:
            raise KeyError(f'Key "{key}" not in the thermostat JSON!')
        return data

    def _get_thermostat_features_key_or_none(self, key: str):
        """
        Returns the thermostat value from the provided key in the thermostat's
        JSON.
        :param key: str
        :return: value
        """
        try:
            return self._get_thermostat_features_key(key)
        except KeyError:
            return None

    def _get_thermostat_features_key(self, key: str):
        """
        Returns the thermostat value from the provided key in the thermostat's
        JSON.
        :param key: str
        :return: value
        """
        return self._get_thermostat_deep_key("features", "name", key)

    def _get_thermostat_key_or_none(self, key):
        """
        Returns the thermostat value from the provided key in the thermostat's
        JSON.
        :param key: str
        :return: value
        """
        return self._thermostat_json.get(key)

    def _get_thermostat_key(self, key):
        """
        Returns the thermostat value from the provided key in the thermostat's
        JSON.
        :param key: str
        :return: value
        """
        thermostat = self._thermostat_json
        if key in thermostat:
            return thermostat[key]

        raise KeyError(f'Key "{key}" not in the thermostat JSON ({thermostat}!')

    def get_thermostat_settings_key_or_none(self, key):
        """
        Returns the thermostat value from the provided key in the thermostat's
        JSON.
        :param key: str
        :return: value
        """
        try:
            return self.get_thermostat_settings_key(key)
        except KeyError:
            return None

    def get_thermostat_settings_key(self, key):
        """
        Returns the thermostat value from the provided key in the thermostat's
        JSON.
        :param key: str
        :return: value
        """
        return self._get_thermostat_deep_key("settings", "type", key)

    def _get_zone_json(self, zone_id=0):
        """
        Returns the thermostat zone's JSON
        :param zone_id: The index of the zone, defaults to 0.
        :return: dict(thermostat_json['zones'][zone_id])
        """
        thermostat = self._thermostat_json
        if not thermostat:
            return None

        zone = find_dict_with_keyvalue_in_json(thermostat["zones"], "id", zone_id)

        if not zone:
            raise IndexError(
                f"The zone_id ({zone_id}) does not exist in the thermostat zones."
            )
        return zone

    async def _post_and_update_thermostat_json(self, end_point, payload):
        url = self.API_MOBILE_THERMOSTAT_URL.format(
            end_point=end_point, thermostat_id=self._thermostat_json["id"]
        )

        """ Support for UX360 Thermostat """
        if self.get_model() == "TSYS2C60A2VVUEA":
            print(f"UX360 End Point      : {end_point}")
            if end_point == "fan_mode":  # update_thermostat_fan_mode
                url = self._get_thermostat_deep_key(
                    "features", "name", "thermostat_fan_mode"
                )["actions"]["update_thermostat_fan_mode"]["href"]

        response = await self._nexia_home.post_url(url, payload)
        response_json = (await response.json())["result"]

        """ Make sure that the data return is was is expected """
        if response_json.get("zones"):
            self.update_thermostat_json(response_json)
        else:
            """ Probably means a PUT request was used -- call update """
            await asyncio.sleep(10)
            await self._nexia_home.update()

    def update_thermostat_json(self, thermostat_json):
        """Update with new json from the api"""
        if self._thermostat_json is None:
            return

        _LOGGER.debug(
            "Updated thermostat_id:%s with new data from post",
            self.thermostat_id,
        )

        self._thermostat_json.update(thermostat_json)

        zone_updates_by_id = {}
        if thermostat_json.get("zones"):
            for zone_json in thermostat_json["zones"]:
                zone_updates_by_id[zone_json["id"]] = zone_json

            for zone in self.zones:
                if zone.zone_id in zone_updates_by_id:
                    zone.update_zone_json(zone_updates_by_id[zone.zone_id])

        else:
            """ Probably means a PUT request was used -- call update """
            print(thermostat_json)
