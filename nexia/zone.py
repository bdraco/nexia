"""Nexia Themostat Zone."""

import logging
import math

from .const import (
    DAMPER_CLOSED,
    HOLD_PERMANENT,
    MOBILE_URL,
    OPERATION_MODE_COOL,
    OPERATION_MODE_HEAT,
    OPERATION_MODES,
    PRESET_MODE_NONE,
    UNIT_CELSIUS,
    ZONE_IDLE,
)
from .util import find_dict_with_keyvalue_in_json

_LOGGER = logging.getLogger(__name__)


class NexiaThermostatZone:
    """A nexia thermostat zone."""

    API_MOBILE_ZONE_URL = MOBILE_URL + "/xxl_zones/{zone_id}/{end_point}"

    def __init__(self, nexia_home, nexia_thermostat, zone_json):
        """Create a nexia zone."""
        self._nexia_home = nexia_home
        self._zone_json = zone_json
        self.thermostat = nexia_thermostat
        self.zone_id = zone_json["id"]

    def get_name(self):
        """
        Returns the zone name
        :return: str
        """
        return str(self._get_zone_key("name"))

    def get_cooling_setpoint(self):
        """
        Returns the cooling setpoint in the temperature unit of the thermostat
        :return: int
        """
        return self._get_zone_key("setpoints")["cool"]

    def get_heating_setpoint(self):
        """
        Returns the heating setpoint in the temperature unit of the thermostat
        :return: int
        """
        return self._get_zone_key("setpoints")["heat"]

    def get_current_mode(self):
        """
        Returns the current mode of the zone. This may not match the requested
        mode

        :return: str
        """
        return self._get_zone_setting("zone_mode")["current_value"].upper()

    def get_requested_mode(self):
        """
        Returns the requested mode of the zone. This should match the zone's
        mode on the thermostat.
        Available options can be found in NexiaThermostat.OPERATION_MODES
        :return: str
        """
        return self._get_zone_features("thermostat_mode")["value"].upper()

    def get_temperature(self):
        """
        Returns the temperature of the zone in the temperature unit of the
        thermostat.
        :return: int
        """
        return self._get_zone_key("temperature")

    def get_presets(self):
        """
        Supposed to return the zone presets. For some reason, most of the time,
        my unit only returns "AWAY", but I can set the other modes. There is
        the capability to add additional zone presets on the main thermostat,
        so this may not work as expected.

        :return:
        """
        options = self._get_zone_setting("preset_selected")["options"]
        return [opt["label"] for opt in options]

    def get_preset(self):
        """
        Returns the zone's currently selected preset. Should be one of the
        strings in NexiaThermostat.get_zone_presets().
        :return: str
        """
        preset_selected = self._get_zone_setting("preset_selected")
        return preset_selected["labels"][preset_selected["current_value"]]

    def get_status(self):
        """
        Returns the zone status.
        :return: str
        """
        return self._get_zone_key("zone_status") or ZONE_IDLE

    def _get_zone_run_mode(self):
        """
        Returns the run mode ("permanent_hold", "run_schedule")
        :return: str
        """
        return self._get_zone_setting("run_mode")

    def get_setpoint_status(self):
        """
        Returns the setpoint status, like "Following Schedule - Home", or
        "Holding Permanently"
        :return: str
        """
        run_mode = self._get_zone_run_mode()
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

    def is_calling(self):
        """
        Returns True if the zone is calling for heat/cool.
        :return: bool
        """
        operating_state = self._get_zone_key("operating_state")
        if not operating_state or operating_state == DAMPER_CLOSED:
            return False
        return True

    def check_heat_cool_setpoints(self, heat_temperature=None, cool_temperature=None):
        """
        Checks the heat and cool setpoints to check if they are within the
        appropriate range and within the deadband limits.

        Will throw exception if not valid.
        :param heat_temperature: int
        :param cool_temperature: int
        :return: None
        """

        deadband = self.thermostat.get_deadband()
        (min_temperature, max_temperature,) = self.thermostat.get_setpoint_limits()

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

    def is_in_permanent_hold(self):
        """
        Returns True if the zone is in a permanent hold.
        :return: bool
        """
        return self._get_zone_setting("run_mode")["current_value"] == HOLD_PERMANENT

    ########################################################################
    # Zone Set Methods

    def call_return_to_schedule(self):
        """
        Tells the zone to return to its schedule.
        :return: None
        """

        # Set the thermostat
        self._post_and_update_zone_json("return_to_schedule", {})

    def call_permanent_hold(
        self, heat_temperature=None, cool_temperature=None,
    ):
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

        self._set_hold_and_setpoints(
            cool_temperature, heat_temperature,
        )

    def set_heat_cool_temp(
        self, heat_temperature=None, cool_temperature=None, set_temperature=None,
    ):
        """
        Sets the heat and cool temperatures of the zone. You must provide
        either heat and cool temperatures, or just the set_temperature. This
        method will add deadband to the heat and cool temperature from the set
        temperature.

        :param heat_temperature: int or None
        :param cool_temperature: int or None
        :param set_temperature: int or None
        :return: None
        """
        deadband = self.thermostat.get_deadband()

        if set_temperature is None:
            if heat_temperature:
                heat_temperature = self.round_temp(heat_temperature)
            else:
                heat_temperature = min(
                    self.get_heating_setpoint(),
                    self.round_temp(cool_temperature) - deadband,
                )

            if cool_temperature:
                cool_temperature = self.round_temp(cool_temperature)
            else:
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

        self._set_setpoints(cool_temperature, heat_temperature)

    def _set_hold_and_setpoints(self, cool_temperature, heat_temperature):
        # Set the thermostat
        if self._get_zone_run_mode()["current_value"] != HOLD_PERMANENT:
            self._post_and_update_zone_json("run_mode", {"value": HOLD_PERMANENT})

        self._set_setpoints(cool_temperature, heat_temperature)

    def _set_setpoints(self, cool_temperature, heat_temperature):
        # Check that the setpoints are valid
        self.check_heat_cool_setpoints(heat_temperature, cool_temperature)
        zone_cooling_setpoint = self.get_cooling_setpoint()
        zone_heating_setpoint = self.get_heating_setpoint()
        if (
            zone_cooling_setpoint != cool_temperature
            or heat_temperature != zone_heating_setpoint
        ):
            self._post_and_update_zone_json(
                "setpoints", {"heat": heat_temperature, "cool": cool_temperature}
            )

    def set_preset(self, preset):
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
            self._post_and_update_zone_json("preset_selected", {"value": value})

    def set_mode(self, mode):
        """
        Sets the mode of the zone.
        :param mode: str - The mode, see NexiaThermostat.OPERATION_MODES
        :return:
        """
        # Validate the data
        if mode in OPERATION_MODES:
            self._post_and_update_zone_json("zone_mode", {"value": mode})
        else:
            raise KeyError(
                f'Invalid mode "{mode}". Select one of the following: '
                f"{OPERATION_MODES}"
            )

    def round_temp(self, temperature: float):
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
    def _has_zoning(self):
        """Returns if zoning is enabled."""
        return bool(self._zone_json["settings"])

    def _get_zone_setting(self, key):
        """
        Returns the zone value for the key and zone_id provided.
        :param key: str
        :return: The value of the key/value pair.
        """

        if not self._has_zoning:
            if key == "zone_mode":
                key = "system_mode"
            return self.thermostat.get_thermostat_settings_key(key)

        zone = self._zone_json
        subdict = find_dict_with_keyvalue_in_json(zone["settings"], "type", key)
        if not subdict:
            raise KeyError(f'Zone settings key "{key}" invalid.')
        return subdict

    def _get_zone_features(self, key):
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

    def _get_zone_key(self, key):
        """
        Returns the zone value for the key provided.
        :param key: str
        :return: The value of the key/value pair.
        """
        if key in self._zone_json:
            return self._zone_json[key]

        raise KeyError(f'Zone key "{key}" invalid.')

    def _post_and_update_zone_json(self, end_point, payload):
        url = self.API_MOBILE_ZONE_URL.format(end_point=end_point, zone_id=self.zone_id)
        response = self._nexia_home.post_url(url, payload)
        self.update_zone_json(response.json()["result"])

    def update_zone_json(self, zone_json):
        """Update with new json from the api"""
        if self._zone_json is None:
            return

        _LOGGER.debug(
            "Updated thermostat_id:%s zone_id:%s with new data from post",
            self.thermostat.thermostat_id,
            self.zone_id,
        )
        self._zone_json.update(zone_json)
