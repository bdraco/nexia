"""Nexia Thermostat Zone."""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import math
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING, Any, Literal

from .const import (
    DAMPER_CLOSED,
    DEFAULT_UPDATE_METHOD,
    HOLD_PERMANENT,
    HOLD_RESUME_SCHEDULE,
    OPERATION_MODE_COOL,
    OPERATION_MODE_HEAT,
    OPERATION_MODE_OFF,
    OPERATION_MODES,
    PRESET_MODE_NONE,
    SYSTEM_STATUS_IDLE,
    UNIT_CELSIUS,
    ZONE_IDLE,
)
from .sensor import NexiaSensor
from .util import find_dict_with_keyvalue_in_json

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .home import NexiaHome
    from .thermostat import NexiaThermostat

RUN_MODE_KEYS = (
    "run_mode",
    "thermostat_run_mode",  # ux360
)
HOLD_VALUES = (
    HOLD_PERMANENT,
    "hold",  # ux360
)
HOLD_VALUES_SET = set(HOLD_VALUES)
RESUME_SCHEDULE_VALUES = (
    HOLD_RESUME_SCHEDULE,
    "schedule",  # ux360
)
RESUME_VALUES_SET = set(RESUME_SCHEDULE_VALUES)


class ZoneEndpoint(Enum):
    """Enum for Thermostat Endpoints."""

    RUN_MODE = auto()
    SETPOINTS = auto()
    PRESET_SELECTED = auto()
    ZONE_MODE = auto()


@dataclass
class ZoneEndPointData:
    """Dataclass for Thermostat Endpoints.

    feature is the area of the json to look for the key
    action is the action to take in the json
    fallback_endpoint is the endpoint to use if the feature is not found
    """

    type: Literal["setting", "feature"]
    key: str
    action: str
    fallback_endpoint: str


ENDPOINT_MAP = {
    ZoneEndpoint.RUN_MODE: ZoneEndPointData(
        type="feature",
        key="thermostat_run_mode",
        action="update_thermostat_run_mode",
        fallback_endpoint="run_mode",
    ),
    ZoneEndpoint.SETPOINTS: ZoneEndPointData(
        type="feature",
        key="thermostat",
        action="set_setpoints",
        fallback_endpoint="setpoints",
    ),
    ZoneEndpoint.PRESET_SELECTED: ZoneEndPointData(
        type="setting",
        key="thermostat_mode",
        action="type",
        fallback_endpoint="preset_selected",
    ),
    ZoneEndpoint.ZONE_MODE: ZoneEndPointData(
        type="feature",
        key="thermostat_mode",
        action="update_thermostat_mode",
        fallback_endpoint="zone_mode",
    ),
}


