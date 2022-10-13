"""Nexia Themostat Zone."""
from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING, Any

from .const import (
    DAMPER_CLOSED,
    HOLD_PERMANENT,
    OPERATION_MODE_COOL,
    OPERATION_MODE_HEAT,
    OPERATION_MODE_OFF,
    OPERATION_MODES,
    PRESET_MODE_NONE,
    SYSTEM_STATUS_IDLE,
    UNIT_CELSIUS,
    ZONE_IDLE,
)
from .util import find_dict_with_keyvalue_in_json

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .home import NexiaHome
    from .thermostat import NexiaThermostat


class NexiaThermostatZone:
    """A nexia thermostat zone."""

    def __init__(self, nexia_home, nexia_thermostat, zone_json):
        """Create a nexia zone."""
        self._nexia_home: NexiaHome = nexia_home
        self._zone_json: dict[str, Any] = zone_json
        self.thermostat: NexiaThermostat = nexia_thermostat
        self.zone_id: int = zone_json["id"]

    @property
    def API_MOBILE_ZONE_URL(self) -> str:  # pylint: disable=invalid-name
        return self._nexia_home.mobile_url + "/xxl_zones/{zone_id}/{end_point}"

    def get_name(self) -> str:
        """
        Returns the zone name
        :return: str
        """
        if self.is_native_zone():
            return f"{self.thermostat.get_name()} NativeZone"

        return str(self._get_zone_key("name"))

    def get_cooling_setpoint(self) -> int:
        """
        Returns the cooling setpoint in the temperature unit of the thermostat
        :return: int
        """
        return self._get_zone_key("setpoints")["cool"]

    def get_heating_setpoint(self) -> int:
        """
        Returns the heating setpoint in the temperature unit of the thermostat
        :return: int
        """
        return self._get_zone_key("setpoints")["heat"]

    def get_current_mode(self) -> str:
        """
        Returns the current mode of the zone. This may not match the requested
        mode

        :return: str
        """
        return self._get_zone_setting("zone_mode")["current_value"].upper()

    def get_requested_mode(self) -> str:
        """
        Returns the requested mode of the zone. This should match the zone's
        mode on the thermostat.
        Available options can be found in NexiaThermostat.OPERATION_MODES
        :return: str
        """
        return self._get_zone_features("thermostat_mode")["value"].upper()

    def get_temperature(self) -> int:
        """
        Returns the temperature of the zone in the temperature unit of the
        thermostat.
        :return: int
        """
        return self._get_zone_key("temperature")

    def get_presets(self) -> list[str]:
        """
        Supposed to return the zone presets. For some reason, most of the time,
        my unit only returns "AWAY", but I can set the other modes. There is
        the capability to add additional zone presets on the main thermostat,
        so this may not work as expected.

        :return:
        """
        options = self._get_zone_setting("preset_selected")["options"]
        return [opt["label"] for opt in options]

    def get_preset(self) -> str:
        """
        Returns the zone's currently selected preset. Should be one of the
        strings in NexiaThermostat.get_zone_presets().
        :return: str
        """
        preset_selected = self._get_zone_setting("preset_selected")
        current_value = preset_selected["current_value"]
        labels = preset_selected["labels"]
        if isinstance(current_value, int):
            return labels[current_value]
        for option in preset_selected["options"]:
            if option["value"] == current_value:
                return option["label"]
        raise ValueError(f"Unknown preset {current_value}")

    def get_status(self) -> str:
        """
        Returns the zone status.
        :return: str
        """
        return self._get_zone_key("zone_status") or ZONE_IDLE

    def _get_zone_run_mode(self) -> dict[str, Any]:
        """
        Returns the run mode ("permanent_hold", "run_schedule")
        :return: str
        """
        # Will be None is scheduling is disabled
        return self._get_zone_setting_or_none("run_mode")

    def get_setpoint_status(self) -> str:
        """
        Returns the setpoint status, like "Following Schedule - Home", or
        "Permanent Hold"
        :return: str
        """
        run_mode = self._get_zone_run_mode()
        if not run_mode:
            # Scheduling is disabled
            return "Permanent Hold"

        run_mode_current_value = run_mode["current_value"]
        run_mode_label = find_dict_with_keyvalue_in_json(
            run_mode["options"], "value", run_mode_current_value
        )["label"]

        if run_mode_current_value == HOLD_PERMANENT:
            return run_mode_label

        preset_label = self.get_preset()
        if run_mode_current_value == PRESET_MODE_NONE:
            return run_mode_label
        return f"{run_mode_label} - {preset_label}"

    def is_calling(self) -> bool:
        """
        Returns True if the zone is calling for heat/cool.
        :return: bool
        """

        if self.is_native_zone():
            return self.thermostat.get_system_status() != SYSTEM_STATUS_IDLE

        operating_state = self._get_zone_key("operating_state")
        if not operating_state or operating_state == DAMPER_CLOSED:
            return False
        return True

    def is_native_zone(self) -> bool:
        """
        Returns True if the zone is a NativeZone
        :return: bool
        """
        return str(self._get_zone_key("name")) == "NativeZone"

    def check_heat_cool_setpoints(
        self,
        heat_temperature: float | None = None,
        cool_temperature: float | None = None,
    ) -> None:
        """
        Checks the heat and cool setpoints to check if they are within the
        appropriate range and within the deadband limits.

        Will throw exception if not valid.
        :param heat_temperature: int
        :param cool_temperature: int
        :return: None
        """

        deadband = self.thermostat.get_deadband()
        (
            min_temperature,
            max_temperature,
        ) = self.thermostat.get_setpoint_limits()

        if heat_temperature is not None:
            heat_temperature = self.round_temp(heat_temperature)
        if cool_temperature is not None:
            cool_temperature = self.round_temp(cool_temperature)

        if (
            heat_temperature is not None
            and cool_temperature is not None
            and not heat_temperature < cool_temperature
        ):
            raise AttributeError(
                f"The heat setpoint ({heat_temperature}) must be less than the"
                f" cool setpoint ({cool_temperature})."
            )
        if (
            heat_temperature is not None
            and cool_temperature is not None
            and not cool_temperature - heat_temperature >= deadband
        ):
            raise AttributeError(
                f"The heat and cool setpoints must be at least {deadband} "
                f"degrees different."
            )
        if heat_temperature is not None and not heat_temperature <= max_temperature:
            raise AttributeError(
                f"The heat setpoint ({heat_temperature} must be less than the "
                f"maximum temperature of {max_temperature} degrees."
            )
        if cool_temperature is not None and not cool_temperature >= min_temperature:
            raise AttributeError(
                f"The cool setpoint ({cool_temperature}) must be greater than "
                f"the minimum temperature of {min_temperature} degrees."
            )
        # The heat and cool setpoints appear to be valid.

    def is_in_permanent_hold(self) -> bool:
        """
        Returns True if the zone is in a permanent hold.
        :return: bool
        """
        run_mode = self._get_zone_run_mode()
        if not run_mode:
            # Scheduling is disabled
            return True
        return run_mode["current_value"] == HOLD_PERMANENT

    ########################################################################
    # Zone Set Methods

    async def call_return_to_schedule(self) -> None:
        """
        Tells the zone to return to its schedule.
        :return: None
        """

        # Set the thermostat
        await self._post_and_update_zone_json("return_to_schedule", {})

    async def call_permanent_hold(
        self,
        heat_temperature=None,
        cool_temperature=None,
    ) -> None:
        """
        Tells the zone to call a permanent hold. Optionally can provide the
        temperatures.
        :param heat_temperature:
        :param cool_temperature:
        :return:
        """

        if heat_temperature is None and cool_temperature is None:
            # Just calling permanent hold on the current temperature
            heat_temperature = self.get_heating_setpoint()
            cool_temperature = self.get_cooling_setpoint()
        elif heat_temperature is not None and cool_temperature is not None:
            # Both heat and cool setpoints provided, continue
            pass
        else:
            # Not sure how I want to handle only one temperature provided, but
            # this definitely assumes you're using auto mode.
            raise AttributeError(
                "Must either provide both heat and cool setpoints, or don't "
                "provide either"
            )

        await self._set_hold_and_setpoints(
            cool_temperature,
            heat_temperature,
        )

    async def call_permanent_off(self) -> None:
        """Turn off permanently."""
        await self.set_permanent_hold()
        await self.set_mode(mode=OPERATION_MODE_OFF)

    async def set_heat_cool_temp(
        self,
        heat_temperature: float | None = None,
        cool_temperature: float | None = None,
        set_temperature: float | None = None,
    ) -> None:
        """
        Sets the heat and cool temperatures of the zone. You must provide
        either heat and cool temperatures, or just the set_temperature. This
        method will add deadband to the heat and cool temperature from the set
        temperature.

        :param heat_temperature: float or None
        :param cool_temperature: float or None
        :param set_temperature: float or None
        :return: None
        """
        deadband = self.thermostat.get_deadband()

        if set_temperature is None or (heat_temperature and cool_temperature):
            if heat_temperature:
                heat_temperature = self.round_temp(heat_temperature)
            elif cool_temperature:
                heat_temperature = min(
                    self.get_heating_setpoint(),
                    self.round_temp(cool_temperature) - deadband,
                )

            if cool_temperature:
                cool_temperature = self.round_temp(cool_temperature)
            elif heat_temperature:
                cool_temperature = max(
                    self.get_cooling_setpoint(),
                    self.round_temp(heat_temperature) + deadband,
                )

        else:
            # This will smartly select either the ceiling of the floor temp
            # depending on the current operating mode.
            zone_mode = self.get_current_mode()
            if zone_mode == OPERATION_MODE_COOL:
                cool_temperature = self.round_temp(set_temperature)
                heat_temperature = min(
                    self.get_heating_setpoint(),
                    self.round_temp(cool_temperature) - deadband,
                )
            elif zone_mode == OPERATION_MODE_HEAT:
                heat_temperature = self.round_temp(set_temperature)
                cool_temperature = max(
                    self.get_cooling_setpoint(),
                    self.round_temp(heat_temperature) + deadband,
                )
            else:
                cool_temperature = self.round_temp(set_temperature) + math.ceil(
                    deadband / 2
                )
                heat_temperature = self.round_temp(set_temperature) - math.ceil(
                    deadband / 2
                )

        await self._set_setpoints(cool_temperature, heat_temperature)

    async def set_permanent_hold(self) -> None:
        """Set to permanent hold.

        This does not set the temperature, it just sets the hold.
        """
        run_mode = self._get_zone_run_mode()
        if run_mode:
            if run_mode["current_value"] != HOLD_PERMANENT:
                await self._post_and_update_zone_json(
                    "run_mode", {"value": HOLD_PERMANENT}
                )

    async def _set_hold_and_setpoints(
        self, cool_temperature: int | None, heat_temperature: int | None
    ) -> None:
        # Set the thermostat
        await self.set_permanent_hold()
        await self._set_setpoints(cool_temperature, heat_temperature)

    async def _set_setpoints(
        self, cool_temperature: float | None, heat_temperature: float | None
    ) -> None:
        # Check that the setpoints are valid
        self.check_heat_cool_setpoints(heat_temperature, cool_temperature)
        zone_cooling_setpoint = self.get_cooling_setpoint()
        zone_heating_setpoint = self.get_heating_setpoint()
        if (
            zone_cooling_setpoint != cool_temperature
            or heat_temperature != zone_heating_setpoint
        ):
            await self._post_and_update_zone_json(
                "setpoints", {"heat": heat_temperature, "cool": cool_temperature}
            )

    async def set_preset(self, preset: str) -> None:
        """
        Sets the preset of the specified zone.
        :param preset: str - The preset, see
        NexiaThermostat.get_zone_presets(zone_id)
        :return: None
        """
        if self.get_preset() != preset:
            preset_selected = self._get_zone_setting("preset_selected")
            value = 0
            for option in preset_selected["options"]:
                if option["label"] == preset:
                    value = option["value"]
                    break
            await self._post_and_update_zone_json("preset_selected", {"value": value})

    async def set_mode(self, mode: str) -> None:
        """
        Sets the mode of the zone.
        :param mode: str - The mode, see NexiaThermostat.OPERATION_MODES
        :return:
        """
        # Validate the data
        if mode in OPERATION_MODES:
            await self._post_and_update_zone_json("zone_mode", {"value": mode})
        else:
            raise KeyError(
                f'Invalid mode "{mode}". Select one of the following: '
                f"{OPERATION_MODES}"
            )

    def round_temp(self, temperature: float) -> float:
        """
        Rounds the temperature to the nearest 1/2 degree for C and neareast 1
        degree for F
        :param temperature: temperature to round
        :return: float rounded temperature
        """
        if self.thermostat.get_unit() == UNIT_CELSIUS:
            temperature *= 2
            temperature = round(temperature)
            temperature /= 2
        else:
            temperature = round(temperature)
        return temperature

    @property
    def _has_zoning(self) -> bool:
        """Returns if zoning is enabled."""
        return bool(self._zone_json["settings"])

    def _get_zone_setting(self, key: str) -> Any:
        """
        Returns the zone value for the key and zone_id provided.
        :param key: str
        :return: The value of the key/value pair.
        """
        if not self._has_zoning:
            thermostat = self.thermostat
            if key == "zone_mode":
                key = "system_mode"

            return thermostat.get_thermostat_settings_key_or_none(
                key
            ) or thermostat.get_thermostat_settings_key_or_none("mode")

        zone = self._zone_json
        subdict = find_dict_with_keyvalue_in_json(zone["settings"], "type", key)
        if not subdict:
            raise KeyError(f'Zone settings key "{key}" invalid.')
        return subdict

    def _get_zone_setting_or_none(self, key: str) -> Any:
        """
        Returns the zone value from the provided key in the zones's
        JSON.
        :param key: str
        :return: value
        """
        try:
            return self._get_zone_setting(key)
        except KeyError:
            return None

    def _get_zone_features(self, key: str) -> Any:
        """
        Returns the zone value for the key provided.
        :param key: str

        :return: The value of the key/value pair.
        """
        zone = self._zone_json
        subdict = find_dict_with_keyvalue_in_json(zone["features"], "name", key)
        if not subdict:
            raise KeyError(f'Zone feature key "{key}" invalid.')
        return subdict

    def _get_zone_key(self, key: str) -> Any:
        """
        Returns the zone value for the key provided.
        :param key: str
        :return: The value of the key/value pair.
        """
        if key in self._zone_json:
            return self._zone_json[key]

        raise KeyError(f'Zone key "{key}" invalid.')

    async def _post_and_update_zone_json(
        self, end_point: str, payload: dict[str, Any]
    ) -> None:
        url = self.API_MOBILE_ZONE_URL.format(end_point=end_point, zone_id=self.zone_id)
        response = await self._nexia_home.post_url(url, payload)
        self.update_zone_json((await response.json())["result"])

    def update_zone_json(self, zone_json: dict[str, Any]) -> None:
        """Update with new json from the api"""
        if self._zone_json is None:
            return

        _LOGGER.debug(
            "Updated thermostat_id:%s zone_id:%s with new data from post",
            self.thermostat.thermostat_id,
            self.zone_id,
        )
        self._zone_json.update(zone_json)