class NexiaThermostatZone:
    """A nexia thermostat zone."""

    def __init__(
        self,
        nexia_home: NexiaHome,
        nexia_thermostat: NexiaThermostat,
        zone_json: dict[str, Any],
    ) -> None:
        """Create a nexia zone."""
        self._nexia_home = nexia_home
        self._zone_json = zone_json
        self.thermostat = nexia_thermostat
        self.zone_id: int = zone_json["id"]

    @property
    def API_MOBILE_ZONE_URL(self) -> str:  # pylint: disable=invalid-name
        return self._nexia_home.mobile_url + "/xxl_zones/{zone_id}/{end_point}"

    def get_name(self) -> str:
        """Returns the zone name
        :return: str.
        """
        if self.is_native_zone():
            return f"{self.thermostat.get_name()} NativeZone"

        return str(self._get_zone_key("name"))

    def get_cooling_setpoint(self) -> int:
        """Returns the cooling setpoint in the temperature unit of the thermostat
        :return: int.
        """
        return (
            self._get_zone_key("setpoints")["cool"]
            or self.thermostat.get_setpoint_limits()[1]
        )

    def get_heating_setpoint(self) -> int:
        """Returns the heating setpoint in the temperature unit of the thermostat
        :return: int.
        """
        return (
            self._get_zone_key("setpoints")["heat"]
            or self.thermostat.get_setpoint_limits()[0]
        )

    def get_current_mode(self) -> str:
        """Returns the current mode of the zone. This may not match the requested
        mode.

        :return: str
        """
        return self._get_zone_setting("zone_mode")["current_value"].upper()

    def get_requested_mode(self) -> str:
        """Returns the requested mode of the zone. This should match the zone's
        mode on the thermostat.
        Available options can be found in NexiaThermostat.OPERATION_MODES
        :return: str.
        """
        return self._get_zone_features("thermostat_mode")["value"].upper()

    def get_temperature(self) -> int:
        """Returns the temperature of the zone in the temperature unit of the
        thermostat.
        :return: int.
        """
        return self._get_zone_key("temperature")

    def get_presets(self) -> list[str]:
        """Supposed to return the zone presets. For some reason, most of the time,
        my unit only returns "AWAY", but I can set the other modes. There is
        the capability to add additional zone presets on the main thermostat,
        so this may not work as expected.

        :return:
        """
        options = self._get_zone_setting("preset_selected")["options"]
        return [opt["label"] for opt in options]

    def get_preset(self) -> str:
        """Returns the zone's currently selected preset. Should be one of the
        strings in NexiaThermostat.get_zone_presets().
        :return: str.
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
        """Returns the zone status.
        :return: str.
        """
        return self._get_zone_key("zone_status") or ZONE_IDLE

    def _get_zone_run_mode(self) -> dict[str, Any] | None:
        """Returns the run mode ("permanent_hold", "run_schedule")
        :return: str.
        """
        # Will be None is scheduling is disabled
        for key in RUN_MODE_KEYS:
            if run_mode := self._get_zone_setting_or_none(key):
                return run_mode
        return None

    def get_setpoint_status(self) -> str:
        """Returns the setpoint status, like "Following Schedule - Home", or
        "Permanent Hold"
        :return: str.
        """
        run_mode = self._get_zone_run_mode()
        if not run_mode:
            # Scheduling is disabled
            return "Permanent Hold"

        run_mode_current_value = run_mode["current_value"]
        run_mode_label = find_dict_with_keyvalue_in_json(
            run_mode["options"],
            "value",
            run_mode_current_value,
        )["label"]

        if run_mode_current_value in HOLD_VALUES_SET:
            return run_mode_label

        preset_label = self.get_preset()
        if run_mode_current_value == PRESET_MODE_NONE:
            return run_mode_label
        return f"{run_mode_label} - {preset_label}"

    def is_calling(self) -> bool:
        """Returns True if the zone is calling for heat/cool.
        :return: bool.
        """
        if self.is_native_zone():
            return self.thermostat.get_system_status() != SYSTEM_STATUS_IDLE

        operating_state = self._get_zone_key("operating_state")
        return not (not operating_state or operating_state == DAMPER_CLOSED)

    def is_native_zone(self) -> bool:
        """Returns True if the zone is a NativeZone
        :return: bool.
        """
        return str(self._get_zone_key("name")) == "NativeZone"

    def check_heat_cool_setpoints(
        self,
        heat_temperature: float | None = None,
        cool_temperature: float | None = None,
    ) -> None:
        """Checks the heat and cool setpoints to check if they are within the
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
                f" cool setpoint ({cool_temperature}).",
            )
        if (
            heat_temperature is not None
            and cool_temperature is not None
            and not cool_temperature - heat_temperature >= deadband
        ):
            raise AttributeError(
                f"The heat and cool setpoints must be at least {deadband} "
                f"degrees different.",
            )
        if heat_temperature is not None and not heat_temperature <= max_temperature:
            raise AttributeError(
                f"The heat setpoint ({heat_temperature} must be less than the "
                f"maximum temperature of {max_temperature} degrees.",
            )
        if cool_temperature is not None and not cool_temperature >= min_temperature:
            raise AttributeError(
                f"The cool setpoint ({cool_temperature}) must be greater than "
                f"the minimum temperature of {min_temperature} degrees.",
            )
        # The heat and cool setpoints appear to be valid.

    def _get_run_mode_option_values(self) -> set[str] | None:
        if not (data := self._get_zone_run_mode()) or "options" not in data:
            return None
        options = data["options"]
        return {option["value"] for option in options}

    def _get_perm_hold_value(self) -> str:
        if not (values := self._get_run_mode_option_values()) or not (
            intersection_values := values & HOLD_VALUES_SET
        ):
            return HOLD_VALUES[0]
        return intersection_values.pop()

    def _get_resume_schedule_value(self) -> str:
        if not (values := self._get_run_mode_option_values()) or not (
            intersection_values := values & RESUME_VALUES_SET
        ):
            return RESUME_SCHEDULE_VALUES[0]
        return intersection_values.pop()

    def is_in_permanent_hold(self) -> bool:
        """Returns True if the zone is in a permanent hold.
        :return: bool.
        """
        if not (run_mode := self._get_zone_run_mode()):
            # Scheduling is disabled
            return True
        return run_mode["current_value"] in HOLD_VALUES_SET

    def _get_room_iq_sensors_json(self) -> list[dict[str, Any]]:
        """Get our list of RoomIQ sensor json dictionaries, or raise AttributeError."""
        try:
            return self._get_zone_features("room_iq_sensors")["sensors"]
        except KeyError as e:
            raise AttributeError(
                f"RoomIQ sensors not supported in zone {self.get_name()}"
            ) from e

    def get_sensors(self) -> list[NexiaSensor]:
        """Get the sensor detail data objects from this instance
        :return: list of sensor detail data objects
        """
        try:
            sensors_json = self._get_room_iq_sensors_json()

            return [NexiaSensor.from_json(sensor_json) for sensor_json in sensors_json]
        except AttributeError:
            # our json has no sensors
            return []

    def get_active_sensor_ids(self) -> set[int]:
        """Get the set of RoomIQ sensor ids included in the zone average.

        :return: set of active RoomIQ sensor ids.
        """
        try:
            sensors_json = self._get_room_iq_sensors_json()

            return {sensor["id"] for sensor in sensors_json if sensor["weight"] > 0.0}
        except AttributeError:
            return set()

    def get_sensor_by_id(self, sensor_id: int) -> NexiaSensor:
        """Get a RoomIQ sensor detail data object by its sensor id.
        :param sensor_id: identifier of RoomIQ sensor to get
        :return: sensor detail data object
        """
        sensors_json = self._get_room_iq_sensors_json()
        try:
            sensor_json = find_dict_with_keyvalue_in_json(sensors_json, "id", sensor_id)
            return NexiaSensor.from_json(sensor_json)
        except KeyError:
            valid_ids = (str(sensor_json["id"]) for sensor_json in sensors_json)
            raise KeyError(
                f"Sensor ID ({sensor_id}) not found, valid IDs: {', '.join(valid_ids)}"
            ) from None

    ########################################################################
    # Zone Set Methods

    async def call_return_to_schedule(self) -> None:
        """Tells the zone to return to its schedule.
        :return: None.
        """
        # Set the thermostat
        if run_mode := self._get_zone_run_mode():
            if run_mode["current_value"] in RESUME_VALUES_SET:
                return
            await self._post_and_update_zone_json(
                ZoneEndpoint.RUN_MODE, {"value": self._get_resume_schedule_value()}
            )
            return
        # Legacy endpoint
        await self._update_zone_json_with_method(
            "return_to_schedule",
            self.API_MOBILE_ZONE_URL.format(
                end_point="return_to_schedule", zone_id=self.zone_id
            ),
            {},
            DEFAULT_UPDATE_METHOD,
        )

    async def call_permanent_hold(
        self,
        heat_temperature=None,
        cool_temperature=None,
    ) -> None:
        """Tells the zone to call a permanent hold. Optionally can provide the
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
                "provide either",
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
        """Sets the heat and cool temperatures of the zone. You must provide
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
                    deadband / 2,
                )
                heat_temperature = self.round_temp(set_temperature) - math.ceil(
                    deadband / 2,
                )

        await self._set_setpoints(cool_temperature, heat_temperature)

    async def set_permanent_hold(self) -> None:
        """Set to permanent hold.

        This does not set the temperature, it just sets the hold.
        """
        run_mode = self._get_zone_run_mode()
        if run_mode and run_mode["current_value"] not in HOLD_VALUES_SET:
            await self._post_and_update_zone_json(
                ZoneEndpoint.RUN_MODE, {"value": self._get_perm_hold_value()}
            )

    async def _set_hold_and_setpoints(
        self,
        cool_temperature: int | None,
        heat_temperature: int | None,
    ) -> None:
        # Set the thermostat
        await self.set_permanent_hold()
        await self._set_setpoints(cool_temperature, heat_temperature)

    async def _set_setpoints(
        self,
        cool_temperature: float | None,
        heat_temperature: float | None,
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
                ZoneEndpoint.SETPOINTS,
                {"heat": heat_temperature, "cool": cool_temperature},
            )

    async def set_preset(self, preset: str) -> None:
        """Sets the preset of the specified zone.
        :param preset: str - The preset, see
        NexiaThermostat.get_zone_presets(zone_id)
        :return: None.
        """
        if self.get_preset() != preset:
            preset_selected = self._get_zone_setting("preset_selected")
            value = 0
            for option in preset_selected["options"]:
                if option["label"] == preset:
                    value = option["value"]
                    break
            await self._post_and_update_zone_json(
                ZoneEndpoint.PRESET_SELECTED, {"value": value}
            )

    async def set_mode(self, mode: str) -> None:
        """Sets the mode of the zone.
        :param mode: str - The mode, see NexiaThermostat.OPERATION_MODES
        :return:
        """
        # Validate the data
        if mode in OPERATION_MODES:
            await self._post_and_update_zone_json(
                ZoneEndpoint.ZONE_MODE, {"value": mode}
            )
        else:
            raise KeyError(
                f'Invalid mode "{mode}". Select one of the following: {OPERATION_MODES}',
            )

    async def select_room_iq_sensors(
        self, active_sensor_ids: Iterable[int], polling_delay=5.0, max_polls=8
    ) -> bool:
        """Select which RoomIQ sensors are included in the zone average.
        :param active_sensor_ids: collection of RoomIQ sensor identifiers to form the zone average
        :param polling_delay: seconds to wait before each polling attempt
        :param max_polls: maximum number of times to poll for completion
        :return: bool indicating completed
        """
        if not active_sensor_ids:
            raise ValueError(
                f"At least one sensor is required when selecting"
                f" RoomIQ sensors, but got `{active_sensor_ids!r}`"
            )
        active_sensor_id_set = set(active_sensor_ids)
        request_json = copy.deepcopy(self._get_room_iq_sensors_json())

        known_sensor_ids = [sensor["id"] for sensor in request_json]
        for sensor_id in active_sensor_id_set:
            if sensor_id not in known_sensor_ids:
                raise ValueError(f"RoomIQ sensor with id {sensor_id} not present")

        weight = 1 / len(active_sensor_id_set)
        for sensor in request_json:
            sensor["weight"] = weight if sensor["id"] in active_sensor_id_set else 0.0

        update_active_sensors = self.API_MOBILE_ZONE_URL.format(
            end_point="update_active_sensors", zone_id=self.zone_id
        )
        return await self._post_and_await_async_completion(
            update_active_sensors,
            {"updated_sensors": request_json},
            "selecting active sensors",
            polling_delay,
            max_polls,
        )

    async def load_current_sensor_state(self, polling_delay=5.0, max_polls=8) -> bool:
        """Load the current state of a zone's sensors into the physical thermostat.
        :param polling_delay: seconds to wait before each polling attempt
        :param max_polls: maximum number of times to poll for completion
        :return: bool indicating completed
        """
        req_cur_state = self.API_MOBILE_ZONE_URL.format(
            end_point="request_current_sensor_state", zone_id=self.zone_id
        )
        return await self._post_and_await_async_completion(
            req_cur_state, {}, "loading current sensor state", polling_delay, max_polls
        )

    async def _post_and_await_async_completion(
        self,
        request_url: str,
        json_data: dict,
        target: str,
        polling_delay: float,
        max_polls: int,
    ) -> bool:
        """Post a request that returns an asynchronous url to poll for completion.
        :param request_url: url for service being requested
        :param json_data: json data to be the request payload
        :param target: description of what is being accomplished
        :param polling_delay: seconds to wait before each polling attempt
        :param max_polls: maximum number of times to poll for completion
        :return: bool indicating completed
        """
        async with await self._nexia_home.post_url(request_url, json_data) as response:
            # The polling path in the response has the form:
            #   https://www.mynexia.com/backstage/announcements/<48-hex-digits>
            polling_url = self._nexia_home.resolve_url(
                (await response.json())["result"]["polling_path"]
            )
        attempts = max_polls

        while attempts:
            await asyncio.sleep(polling_delay)
            async with await self._nexia_home._get_url(polling_url) as response:  # noqa: SLF001
                payload = (await response.read()).strip()

            if payload != b"null":
                status = json.loads(payload)["status"]

                if status != "success":
                    _LOGGER.error("Unexpected status [%s] %s", status, target)
                return True
            attempts -= 1
        # end while waiting for status

        _LOGGER.error("Gave up waiting while %s", target)
        return False

    def round_temp(self, temperature: float) -> float:
        """Rounds the temperature to the nearest 1/2 degree for C and nearest 1
        degree for F
        :param temperature: temperature to round
        :return: float rounded temperature.
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
        """Returns the zone value for the key and zone_id provided.
        :param key: str
        :return: The value of the key/value pair.
        """
        if not self._has_zoning:
            thermostat = self.thermostat
            if key == "zone_mode":
                key = "system_mode"

            return thermostat.get_thermostat_settings_key_or_none(
                key,
            ) or thermostat.get_thermostat_settings_key_or_none("mode")

        zone = self._zone_json
        subdict = find_dict_with_keyvalue_in_json(zone["settings"], "type", key)
        if not subdict:
            raise KeyError(f'Zone settings key "{key}" invalid.')
        return subdict

    def _get_zone_setting_or_none(self, key: str) -> Any:
        """Returns the zone value from the provided key in the zone's
        JSON.
        :param key: str
        :return: value.
        """
        try:
            return self._get_zone_setting(key)
        except KeyError:
            return None

    def _get_zone_features(self, key: str) -> Any:
        """Returns the zone value for the key provided.
        :param key: str.

        :return: The value of the key/value pair.
        """
        zone = self._zone_json
        subdict = find_dict_with_keyvalue_in_json(zone["features"], "name", key)
        if not subdict:
            raise KeyError(f'Zone feature key "{key}" invalid.')
        return subdict

    def _get_zone_key(self, key: str) -> Any:
        """Returns the zone value for the key provided.
        :param key: str
        :return: The value of the key/value pair.
        """
        if key in self._zone_json:
            return self._zone_json[key]

        raise KeyError(f'Zone key "{key}" invalid.')

    def _find_url_and_method_for_endpoint(
        self, end_point_data: ZoneEndPointData
    ) -> tuple[str, str] | None:
        actions: dict[str, dict[str, str]] | None = None
        try:
            if (
                data := self._get_zone_setting(end_point_data.key)
                if end_point_data.type == "setting"
                else self._get_zone_features(end_point_data.key)
            ) and "actions" in data:
                actions = data["actions"]
        except KeyError:
            pass

        if actions:
            for action in ("self", end_point_data.action):
                if action_data := actions.get(action):
                    return action_data["href"], action_data.get(
                        "method", DEFAULT_UPDATE_METHOD
                    )

        return None

    async def _post_and_update_zone_json(
        self,
        end_point: ZoneEndpoint,
        payload: dict[str, Any],
    ) -> None:
        if not (end_point_data := ENDPOINT_MAP.get(end_point)):
            raise ValueError(f"Invalid endpoint {end_point}")
        url: str | None = None
        method: str = DEFAULT_UPDATE_METHOD
        url_method = self._find_url_and_method_for_endpoint(end_point_data)
        if url_method is not None:
            url, method = url_method
        if url is None:
            if end_point_data.fallback_endpoint is None:
                raise ValueError(
                    f"Could not find url for endpoint {end_point} and no fallback"
                )
            url = self.API_MOBILE_ZONE_URL.format(
                end_point=end_point_data.fallback_endpoint, zone_id=self.zone_id
            )
        await self._update_zone_json_with_method(end_point, url, payload, method)

    async def _update_zone_json_with_method(
        self,
        end_point: ZoneEndpoint | str,
        url: str,
        payload: dict[str, Any],
        method: str,
    ) -> None:
        if method != DEFAULT_UPDATE_METHOD:
            raise ValueError(
                f"Unsupported method {method} for endpoint {end_point} url {url}"
            )
        async with await self._nexia_home.post_url(url, payload) as response:
            self.update_zone_json((await response.json())["result"])

    def update_zone_json(self, zone_json: dict[str, Any]) -> None:
        """Update with new json from the api."""
        if self._zone_json is None:
            return

        _LOGGER.debug(
            "Updated thermostat_id:%s zone_id:%s with new data from post",
            self.thermostat.thermostat_id,
            self.zone_id,
        )
        self._zone_json.update(zone_json)
