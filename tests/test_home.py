"""Tests for Nexia Home."""

import asyncio
import json
import logging
import os
from os.path import dirname
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
from aioresponses import aioresponses
from aioresponses.compat import URL

from nexia.home import (
    LoginFailedException,
    NexiaHome,
    _extract_devices_from_houses_json,
    extract_children_from_devices_json,
)
from nexia.roomiq import NexiaRoomIQHarmonizer
from nexia.thermostat import NexiaThermostat, clamp_to_predefined_values
from nexia.util import SingleShot, find_dict_with_keyvalue_in_json
from nexia.zone import NexiaThermostatZone

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_aioresponse():
    with aioresponses() as m:
        yield m


@pytest.fixture(name="aiohttp_session")
async def aiohttp_session():
    """Mock session."""
    session = aiohttp.ClientSession()
    yield session
    await session.close()


def _load_fixture(filename):
    """Load a fixture."""
    test_dir = dirname(__file__)

    path = os.path.join(test_dir, "fixtures", filename)
    with open(path) as fptr:
        return fptr.read()


async def load_fixture(filename):
    """Load a fixture."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _load_fixture, filename)


async def test_login(
    aiohttp_session: aiohttp.ClientSession, mock_aioresponse: aioresponses
) -> None:
    """Test login sequence."""
    persist_file = Path("nexia_config_test.conf")
    nexia = NexiaHome(aiohttp_session, state_file=persist_file)

    mock_aioresponse.post(
        "https://www.mynexia.com/mobile/accounts/sign_in",
        status=206,
        body="no good",
    )
    with pytest.raises(
        ValueError,
        match="Failed to login\nno good",
    ):
        await nexia.login()

    forgot_password_url = "https://www.mynexia.com/account/forgotten_credentials"
    mock_aioresponse.post(
        "https://www.mynexia.com/mobile/accounts/sign_in",
        status=307,
        headers={aiohttp.hdrs.LOCATION: forgot_password_url},
    )
    mock_aioresponse.get(
        forgot_password_url,
    )
    with pytest.raises(
        LoginFailedException,
        match=f"Failed to login, getting redirected to {forgot_password_url}"
        f". Try to login manually on the website.",
    ):
        await nexia.login()

    mock_aioresponse.post(
        "https://www.mynexia.com/mobile/accounts/sign_in",
        payload={
            "success": True,
            "error": None,
            "result": {
                "mobile_id": 5400000,
                "api_key": "10654c0be00000000000000000000000",
                "setup_step": "done",
                "locale": "en_us",
            },
        },
    )
    mock_aioresponse.post(
        "https://www.mynexia.com/mobile/session",
        body=await load_fixture("mobile_session.json"),
    )
    await nexia.login()

    mock_aioresponse.get(
        "https://www.mynexia.com/mobile/houses/2582941",
        status=304,
    )
    assert await nexia.update() is None

    mock_aioresponse.get(
        "https://www.mynexia.com/mobile/houses/2582941",
        status=208,
        body="failing text",
    )
    with pytest.raises(
        ValueError,
        match="Unexpected http status while fetching house JSON\nfailing text",
    ):
        await nexia.update()

    mock_aioresponse.get(
        "https://www.mynexia.com/mobile/houses/2582941",
    )
    with pytest.raises(
        ValueError,
        match="Nothing in the JSON",
    ):
        await nexia.update()

    mock_aioresponse.get(
        "https://www.mynexia.com/mobile/houses/2582941",
        body=await load_fixture("mobile_houses_123456.json"),
    )
    assert await nexia.update() is not None

    mock_aioresponse.get(
        "https://www.mynexia.com/mobile/phones",
        body=await load_fixture("mobile_phones_response.json"),
    )
    assert await nexia.get_phone_ids() == [5488863]

    assert nexia.get_thermostat_ids() == [2059661, 2059676, 2293892, 2059652]
    thermostat = nexia.get_thermostat_by_id(2059661)
    assert thermostat.get_zone_ids() == [83261002, 83261005, 83261008, 83261011]
    zone = thermostat.get_zone_by_id(83261002)

    mock_aioresponse.post(
        "https://www.mynexia.com/mobile/xxl_zones/83261002/setpoints",
        body=await load_fixture("zone_response.json"),
    )
    await zone.set_heat_cool_temp(69.0, 78.0)

    assert persist_file.exists() is True
    persist_file.unlink()
    assert persist_file.exists() is False


async def test_update(aiohttp_session: aiohttp.ClientSession) -> None:
    nexia = NexiaHome(aiohttp_session)
    devices_json = json.loads(await load_fixture("mobile_houses_123456.json"))
    nexia.update_from_json(devices_json)
    thermostat = nexia.get_thermostat_by_id(2059661)
    zone_ids = thermostat.get_zone_ids()
    assert zone_ids == [83261002, 83261005, 83261008, 83261011]
    nexia.update_from_json(devices_json)
    zone_ids = thermostat.get_zone_ids()
    assert zone_ids == [83261002, 83261005, 83261008, 83261011]
    nexia.update_from_json(devices_json)


async def test_idle_thermo(aiohttp_session: aiohttp.ClientSession) -> None:
    """Get methods for an idle thermostat."""
    nexia = NexiaHome(aiohttp_session)
    devices_json = json.loads(await load_fixture("mobile_houses_123456.json"))
    nexia.update_from_json(devices_json)

    thermostat = nexia.get_thermostat_by_id(2059661)

    assert thermostat.get_model() == "XL1050"
    assert thermostat.get_firmware() == "5.9.1"
    assert thermostat.get_dev_build_number() == "1581321824"
    assert thermostat.get_device_id() == "000000"
    assert thermostat.get_type() == "XL1050"
    assert thermostat.get_name() == "Downstairs East Wing"
    assert thermostat.get_deadband() == 3
    assert thermostat.get_setpoint_limits() == (55, 99)
    assert thermostat.get_variable_fan_speed_limits() == (0.35, 1.0)
    assert thermostat.get_unit() == "F"
    assert thermostat.get_humidity_setpoint_limits() == (0.35, 0.65)
    assert thermostat.get_fan_mode(), "Auto"
    assert thermostat.get_fan_modes() == ["Auto", "On", "Circulate"]
    assert thermostat.get_outdoor_temperature() == 88.0
    assert thermostat.get_relative_humidity() == 0.36
    assert thermostat.get_current_compressor_speed() == 0.0
    assert thermostat.get_requested_compressor_speed() == 0.0
    assert thermostat.get_fan_speed_setpoint() == 0.35
    assert thermostat.get_dehumidify_setpoint() == 0.50
    assert thermostat.has_dehumidify_support() is True
    assert thermostat.has_dehumidify_support() is True
    assert thermostat.has_humidify_support() is False
    assert thermostat.has_emergency_heat() is False
    assert thermostat.get_system_status() == "System Idle"
    assert thermostat.has_air_cleaner() is True
    assert thermostat.get_air_cleaner_mode() == "auto"
    assert thermostat.is_blower_active() is False

    zone_ids = thermostat.get_zone_ids()
    assert zone_ids == [83261002, 83261005, 83261008, 83261011]


async def test_idle_thermo_issue_33758(mock_aioresponse: aioresponses) -> None:
    """Get methods for an idle thermostat."""
    aiohttp_session = aiohttp.ClientSession()
    nexia = NexiaHome(aiohttp_session)
    devices_json = json.loads(await load_fixture("mobile_house_issue_33758.json"))
    nexia.update_from_json(devices_json)

    thermostat: NexiaThermostat = nexia.get_thermostat_by_id(12345678)

    assert thermostat.get_model() == "XL1050"
    assert thermostat.get_firmware() == "5.9.1"
    assert thermostat.get_dev_build_number() == "1581321824"
    assert thermostat.get_device_id() == "xxxxxx"
    assert thermostat.get_type() == "XL1050"
    assert thermostat.get_name() == "Thermostat"
    assert thermostat.get_deadband() == 3
    assert thermostat.get_setpoint_limits() == (55, 99)
    assert thermostat.get_variable_fan_speed_limits() == (0.35, 1.0)
    assert thermostat.get_unit() == "F"
    assert thermostat.has_humidify_support() is True
    assert thermostat.get_humidity_setpoint_limits() == (0.10, 0.65)
    assert thermostat.get_fan_mode() == "Auto"
    assert thermostat.get_fan_modes() == ["Auto", "On", "Circulate"]
    assert thermostat.get_outdoor_temperature() == 55.0
    assert thermostat.get_relative_humidity() == 0.43
    assert thermostat.get_current_compressor_speed() == 0.0
    assert thermostat.get_requested_compressor_speed() == 0.0
    assert thermostat.get_fan_speed_setpoint() == 1
    assert thermostat.get_dehumidify_setpoint() == 0.55
    assert thermostat.has_dehumidify_support() is True
    assert thermostat.has_humidify_support() is True
    assert thermostat.has_emergency_heat() is True
    assert thermostat.is_emergency_heat_active() is False
    assert thermostat.get_system_status() == "System Idle"
    assert thermostat.has_air_cleaner() is True
    assert thermostat.get_air_cleaner_mode() == "auto"
    assert thermostat.is_blower_active() is False

    devices = _extract_devices_from_houses_json(devices_json)
    mock_aioresponse.post(
        "https://www.mynexia.com/mobile/xxl_thermostats/12345678/emergency_heat",
        payload={"result": devices[0]},
    )
    await thermostat.set_emergency_heat(True)

    mock_aioresponse.post(
        "https://www.mynexia.com/mobile/xxl_thermostats/12345678/emergency_heat",
        payload={"result": devices[0]},
    )
    await thermostat.set_emergency_heat(False)

    zone_ids = thermostat.get_zone_ids()
    assert zone_ids == [12345678]
    await aiohttp_session.close()


async def test_idle_thermo_issue_33968_thermostat_1690380(
    aiohttp_session: aiohttp.ClientSession,
) -> None:
    """Get methods for a cooling thermostat."""
    nexia = NexiaHome(aiohttp_session)
    devices_json = json.loads(await load_fixture("mobile_house_issue_33968.json"))
    nexia.update_from_json(devices_json)

    thermostat_ids = nexia.get_thermostat_ids()
    assert thermostat_ids == [1690380]

    thermostat = nexia.get_thermostat_by_id(1690380)

    zone_ids = thermostat.get_zone_ids()
    assert zone_ids == [83037337, 83037340, 83037343]

    assert thermostat.get_model() == "XL1050"
    assert thermostat.get_firmware() == "5.9.1"
    assert thermostat.get_dev_build_number() == "1581321824"
    assert thermostat.get_device_id() == "removed"
    assert thermostat.get_type() == "XL1050"
    assert thermostat.get_name() == "Thermostat"
    assert thermostat.get_deadband() == 3
    assert thermostat.get_setpoint_limits() == (55, 99)
    assert thermostat.get_variable_fan_speed_limits() == (0.35, 1.0)
    assert thermostat.get_unit() == "F"
    assert thermostat.get_humidity_setpoint_limits() == (0.35, 0.65)
    assert thermostat.get_fan_mode() == "Auto"
    assert thermostat.get_fan_modes() == ["Auto", "On", "Circulate"]
    assert thermostat.get_outdoor_temperature() == 80.0
    assert thermostat.get_relative_humidity() == 0.55
    assert thermostat.get_current_compressor_speed() == 0.41
    assert thermostat.get_requested_compressor_speed() == 0.41
    assert thermostat.get_fan_speed_setpoint() == 0.5
    assert thermostat.get_dehumidify_setpoint() == 0.55
    assert thermostat.has_dehumidify_support() is True
    assert thermostat.has_humidify_support() is False
    assert thermostat.has_emergency_heat() is True
    assert thermostat.is_emergency_heat_active() is False
    assert thermostat.get_system_status() == "Cooling"
    assert thermostat.has_air_cleaner() is True
    assert thermostat.get_air_cleaner_mode() == "auto"
    assert thermostat.is_blower_active() is True


async def test_active_thermo(aiohttp_session):
    """Get methods for an active thermostat."""
    nexia = NexiaHome(aiohttp_session)
    devices_json = json.loads(await load_fixture("mobile_houses_123456.json"))
    nexia.update_from_json(devices_json)

    thermostat = nexia.get_thermostat_by_id(2293892)

    assert thermostat.get_model() == "XL1050"
    assert thermostat.get_firmware() == "5.9.1"
    assert thermostat.get_dev_build_number() == "1581321824"
    assert thermostat.get_device_id() == "0281B02C"
    assert thermostat.get_type() == "XL1050"
    assert thermostat.get_name() == "Master Suite"
    assert thermostat.get_deadband() == 3
    assert thermostat.get_setpoint_limits() == (55, 99)
    assert thermostat.get_variable_fan_speed_limits() == (0.35, 1.0)
    assert thermostat.get_unit() == "F"
    assert thermostat.get_humidity_setpoint_limits() == (0.35, 0.65)
    assert thermostat.get_fan_mode() == "Auto"
    assert thermostat.get_fan_modes() == ["Auto", "On", "Circulate"]
    assert thermostat.get_outdoor_temperature() == 87.0
    assert thermostat.get_relative_humidity() is None
    assert thermostat.get_current_compressor_speed() == 0.69
    assert thermostat.get_requested_compressor_speed() == 0.69
    assert thermostat.get_fan_speed_setpoint() == 0.35
    assert thermostat.get_dehumidify_setpoint() == 0.45
    assert thermostat.has_dehumidify_support() is True
    assert thermostat.has_humidify_support() is False
    assert thermostat.has_emergency_heat() is False
    assert thermostat.get_system_status() == "Cooling"
    assert thermostat.has_air_cleaner() is True
    assert thermostat.get_air_cleaner_mode() == "auto"
    assert thermostat.is_blower_active() is True

    zone_ids = thermostat.get_zone_ids()
    assert zone_ids == [83394133, 83394130, 83394136, 83394127, 83394139]


@pytest.mark.skip(reason="not yet supported")
async def test_xl624(aiohttp_session):
    """Get methods for an xl624 thermostat."""
    nexia = NexiaHome(aiohttp_session)
    devices_json = json.loads(await load_fixture("mobile_house_xl624.json"))
    nexia.update_from_json(devices_json)

    thermostat_ids = nexia.get_thermostat_ids()
    assert thermostat_ids == [2222222, 3333333]
    thermostat = nexia.get_thermostat_by_id(1111111)

    assert thermostat.get_model() is None
    assert thermostat.get_firmware() == "2.8"
    assert thermostat.get_dev_build_number() == "0603340208"
    assert thermostat.get_device_id() is None
    assert thermostat.get_type() is None
    assert thermostat.get_name() == "Downstairs Hall"
    assert thermostat.get_deadband() == 3
    assert thermostat.get_setpoint_limits() == (55, 99)
    assert thermostat.has_variable_fan_speed() is False
    assert thermostat.get_unit() == "F"
    assert thermostat.get_humidity_setpoint_limits() == (0.10, 0.65)
    assert thermostat.get_fan_mode() == "Auto"
    assert thermostat.get_fan_modes() == ["Auto", "On", "Cycler"]
    assert thermostat.get_current_compressor_speed() == 0.0
    assert thermostat.get_requested_compressor_speed() == 0.0
    assert thermostat.has_dehumidify_support() is False
    assert thermostat.has_humidify_support() is False
    assert thermostat.has_emergency_heat() is False
    assert thermostat.get_system_status() == "System Idle"
    assert thermostat.has_air_cleaner() is False
    assert thermostat.is_blower_active() is False

    zone_ids = thermostat.get_zone_ids()
    assert zone_ids == [12345678]


async def test_xl824_1(aiohttp_session):
    """Get methods for an xl824 thermostat."""
    nexia = NexiaHome(aiohttp_session)
    devices_json = json.loads(await load_fixture("mobile_house_xl624.json"))
    nexia.update_from_json(devices_json)

    thermostat_ids = nexia.get_thermostat_ids()
    assert thermostat_ids == [2222222, 3333333]
    thermostat = nexia.get_thermostat_by_id(2222222)

    assert thermostat.get_model() == "XL824"
    assert thermostat.get_firmware() == "5.9.1"
    assert thermostat.get_dev_build_number() == "1581314625"
    assert thermostat.get_device_id() == "0167CA48"
    assert thermostat.get_type() == "XL824"
    assert thermostat.get_name() == "Family Room"
    assert thermostat.get_deadband() == 3
    assert thermostat.get_setpoint_limits() == (55, 99)
    assert thermostat.has_variable_fan_speed() is True
    assert thermostat.get_unit() == "F"
    assert thermostat.get_humidity_setpoint_limits() == (0.35, 0.65)
    assert thermostat.get_fan_mode() == "Circulate"
    assert thermostat.get_fan_modes() == ["Auto", "On", "Circulate"]
    assert thermostat.get_current_compressor_speed() == 0.0
    assert thermostat.get_requested_compressor_speed() == 0.0
    assert thermostat.has_dehumidify_support() is True
    assert thermostat.has_humidify_support() is False
    assert thermostat.has_emergency_heat() is False
    assert thermostat.get_system_status() == "System Idle"
    assert thermostat.has_air_cleaner() is True
    assert thermostat.is_blower_active() is False

    zone_ids = thermostat.get_zone_ids()
    assert zone_ids == [88888888]


async def test_xl824_2(aiohttp_session: aiohttp.ClientSession) -> None:
    """Get methods for an xl824 thermostat."""
    nexia = NexiaHome(aiohttp_session)
    devices_json = json.loads(await load_fixture("mobile_house_xl624.json"))
    nexia.update_from_json(devices_json)

    thermostat_ids = nexia.get_thermostat_ids()
    assert thermostat_ids == [2222222, 3333333]
    thermostat = nexia.get_thermostat_by_id(3333333)

    assert thermostat.get_model() == "XL824"
    assert thermostat.get_firmware() == "5.9.1"
    assert thermostat.get_dev_build_number() == "1581314625"
    assert thermostat.get_device_id() == "01573380"
    assert thermostat.get_type() == "XL824"
    assert thermostat.get_name() == "Upstairs"
    assert thermostat.get_deadband() == 3
    assert thermostat.get_setpoint_limits() == (55, 99)
    assert thermostat.has_variable_fan_speed() is True
    assert thermostat.get_unit() == "F"
    assert thermostat.get_humidity_setpoint_limits() == (0.35, 0.65)
    assert thermostat.get_fan_mode() == "Circulate"
    assert thermostat.get_fan_modes() == ["Auto", "On", "Circulate"]
    assert thermostat.get_current_compressor_speed() == 0.0
    assert thermostat.get_requested_compressor_speed() == 0.0
    assert thermostat.has_dehumidify_support() is True
    assert thermostat.has_humidify_support() is False
    assert thermostat.has_emergency_heat() is False
    assert thermostat.get_system_status() == "System Idle"
    assert thermostat.has_air_cleaner() is True
    assert thermostat.is_blower_active() is False

    zone_ids = thermostat.get_zone_ids()
    assert zone_ids == [99999999]


async def test_basic(aiohttp_session):
    """Basic tests for NexiaHome."""
    nexia = NexiaHome(aiohttp_session)
    devices_json = json.loads(await load_fixture("mobile_houses_123456.json"))
    nexia.update_from_json(devices_json)

    assert nexia.get_name() == "Hidden"
    thermostat_ids = nexia.get_thermostat_ids()
    assert thermostat_ids == [2059661, 2059676, 2293892, 2059652]


async def test_basic_issue_33758(aiohttp_session):
    """Basic tests for NexiaHome."""
    nexia = NexiaHome(aiohttp_session)
    devices_json = json.loads(await load_fixture("mobile_house_issue_33758.json"))
    nexia.update_from_json(devices_json)

    assert nexia.get_name() == "Hidden"
    thermostat_ids = nexia.get_thermostat_ids()
    assert thermostat_ids == [12345678]


async def test_zone_issue_33968_zone_83037337(aiohttp_session):
    """Tests for nexia thermostat zone that is cooling."""
    nexia = NexiaHome(aiohttp_session)
    devices_json = json.loads(await load_fixture("mobile_house_issue_33968.json"))
    nexia.update_from_json(devices_json)

    thermostat = nexia.get_thermostat_by_id(1690380)
    zone = thermostat.get_zone_by_id(83037337)

    assert zone.thermostat == thermostat

    assert zone.get_name() == "Family Room"
    assert zone.get_cooling_setpoint() == 77
    assert zone.get_heating_setpoint() == 74
    assert zone.get_current_mode() == "COOL"
    assert zone.get_requested_mode() == "COOL"
    assert zone.get_presets() == ["None", "Home", "Away", "Sleep"]
    assert zone.get_preset() == "None"
    assert zone.get_status() == "Damper Closed"
    assert zone.get_setpoint_status() == "Permanent Hold"
    assert zone.is_calling() is False
    assert zone.is_in_permanent_hold() is True


async def test_zone_issue_33968_zone_83037340(aiohttp_session):
    """Tests for nexia thermostat zone that is cooling."""
    nexia = NexiaHome(aiohttp_session)
    devices_json = json.loads(await load_fixture("mobile_house_issue_33968.json"))
    nexia.update_from_json(devices_json)

    thermostat = nexia.get_thermostat_by_id(1690380)
    zone = thermostat.get_zone_by_id(83037340)

    assert zone.thermostat == thermostat

    assert zone.get_name() == "Office"
    assert zone.get_cooling_setpoint() == 77
    assert zone.get_heating_setpoint() == 74
    assert zone.get_current_mode() == "COOL"
    assert zone.get_requested_mode() == "COOL"
    assert zone.get_presets() == ["None", "Home", "Away", "Sleep"]
    assert zone.get_preset() == "None"
    assert zone.get_status() == "Damper Open"
    assert zone.get_setpoint_status() == "Permanent Hold"
    assert zone.is_calling() is True
    assert zone.is_in_permanent_hold() is True


async def test_zone_issue_33968_zone_83037343(
    aiohttp_session: aiohttp.ClientSession,
) -> None:
    """Tests for nexia thermostat zone that is cooling."""
    nexia = NexiaHome(aiohttp_session)
    devices_json = json.loads(await load_fixture("mobile_house_issue_33968.json"))
    nexia.update_from_json(devices_json)

    thermostat = nexia.get_thermostat_by_id(1690380)
    zone = thermostat.get_zone_by_id(83037343)

    assert zone.thermostat == thermostat

    assert zone.get_name() == "Master"
    assert zone.get_cooling_setpoint() == 77
    assert zone.get_heating_setpoint() == 68
    assert zone.get_current_mode() == "COOL"
    assert zone.get_requested_mode() == "COOL"
    assert zone.get_presets() == ["None", "Home", "Away", "Sleep"]
    assert zone.get_preset() == "None"
    assert zone.get_status() == "Damper Open"
    assert zone.get_setpoint_status() == "Permanent Hold"
    assert zone.is_calling() is True
    assert zone.is_in_permanent_hold() is True


async def test_zone_issue_33758(aiohttp_session: aiohttp.ClientSession) -> None:
    """Tests for nexia thermostat zone relieving air."""
    nexia = NexiaHome(aiohttp_session)
    devices_json = json.loads(await load_fixture("mobile_house_issue_33758.json"))
    nexia.update_from_json(devices_json)

    thermostat = nexia.get_thermostat_by_id(12345678)
    zone = thermostat.get_zone_by_id(12345678)

    assert zone.thermostat == thermostat

    assert zone.get_name() == "Thermostat NativeZone"
    assert zone.get_cooling_setpoint() == 73
    assert zone.get_heating_setpoint() == 68
    assert zone.get_current_mode() == "AUTO"
    assert zone.get_requested_mode() == "AUTO"
    assert zone.get_presets() == ["None", "Home", "Away", "Sleep"]
    assert zone.get_preset() == "None"
    assert zone.get_status() == "Idle"
    assert zone.get_setpoint_status() == "Run Schedule - None"
    assert zone.is_calling() is False
    assert zone.is_in_permanent_hold() is False


async def test_zone_relieving_air(aiohttp_session):
    """Tests for nexia thermostat zone relieving air."""
    nexia = NexiaHome(aiohttp_session)
    devices_json = json.loads(await load_fixture("mobile_houses_123456.json"))
    nexia.update_from_json(devices_json)

    thermostat = nexia.get_thermostat_by_id(2293892)
    zone = thermostat.get_zone_by_id(83394133)

    assert zone.thermostat == thermostat

    assert zone.get_name() == "Bath Closet"
    assert zone.get_cooling_setpoint() == 79
    assert zone.get_heating_setpoint() == 63
    assert zone.get_current_mode() == "AUTO"
    assert zone.get_requested_mode() == "AUTO"
    assert zone.get_presets() == ["None", "Home", "Away", "Sleep"]
    assert zone.get_preset() == "None"
    assert zone.get_status() == "Relieving Air"
    assert zone.get_setpoint_status() == "Permanent Hold"
    assert zone.is_calling() is True
    assert zone.is_in_permanent_hold() is True


async def test_zone_cooling_air(aiohttp_session):
    """Tests for nexia thermostat zone cooling."""
    nexia = NexiaHome(aiohttp_session)
    devices_json = json.loads(await load_fixture("mobile_houses_123456.json"))
    nexia.update_from_json(devices_json)

    thermostat = nexia.get_thermostat_by_id(2293892)
    zone = thermostat.get_zone_by_id(83394130)

    assert zone.get_name() == "Master"
    assert zone.get_cooling_setpoint() == 71
    assert zone.get_heating_setpoint() == 63
    assert zone.get_current_mode() == "AUTO"
    assert zone.get_requested_mode() == "AUTO"
    assert zone.get_presets() == ["None", "Home", "Away", "Sleep"]
    assert zone.get_preset() == "None"
    assert zone.get_status() == "Damper Open"
    assert zone.get_setpoint_status() == "Permanent Hold"
    assert zone.is_calling() is True
    assert zone.is_in_permanent_hold() is True


async def test_zone_idle(aiohttp_session):
    """Tests for nexia thermostat zone idle."""
    nexia = NexiaHome(aiohttp_session)
    devices_json = json.loads(await load_fixture("mobile_houses_123456.json"))
    nexia.update_from_json(devices_json)

    thermostat = nexia.get_thermostat_by_id(2059661)
    zone = thermostat.get_zone_by_id(83261002)

    assert zone.get_name() == "Living East"
    assert zone.get_cooling_setpoint() == 79
    assert zone.get_heating_setpoint() == 63
    assert zone.get_current_mode() == "AUTO"
    assert zone.get_requested_mode() == "AUTO"
    assert zone.get_presets() == ["None", "Home", "Away", "Sleep"]
    assert zone.get_preset() == "None"
    assert zone.get_status() == "Idle"
    assert zone.get_setpoint_status() == "Permanent Hold"
    assert zone.is_calling() is False
    assert zone.is_in_permanent_hold() is True


async def test_xl824_idle(aiohttp_session):
    """Tests for nexia xl824 zone idle."""
    nexia = NexiaHome(aiohttp_session)
    devices_json = json.loads(await load_fixture("mobile_house_xl624.json"))
    nexia.update_from_json(devices_json)

    thermostat_ids = nexia.get_thermostat_ids()
    assert thermostat_ids == [2222222, 3333333]
    thermostat = nexia.get_thermostat_by_id(3333333)
    zone = thermostat.get_zone_by_id(99999999)

    assert zone.get_name() == "Upstairs NativeZone"
    assert zone.get_cooling_setpoint() == 74
    assert zone.get_heating_setpoint() == 62
    assert zone.get_current_mode() == "COOL"
    assert zone.get_requested_mode() == "COOL"
    assert zone.get_presets() == ["None", "Home", "Away", "Sleep"]
    assert zone.get_preset() == "None"
    assert zone.get_status() == "Idle"
    assert zone.get_setpoint_status() == "Permanent Hold"
    assert zone.is_calling() is False
    assert zone.is_in_permanent_hold() is True


async def test_single_zone(aiohttp_session: aiohttp.ClientSession) -> None:
    """Test thermostat with only a single (Native) zone."""
    nexia = NexiaHome(aiohttp_session)
    devices_json = json.loads(await load_fixture("single_zone_xl1050.json"))
    nexia.update_from_json(devices_json)

    thermostat_ids = nexia.get_thermostat_ids()
    assert thermostat_ids == [345678]
    thermostat = nexia.get_thermostat_by_id(345678)
    zone = thermostat.get_zone_by_id(234567)

    assert zone.get_name() == "Thermostat 1 NativeZone"
    assert zone.get_cooling_setpoint() == 73
    assert zone.get_heating_setpoint() == 68
    assert zone.get_current_mode() == "AUTO"
    assert zone.get_requested_mode() == "AUTO"
    assert zone.get_presets() == ["None", "Home", "Away", "Sleep"]
    assert zone.get_preset() == "None"
    assert zone.get_status() == "Idle"
    assert zone.get_setpoint_status() == "Permanent Hold"
    assert zone.is_calling() is True
    assert zone.is_in_permanent_hold() is True

    # No sensors
    sensors = zone.get_sensors()
    assert len(sensors) == 0
    assert len(zone.get_active_sensor_ids()) == 0
    with pytest.raises(
        AttributeError,
        match="RoomIQ sensors not supported in zone Thermostat 1 NativeZone",
    ):
        await zone.select_room_iq_sensors([76543210])

    with pytest.raises(
        AttributeError,
        match="RoomIQ sensors not supported in zone Thermostat 1 NativeZone",
    ):
        zone.get_sensor_by_id(87654321)


async def test_single_zone_system_off(aiohttp_session: aiohttp.ClientSession) -> None:
    """Test thermostat with only a single (Native) zone."""
    nexia = NexiaHome(aiohttp_session)
    devices_json = json.loads(await load_fixture("single_zone_xl1050_system_off.json"))
    nexia.update_from_json(devices_json)

    thermostat_ids = nexia.get_thermostat_ids()
    assert thermostat_ids == [345678]
    thermostat = nexia.get_thermostat_by_id(345678)
    assert thermostat.get_model() == "XL1050"
    assert thermostat.get_firmware() == "5.9.3"
    assert thermostat.get_dev_build_number() == "1599485560"
    assert thermostat.get_device_id() == "028E05EC"
    assert thermostat.get_type() == "XL1050"
    assert thermostat.get_name() == "Thermostat 1"
    assert thermostat.get_deadband() == 3
    assert thermostat.get_setpoint_limits() == (55, 99)
    assert thermostat.get_variable_fan_speed_limits() == (0.35, 1.0)
    assert thermostat.get_unit() == "F"
    assert thermostat.get_humidity_setpoint_limits() == (0.35, 0.65)
    assert thermostat.get_fan_mode(), "Auto"
    assert thermostat.get_fan_modes() == ["Auto", "On", "Circulate"]
    assert thermostat.get_outdoor_temperature() == 64.0
    assert thermostat.get_relative_humidity() == 0.59
    assert thermostat.get_current_compressor_speed() == 0.0
    assert thermostat.get_requested_compressor_speed() == 0.0
    assert thermostat.get_fan_speed_setpoint() == 0.5
    assert thermostat.get_dehumidify_setpoint() == 0.50
    assert thermostat.has_dehumidify_support() is True
    assert thermostat.has_humidify_support() is False
    assert thermostat.has_emergency_heat() is True
    assert thermostat.get_system_status() == "System Off"
    assert thermostat.has_air_cleaner() is True
    assert thermostat.get_air_cleaner_mode() == "auto"
    assert thermostat.is_blower_active() is False

    zone = thermostat.get_zone_by_id(234567)

    assert zone.get_name() == "Thermostat 1 NativeZone"
    assert zone.get_cooling_setpoint() == 73
    assert zone.get_heating_setpoint() == 68
    assert zone.get_current_mode() == "AUTO"
    assert zone.get_requested_mode() == "AUTO"
    assert zone.get_presets() == ["None", "Home", "Away", "Sleep"]
    assert zone.get_preset() == "None"
    assert zone.get_status() == "Idle"
    assert zone.get_setpoint_status() == "Permanent Hold"
    assert zone.is_calling() is True
    assert zone.is_in_permanent_hold() is True


async def test_automations(
    aiohttp_session: aiohttp.ClientSession, mock_aioresponse: aioresponses
) -> None:
    """Get methods for an active thermostat."""
    nexia = NexiaHome(aiohttp_session)
    text = await load_fixture("mobile_houses_123456.json")
    devices_json = json.loads(text)
    nexia.update_from_json(devices_json)

    automation_ids = nexia.get_automation_ids()
    assert automation_ids == [
        3467876,
        3467870,
        3452469,
        3452472,
        3454776,
        3454774,
        3486078,
        3486091,
    ]

    automation_one = nexia.get_automation_by_id(3467876)

    assert automation_one.name == "Away for 12 Hours"
    assert automation_one.description == (
        "When IFTTT activates the automation Upstairs West Wing will "
        "permanently hold the heat to 62.0 and cool to 83.0 AND "
        "Downstairs East Wing will permanently hold the heat to 62.0 "
        "and cool to 83.0 AND Downstairs West Wing will permanently "
        "hold the heat to 62.0 and cool to 83.0 AND Activate the mode "
        "named 'Away 12' AND Master Suite will permanently hold the "
        "heat to 62.0 and cool to 83.0"
    )
    assert automation_one.enabled is True
    assert automation_one.automation_id == 3467876

    mock_aioresponse.post(
        "https://www.mynexia.com/mobile/automations/3467876/activate",
        payload={
            "success": True,
            "error": None,
        },
    )
    await automation_one.activate()


async def test_x850_grouped(aiohttp_session: aiohttp.ClientSession) -> None:
    """Get methods for an xl850 grouped thermostat."""
    nexia = NexiaHome(aiohttp_session)
    devices_json = json.loads(await load_fixture("grouped_xl850.json"))
    nexia.update_from_json(devices_json)

    thermostat_ids = nexia.get_thermostat_ids()
    assert thermostat_ids == [2323232]
    thermostat = nexia.get_thermostat_by_id(2323232)

    assert thermostat.get_model() == "XL850"
    assert thermostat.get_firmware() == "5.9.7"
    assert thermostat.get_dev_build_number() == "XXXXXXXXXXXXXXXXX"
    assert thermostat.get_device_id() == "XXXXXXXXXXX"
    assert thermostat.get_type() == "XL850"
    assert thermostat.get_name() == "Hallway Control"
    assert thermostat.get_deadband() == 3
    assert thermostat.get_setpoint_limits() == (55, 99)
    assert thermostat.has_variable_fan_speed() is True
    assert thermostat.get_unit() == "F"
    assert thermostat.get_humidity_setpoint_limits() == (0.10, 0.65)
    assert thermostat.get_fan_mode() == "Circulate"
    assert thermostat.get_fan_modes() == ["Auto", "On", "Circulate"]
    assert thermostat.get_current_compressor_speed() == 1.0
    assert thermostat.get_requested_compressor_speed() == 1.0
    assert thermostat.has_dehumidify_support() is True
    assert thermostat.has_humidify_support() is True
    assert thermostat.has_emergency_heat() is False
    assert thermostat.get_system_status() == "Cooling"
    assert thermostat.has_air_cleaner() is True
    assert thermostat.is_blower_active() is True

    zone_ids = thermostat.get_zone_ids()
    assert zone_ids == [343434334]
    zone = thermostat.get_zone_by_id(343434334)

    assert zone.get_name() == "Hallway Control NativeZone"
    assert zone.get_cooling_setpoint() == 75
    assert zone.get_heating_setpoint() == 68
    assert zone.get_current_mode() == "COOL"
    assert zone.get_requested_mode() == "COOL"
    assert zone.get_presets() == ["None", "Home", "Away", "Sleep"]
    assert zone.get_preset() == "None"
    assert zone.get_status() == "Idle"
    assert zone.get_setpoint_status() == "Permanent Hold"
    assert zone.is_calling() is True
    assert zone.is_in_permanent_hold() is True


async def test_issue_79891(aiohttp_session: aiohttp.ClientSession) -> None:
    """Get methods issue 79891 thermostat.

    https://github.com/home-assistant/core/issues/79891
    """
    nexia = NexiaHome(aiohttp_session)
    devices_json = json.loads(await load_fixture("issue_79891.json"))
    nexia.update_from_json(devices_json)

    thermostat_ids = nexia.get_thermostat_ids()
    assert thermostat_ids == [2473073, 2222249]

    # Thermostat 1
    thermostat = nexia.get_thermostat_by_id(2473073)
    assert thermostat.get_model() == "XL824"
    assert thermostat.get_firmware() == "5.9.6"
    assert thermostat.get_dev_build_number() == "1614575015"
    assert thermostat.get_device_id() == "01695948"
    assert thermostat.get_type() == "XL824"
    assert thermostat.get_name() == "First floor"
    assert thermostat.get_deadband() == 2
    assert thermostat.get_setpoint_limits() == (13.0, 37.0)
    assert thermostat.has_variable_fan_speed() is False
    assert thermostat.get_unit() == "C"
    assert thermostat.get_humidity_setpoint_limits() == (0.35, 0.65)
    assert thermostat.get_fan_mode() == "Auto"
    assert thermostat.get_fan_modes() == ["Auto", "On", "Circulate"]
    assert thermostat.get_current_compressor_speed() == 0
    assert thermostat.get_requested_compressor_speed() == 0
    assert thermostat.has_dehumidify_support() is True
    assert thermostat.has_humidify_support() is False
    assert thermostat.has_emergency_heat() is False
    assert thermostat.get_system_status() == "System Idle"
    assert thermostat.has_air_cleaner() is True
    assert thermostat.is_blower_active() is False

    zone_ids = thermostat.get_zone_ids()
    assert zone_ids == [83496154]
    zone = thermostat.get_zone_by_id(83496154)

    assert zone.get_name() == "First floor NativeZone"
    assert zone.get_cooling_setpoint() == 26.5
    assert zone.get_heating_setpoint() == 22.0
    assert zone.get_current_mode() == "AUTO"
    assert zone.get_requested_mode() == "AUTO"
    assert zone.get_presets() == ["None", "Home", "Away", "Sleep"]
    assert zone.get_preset() == "None"
    assert zone.get_status() == "Idle"
    assert zone.get_setpoint_status() == "Run Schedule - None"
    assert zone.is_calling() is False
    assert zone.is_in_permanent_hold() is False

    # Thermostat 2
    thermostat = nexia.get_thermostat_by_id(2222249)
    assert thermostat.get_model() == "XR724"
    assert thermostat.get_firmware() == "02.72.00"
    assert thermostat.get_dev_build_number() is None
    assert thermostat.get_device_id() == "0080E1CB6FF0"
    assert thermostat.get_type() == "XR724"
    assert thermostat.get_name() == "Second floor"
    assert thermostat.get_deadband() == 2
    assert thermostat.get_setpoint_limits() == (13.0, 37.0)
    assert thermostat.has_variable_fan_speed() is False
    assert thermostat.get_unit() == "C"
    assert thermostat.get_humidity_setpoint_limits() == (0.10, 0.65)
    assert thermostat.get_fan_mode() == "Auto"
    assert thermostat.get_fan_modes() == ["Circulate", "Auto", "On"]
    assert thermostat.get_current_compressor_speed() == 0
    assert thermostat.get_requested_compressor_speed() == 0
    assert thermostat.has_dehumidify_support() is False
    assert thermostat.has_humidify_support() is False
    assert thermostat.has_emergency_heat() is False
    assert thermostat.get_system_status() == "System Idle"
    assert thermostat.has_air_cleaner() is False
    assert thermostat.is_blower_active() is False

    zone_ids = thermostat.get_zone_ids()
    assert zone_ids == [1]
    zone = thermostat.get_zone_by_id(1)

    assert zone.get_name() == "default"
    assert zone.get_cooling_setpoint() == 27.0
    assert zone.get_heating_setpoint() == 20.0
    assert zone.get_current_mode() == "AUTO"
    assert zone.get_requested_mode() == "AUTO"
    assert zone.get_presets() == ["Off", "Auto", "Cool", "Heat"]
    assert zone.get_preset() == "Auto"
    assert zone.get_status() == "auto"
    assert zone.get_setpoint_status() == "Run Schedule - Auto"
    assert zone.is_calling() is True
    assert zone.is_in_permanent_hold() is False


async def test_new_xl1050(aiohttp_session: aiohttp.ClientSession) -> None:
    """Get with a new xl1050."""
    nexia = NexiaHome(aiohttp_session)
    devices_json = json.loads(await load_fixture("xl1050.json"))
    nexia.update_from_json(devices_json)

    thermostat_ids = nexia.get_thermostat_ids()
    assert thermostat_ids == [4122267, 2059676, 4125886, 2059652]

    # Thermostat 1
    thermostat = nexia.get_thermostat_by_id(4122267)
    assert thermostat.get_model() == "XL1050"
    assert thermostat.get_firmware() == "5.9.6"
    assert thermostat.get_dev_build_number() == "1614588140"
    assert thermostat.get_device_id() == "02868F20"
    assert thermostat.get_type() == "XL1050"
    assert thermostat.get_name() == "Downstairs East Wing"
    assert thermostat.get_deadband() == 3
    assert thermostat.get_setpoint_limits() == (55, 99)
    assert thermostat.has_variable_fan_speed() is True
    assert thermostat.get_unit() == "F"
    assert thermostat.get_humidity_setpoint_limits() == (0.35, 0.65)
    assert thermostat.get_fan_mode() == "Auto"
    assert thermostat.get_fan_modes() == ["Auto", "On", "Circulate"]
    assert thermostat.get_current_compressor_speed() == 0
    assert thermostat.get_requested_compressor_speed() == 0
    assert thermostat.has_dehumidify_support() is True
    assert thermostat.has_humidify_support() is False
    assert thermostat.has_emergency_heat() is False
    assert thermostat.get_system_status() == "System Idle"
    assert thermostat.has_air_cleaner() is True
    assert thermostat.is_blower_active() is False

    zone_ids = thermostat.get_zone_ids()
    assert zone_ids == [84398305, 84398308, 84398311, 84398314]
    zone = thermostat.get_zone_by_id(84398305)

    assert zone.get_name() == "Living East"
    assert zone.get_cooling_setpoint() == 75
    assert zone.get_heating_setpoint() == 55
    assert zone.get_current_mode() == "COOL"
    assert zone.get_requested_mode() == "COOL"
    assert zone.get_temperature() == 72
    assert zone.get_presets() == ["None", "Home", "Away", "Sleep"]
    assert zone.get_preset() == "None"
    assert zone.get_status() == "Idle"
    assert zone.get_setpoint_status() == "Run Schedule - None"
    assert zone.is_calling() is False
    zone.check_heat_cool_setpoints(70, 76)
    assert zone.is_in_permanent_hold() is False

    # Sensors
    thermostat = nexia.get_thermostat_by_id(2059676)

    assert thermostat.get_zone_ids() == [83261015, 83261018, 84243806, 83535112]
    zone = thermostat.get_zone_by_id(83261015)
    sensors = zone.get_sensors()

    assert len(sensors) == 1
    sensor = sensors[0]
    assert sensor.id == 16800389
    assert sensor.name == "Living West"
    assert sensor.type == "thermostat"
    assert sensor.serial_number == "NativeIDTUniqueID"
    assert sensor.weight == 1.0
    assert sensor.temperature == 70
    assert sensor.temperature_valid is True
    assert sensor.humidity == 42
    assert sensor.humidity_valid is True
    assert sensor.has_online is False
    assert sensor.has_battery is False


async def test_new_xl824(aiohttp_session: aiohttp.ClientSession) -> None:
    """Get with a new xl824."""
    nexia = NexiaHome(aiohttp_session)
    devices_json = json.loads(await load_fixture("xl824.json"))
    nexia.update_from_json(devices_json)

    thermostat_ids = nexia.get_thermostat_ids()
    assert thermostat_ids == [1841910]

    # Thermostat 1
    thermostat = nexia.get_thermostat_by_id(1841910)
    assert thermostat.get_model() == "XL824"
    assert thermostat.get_firmware() == "5.9.6"
    assert thermostat.get_dev_build_number() == "1614575015"
    assert thermostat.get_device_id() == "0160F840"
    assert thermostat.get_type() == "XL824"
    assert thermostat.get_name() == "Office Thermostat"
    assert thermostat.get_deadband() == 3
    assert thermostat.get_setpoint_limits() == (55, 99)
    assert thermostat.has_variable_fan_speed() is True
    assert thermostat.get_unit() == "F"
    assert thermostat.get_humidity_setpoint_limits() == (0.1, 0.45)
    assert thermostat.get_fan_mode() == "On"
    assert thermostat.get_fan_modes() == ["Auto", "On", "Circulate"]
    assert thermostat.get_current_compressor_speed() == 0
    assert thermostat.get_requested_compressor_speed() == 0
    assert thermostat.has_dehumidify_support() is False
    assert thermostat.has_humidify_support() is True
    assert thermostat.has_emergency_heat() is False
    assert thermostat.get_system_status() == "Fan Running"
    assert thermostat.has_air_cleaner() is True
    assert thermostat.is_blower_active() is True
    assert thermostat.is_online is True

    zone_ids = thermostat.get_zone_ids()
    assert zone_ids == [83128724]
    zone = thermostat.get_zone_by_id(83128724)

    assert zone.get_name() == "Office Thermostat NativeZone"
    assert zone.get_cooling_setpoint() == 99
    assert zone.get_heating_setpoint() == 55
    assert zone.get_current_mode() == "OFF"
    assert zone.get_requested_mode() == "OFF"
    assert zone.get_presets() == ["None", "Home", "Away", "Sleep"]
    assert zone.get_preset() == "None"
    assert zone.get_status() == "Idle"
    assert zone.get_setpoint_status() == "Permanent Hold"
    assert zone.is_calling() is True
    assert zone.is_in_permanent_hold() is True


async def test_system_offline(aiohttp_session: aiohttp.ClientSession) -> None:
    """Get a system offline."""
    nexia = NexiaHome(aiohttp_session)
    devices_json = json.loads(await load_fixture("system_offline.json"))
    nexia.update_from_json(devices_json)

    thermostat_ids = nexia.get_thermostat_ids()
    assert thermostat_ids == [2224092, 3887969, 3295333]

    # Thermostat 1
    thermostat = nexia.get_thermostat_by_id(2224092)
    assert thermostat.get_model() == "XL1050"
    assert thermostat.get_firmware() == "5.9.6"
    assert thermostat.get_dev_build_number() == "1614588140"
    assert thermostat.get_device_id() == "02863D94"
    assert thermostat.get_type() == "XL1050"
    assert thermostat.get_name() == "Game Room"
    assert thermostat.get_deadband() == 3
    assert thermostat.get_setpoint_limits() == (55, 99)
    assert thermostat.has_variable_fan_speed() is True
    assert thermostat.get_unit() == "F"
    assert thermostat.get_humidity_setpoint_limits() == (0.35, 0.65)
    assert thermostat.get_fan_mode() == "Auto"
    assert thermostat.get_fan_modes() == ["Auto", "On", "Circulate"]
    assert thermostat.get_current_compressor_speed() == 0.35
    assert thermostat.get_requested_compressor_speed() == 0.35
    assert thermostat.has_dehumidify_support() is True
    assert thermostat.has_humidify_support() is False
    assert thermostat.has_emergency_heat() is False
    assert thermostat.get_system_status() == "NOT CONNECTED"
    assert thermostat.has_air_cleaner() is True
    assert thermostat.is_blower_active() is True
    assert thermostat.is_online is False

    zone_ids = thermostat.get_zone_ids()
    assert zone_ids == [83354736, 83354739, 83354742, 83354745]
    zone = thermostat.get_zone_by_id(83354736)

    assert zone.get_name() == "Game Room"
    assert zone.get_cooling_setpoint() == 75
    assert zone.get_heating_setpoint() == 55
    assert zone.get_current_mode() == "COOL"
    assert zone.get_requested_mode() == "COOL"
    assert zone.get_presets() == ["None", "Home", "Away", "Sleep"]
    assert zone.get_preset() == "None"
    assert zone.get_status() == "Damper Open"
    assert zone.get_setpoint_status() == "Permanent Hold"
    assert zone.is_calling() is True
    assert zone.is_in_permanent_hold() is True


async def test_emergency_heat(aiohttp_session: aiohttp.ClientSession) -> None:
    """Test emergency heat."""
    nexia = NexiaHome(aiohttp_session)
    devices_json = json.loads(await load_fixture("eme_heat.json"))
    nexia.update_from_json(devices_json)

    thermostat_ids = nexia.get_thermostat_ids()
    assert thermostat_ids == [3983351]

    # Thermostat 1
    thermostat = nexia.get_thermostat_by_id(3983351)
    assert thermostat.get_model() == "XL850"
    assert thermostat.get_firmware() == "5.9.6"
    assert thermostat.get_dev_build_number() == "1614581867"
    assert thermostat.get_device_id() == "00D68470"
    assert thermostat.get_type() == "XL850"
    assert thermostat.get_name() == "XL850 Home"
    assert thermostat.get_deadband() == 3
    assert thermostat.get_setpoint_limits() == (55, 99)
    assert thermostat.has_variable_fan_speed() is True
    assert thermostat.get_unit() == "F"
    assert thermostat.get_humidity_setpoint_limits() == (0.10, 0.65)
    assert thermostat.get_fan_mode() == "On"
    assert thermostat.get_fan_modes() == ["Auto", "On", "Circulate"]
    assert thermostat.get_current_compressor_speed() == 0
    assert thermostat.get_requested_compressor_speed() == 0
    assert thermostat.has_dehumidify_support() is True
    assert thermostat.has_humidify_support() is True
    assert thermostat.has_emergency_heat() is True
    assert thermostat.get_system_status() == "Fan Running"
    assert thermostat.has_air_cleaner() is True
    assert thermostat.is_blower_active() is True
    assert thermostat.is_online is True

    zone_ids = thermostat.get_zone_ids()
    assert zone_ids == [84326108]
    zone = thermostat.get_zone_by_id(84326108)

    assert zone.get_name() == "XL850 Home NativeZone"
    assert zone.get_cooling_setpoint() == 99
    assert zone.get_heating_setpoint() == 68
    assert zone.get_current_mode() == "HEAT"
    assert zone.get_requested_mode() == "HEAT"
    assert zone.get_presets() == ["None", "Home", "Away", "Sleep"]
    assert zone.get_preset() == "None"
    assert zone.get_status() == "Idle"
    assert zone.get_setpoint_status() == "Run Schedule - None"
    assert zone.is_calling() is True
    assert zone.is_in_permanent_hold() is False


async def test_humidity_and_fan_mode(
    aiohttp_session: aiohttp.ClientSession, mock_aioresponse: aioresponses
) -> None:
    """Tests for preventing an API timeout when updating humidity
    and fan modes to the same value
    """
    nexia = NexiaHome(aiohttp_session)
    devices_json = json.loads(await load_fixture("mobile_house_issue_33758.json"))
    nexia.update_from_json(devices_json)

    thermostat: NexiaThermostat = nexia.get_thermostat_by_id(12345678)
    devices = _extract_devices_from_houses_json(devices_json)

    assert thermostat.has_dehumidify_support() is True
    assert thermostat.has_humidify_support() is True
    assert thermostat.get_humidify_setpoint_limits() == (0.10, 0.45)
    assert thermostat.get_dehumidify_setpoint_limits() == (0.35, 0.65)

    mock_aioresponse.post(
        "https://www.mynexia.com/mobile/xxl_thermostats/12345678/fan_mode",
        payload={"result": devices[0]},
    )
    mock_aioresponse.post(
        "https://www.mynexia.com/mobile/xxl_thermostats/12345678/humidify",
        payload={"result": devices[0]},
    )
    mock_aioresponse.post(
        "https://www.mynexia.com/mobile/xxl_thermostats/12345678/dehumidify",
        payload={"result": devices[0]},
    )

    with pytest.raises(KeyError, match="Invalid fan mode.*"):
        await thermostat.set_fan_mode("DOES_NOT_EXIST")

    # Attempting to set to the same value should not trigger an API call
    await thermostat.set_fan_mode("Auto")
    assert not mock_aioresponse.requests.get(
        ("POST", "https://www.mynexia.com/mobile/xxl_thermostats/12345678/fan_mode")
    )

    # Attempting to set to different value should trigger an API call
    await thermostat.set_fan_mode("On")
    assert mock_aioresponse.requests.get(
        (
            "POST",
            URL("https://www.mynexia.com/mobile/xxl_thermostats/12345678/fan_mode"),
        )
    )

    # Attempting to set to the same value should not trigger an API call
    await thermostat.set_humidity_setpoints(
        humidify_setpoint=0.4, dehumidify_setpoint=0.55
    )
    assert not mock_aioresponse.requests.get(
        (
            "POST",
            URL("https://www.mynexia.com/mobile/xxl_thermostats/12345678/humidify"),
        )
    )
    assert not mock_aioresponse.requests.get(
        (
            "POST",
            URL("https://www.mynexia.com/mobile/xxl_thermostats/12345678/dehumidify"),
        )
    )

    # Attempting to set to different value should trigger an API call
    await thermostat.set_humidity_setpoints(
        humidify_setpoint=0.15, dehumidify_setpoint=0.60
    )
    request = mock_aioresponse.requests.get(
        (
            "POST",
            URL("https://www.mynexia.com/mobile/xxl_thermostats/12345678/humidify"),
        )
    )
    assert request is not None
    first_request = request[0]
    assert first_request.kwargs["json"]["value"] == "0.15"
    request = mock_aioresponse.requests.get(
        (
            "POST",
            URL("https://www.mynexia.com/mobile/xxl_thermostats/12345678/dehumidify"),
        )
    )
    assert request is not None
    first_request = request[0]
    assert first_request.kwargs["json"]["value"] == "0.6"

    mock_aioresponse.requests.clear()
    mock_aioresponse.post(
        "https://www.mynexia.com/mobile/xxl_thermostats/12345678/humidify",
        payload={"result": devices[0]},
    )
    mock_aioresponse.post(
        "https://www.mynexia.com/mobile/xxl_thermostats/12345678/dehumidify",
        payload={"result": devices[0]},
    )
    # Attempting to set to an out of range value should clamp to the nearest valid value
    await thermostat.set_humidity_setpoints(
        humidify_setpoint=0.242, dehumidify_setpoint=0.652
    )
    request = mock_aioresponse.requests.get(
        (
            "POST",
            URL("https://www.mynexia.com/mobile/xxl_thermostats/12345678/humidify"),
        )
    )
    assert request is not None
    first_request = request[0]
    assert first_request.kwargs["json"]["value"] == "0.25"
    request = mock_aioresponse.requests.get(
        (
            "POST",
            URL("https://www.mynexia.com/mobile/xxl_thermostats/12345678/dehumidify"),
        )
    )
    assert request is not None
    first_request = request[0]
    assert first_request.kwargs["json"]["value"] == "0.65"


async def test_sensor_access(
    aiohttp_session: aiohttp.ClientSession, mock_aioresponse: aioresponses
) -> None:
    """Test sensor access methods."""
    persist_file = Path("nexia_config_test.conf")
    nexia = NexiaHome(aiohttp_session, house_id=2582941, state_file=persist_file)
    logging.getLogger("nexia").setLevel(logging.DEBUG)
    mock_aioresponse.post(
        "https://www.mynexia.com/mobile/accounts/sign_in",
        payload={
            "success": True,
            "error": None,
            "result": {
                "mobile_id": 5400000,
                "api_key": "10654c0be00000000000000000000000",
                "setup_step": "done",
                "locale": "en_us",
            },
        },
    )
    await nexia.login()

    mock_aioresponse.get(
        "https://www.mynexia.com/mobile/houses/2582941",
        body=await load_fixture("sensors_xl1050_house.json"),
    )
    assert await nexia.update() is not None

    assert nexia.get_thermostat_ids() == [5378307]
    thermostat: NexiaThermostat = nexia.get_thermostat_by_id(5378307)

    assert thermostat.get_zone_ids() == [85034552]
    zone = thermostat.get_zone_by_id(85034552)
    sensors = zone.get_sensors()

    assert len(sensors) == 2
    sensor = sensors[0]
    assert sensor.id == 17687546
    assert sensor.name == "Center"
    assert sensor.type == "thermostat"
    assert sensor.serial_number == "NativeIDTUniqueID"
    assert sensor.weight == 0.5
    assert sensor.temperature == 68
    assert sensor.temperature_valid is True
    assert sensor.humidity == 32
    assert sensor.humidity_valid is True
    assert sensor.has_online is False
    assert sensor.connected is None
    assert sensor.has_battery is False
    assert sensor.battery_level is None
    assert sensor.battery_low is None
    assert sensor.battery_valid is None

    sensor = sensors[1]
    assert sensor.id == 17687549
    assert sensor.name == "Upstairs"
    assert sensor.type == "930"
    assert sensor.serial_number == "2410R5C53X"
    assert sensor.weight == 0.5
    assert sensor.temperature == 69
    assert sensor.temperature_valid is True
    assert sensor.humidity == 32
    assert sensor.humidity_valid is True
    assert sensor.has_online is True
    assert sensor.connected is True
    assert sensor.has_battery is True
    assert sensor.battery_level == 95
    assert sensor.battery_low is False
    assert sensor.battery_valid is True

    assert zone.get_active_sensor_ids() == {17687546, 17687549}

    with pytest.raises(
        KeyError,
        match=r"Sensor ID \(87654321\) not found, valid IDs: 17687546, 17687549",
    ):
        zone.get_sensor_by_id(87654321)

    sensor = zone.get_sensor_by_id(17687549)
    assert sensor.id == 17687549
    assert sensor.name == "Upstairs"
    assert sensor.type == "930"
    assert sensor.serial_number == "2410R5C53X"
    assert sensor.weight == 0.5
    assert sensor.temperature == 69
    assert sensor.temperature_valid is True
    assert sensor.humidity == 32
    assert sensor.humidity_valid is True
    assert sensor.has_online is True
    assert sensor.connected is True
    assert sensor.has_battery is True
    assert sensor.battery_level == 95
    assert sensor.battery_low is False
    assert sensor.battery_valid is True

    # execute no log response code path
    nexia.log_response = False

    # execute no completion code path
    mock_aioresponse.post(
        "https://www.mynexia.com/mobile/xxl_zones/85034552/request_current_sensor_state",
        payload={
            "success": True,
            "error": None,
            "result": {
                "polling_path": "https://www.mynexia.com/backstage/announcements/6a31e745716789b84603036489fe8d1e35ca80fa50000000"
            },
        },
    )
    assert await zone.load_current_sensor_state(max_polls=0) is False

    # execute normal code path
    mock_aioresponse.post(
        "https://www.mynexia.com/mobile/xxl_zones/85034552/request_current_sensor_state",
        payload={
            "success": True,
            "error": None,
            "result": {
                "polling_path": "https://www.mynexia.com/backstage/announcements/6a31e745716789b84603036489fe8d1e35ca80fa5dd381e5"
            },
        },
    )
    mock_aioresponse.get(
        "https://www.mynexia.com/backstage/announcements/6a31e745716789b84603036489fe8d1e35ca80fa5dd381e5",
        body=b"null",
    )
    mock_aioresponse.get(
        "https://www.mynexia.com/backstage/announcements/6a31e745716789b84603036489fe8d1e35ca80fa5dd381e5",
        payload={
            "status": "success, altered to enhance test coverage",
            "options": {},
        },
    )
    assert await zone.load_current_sensor_state(0.01) is True

    mock_aioresponse.get(
        "https://www.mynexia.com/mobile/xxl_thermostats/5378307",
        body=await load_fixture("sensors_xl1050_thermostat.json"),
    )
    await thermostat.refresh_thermostat_data()
    sensors = zone.get_sensors()

    assert len(sensors) == 2
    sensor = sensors[0]
    assert sensor.id == 17687546
    assert sensor.name == "Center"
    assert sensor.weight == 0.5
    assert sensor.temperature == 69
    assert sensor.humidity == 33

    sensor = sensors[1]
    assert sensor.id == 17687549
    assert sensor.name == "Upstairs"
    assert sensor.weight == 0.5
    assert sensor.temperature == 70
    assert sensor.humidity == 33

    with pytest.raises(
        ValueError,
        match=r"At least one sensor is required when selecting RoomIQ sensors, but got `\[\]`",
    ):
        await zone.select_room_iq_sensors([])

    with pytest.raises(
        ValueError,
        match="RoomIQ sensor with id 76543210 not present",
    ):
        await zone.select_room_iq_sensors([76543210])

    # execute normal code path
    mock_aioresponse.post(
        "https://www.mynexia.com/mobile/xxl_zones/85034552/update_active_sensors",
        payload={
            "success": True,
            "error": None,
            "result": {
                "polling_path": "https://www.mynexia.com/backstage/announcements/98765432106789b84603036489fe8d1e35ca80fa5dd381e5"
            },
        },
    )
    mock_aioresponse.get(
        "https://www.mynexia.com/backstage/announcements/98765432106789b84603036489fe8d1e35ca80fa5dd381e5",
        body=b"null",
    )
    mock_aioresponse.get(
        "https://www.mynexia.com/backstage/announcements/98765432106789b84603036489fe8d1e35ca80fa5dd381e5",
        payload={
            "status": "success, altered to enhance test coverage",
            "options": {},
        },
    )
    assert await zone.select_room_iq_sensors((17687546, 17687549), 0.01) is True

    assert persist_file.exists() is True
    persist_file.unlink()
    assert persist_file.exists() is False


async def test_clamp_to_predefined_values() -> None:
    assert clamp_to_predefined_values(45, [50, 55, 60, 65, 70, 75, 80, 85, 90]) == 50
    assert clamp_to_predefined_values(50, [50, 55, 60, 65, 70, 75, 80, 85, 90]) == 50
    assert clamp_to_predefined_values(51, [50, 55, 60, 65, 70, 75, 80, 85, 90]) == 50
    assert clamp_to_predefined_values(52, [50, 55, 60, 65, 70, 75, 80, 85, 90]) == 50
    assert clamp_to_predefined_values(53, [50, 55, 60, 65, 70, 75, 80, 85, 90]) == 55
    assert clamp_to_predefined_values(52.51, [50, 55, 60, 65, 70, 75, 80, 85, 90]) == 55
    assert clamp_to_predefined_values(55, [50, 55, 60, 65, 70, 75, 80, 85, 90]) == 55
    assert clamp_to_predefined_values(56, [50, 55, 60, 65, 70, 75, 80, 85, 90]) == 55
    assert clamp_to_predefined_values(90, [50, 55, 60, 65, 70, 75, 80, 85, 90]) == 90
    assert clamp_to_predefined_values(95, [50, 55, 60, 65, 70, 75, 80, 85, 90]) == 90
    assert clamp_to_predefined_values(100, [50, 55, 60, 65, 70, 75, 80, 85, 90]) == 90
    assert clamp_to_predefined_values(100, [90, 85, 80, 75, 70]) == 90
    assert clamp_to_predefined_values(0.4, [0.1, 0.2, 0.3, 0.4, 0.5]) == 0.4
    assert clamp_to_predefined_values(0.45, [0.1, 0.2, 0.3, 0.4, 0.5]) == 0.4


async def test_set_preset(
    aiohttp_session: aiohttp.ClientSession, mock_aioresponse: aioresponses
) -> None:
    """Test setting a zone preset."""
    nexia = NexiaHome(aiohttp_session)
    devices_json = json.loads(await load_fixture("xl1050.json"))
    nexia.update_from_json(devices_json)

    thermostat = nexia.get_thermostat_by_id(4122267)
    zone = thermostat.get_zone_by_id(84398305)

    devices = _extract_devices_from_houses_json(devices_json)
    children = extract_children_from_devices_json(devices)
    zone_data = find_dict_with_keyvalue_in_json(children[0]["zones"], "id", 84398305)

    mock_aioresponse.post(
        "https://www.mynexia.com/mobile/xxl_zones/84398305/preset_selected",
        payload={"result": zone_data},
    )
    await zone.set_preset("Home")

    requests = mock_aioresponse.requests[
        (
            "POST",
            URL("https://www.mynexia.com/mobile/xxl_zones/84398305/preset_selected"),
        )
    ]
    assert requests is not None
    first_request = requests[0]
    assert first_request.kwargs["json"]["value"] == 1

    mock_aioresponse.requests.clear()

    mock_aioresponse.post(
        "https://www.mynexia.com/mobile/xxl_zones/84398305/preset_selected",
        payload={"result": zone_data},
    )
    await zone.set_preset("Away")

    requests = mock_aioresponse.requests[
        (
            "POST",
            URL("https://www.mynexia.com/mobile/xxl_zones/84398305/preset_selected"),
        )
    ]
    assert requests is not None
    first_request = requests[0]
    assert first_request.kwargs["json"]["value"] == 2

    mock_aioresponse.requests.clear()


async def test_set_return_to_schedule_already_in_schedule(
    aiohttp_session: aiohttp.ClientSession, mock_aioresponse: aioresponses
) -> None:
    """Test returning to schedule."""
    nexia = NexiaHome(aiohttp_session)
    devices_json = json.loads(await load_fixture("xl1050.json"))
    nexia.update_from_json(devices_json)

    thermostat = nexia.get_thermostat_by_id(4122267)
    zone = thermostat.get_zone_by_id(84398305)

    devices = _extract_devices_from_houses_json(devices_json)
    children = extract_children_from_devices_json(devices)
    zone_data = find_dict_with_keyvalue_in_json(children[0]["zones"], "id", 84398305)

    mock_aioresponse.post(
        "https://www.mynexia.com/mobile/xxl_zones/84398305/return_to_schedule",
        payload={"result": zone_data},
    )
    await zone.call_return_to_schedule()

    assert not mock_aioresponse.requests  # already in schedule


async def test_set_return_to_schedule_from_hold(
    aiohttp_session: aiohttp.ClientSession, mock_aioresponse: aioresponses
) -> None:
    """Test returning to schedule."""
    nexia = NexiaHome(aiohttp_session)
    devices_json = json.loads(await load_fixture("xl1050.json"))
    nexia.update_from_json(devices_json)

    thermostat = nexia.get_thermostat_by_id(4122267)
    zone = thermostat.get_zone_by_id(84398314)

    devices = _extract_devices_from_houses_json(devices_json)
    children = extract_children_from_devices_json(devices)
    zone_data = find_dict_with_keyvalue_in_json(children[0]["zones"], "id", 84398314)

    mock_aioresponse.post(
        "https://www.mynexia.com/mobile/xxl_zones/84398314/run_mode",
        payload={"result": zone_data},
    )
    await zone.call_return_to_schedule()
    requests = mock_aioresponse.requests[
        (
            "POST",
            URL("https://www.mynexia.com/mobile/xxl_zones/84398314/run_mode"),
        )
    ]
    assert requests is not None
    first_request = requests[0]
    assert first_request.kwargs["json"] == {"value": "run_schedule"}


async def test_set_return_to_schedule_xl824(
    aiohttp_session: aiohttp.ClientSession, mock_aioresponse: aioresponses
) -> None:
    """Test returning to schedule with xl824."""
    nexia = NexiaHome(aiohttp_session)
    devices_json = json.loads(await load_fixture("xl824.json"))
    nexia.update_from_json(devices_json)

    thermostat = nexia.get_thermostat_by_id(1841910)
    zone = thermostat.get_zone_by_id(83128724)

    devices = _extract_devices_from_houses_json(devices_json)
    children = extract_children_from_devices_json(devices)
    zone_data = find_dict_with_keyvalue_in_json(children[0]["zones"], "id", 83128724)

    mock_aioresponse.post(
        "https://www.mynexia.com/mobile/xxl_zones/83128724/run_mode",
        payload={"result": zone_data},
    )
    await zone.call_return_to_schedule()
    requests = mock_aioresponse.requests[
        (
            "POST",
            URL("https://www.mynexia.com/mobile/xxl_zones/83128724/run_mode"),
        )
    ]
    assert requests is not None
    first_request = requests[0]
    assert first_request.kwargs["json"] == {"value": "run_schedule"}


async def test_set_return_to_schedule_single_zone_xl1050(
    aiohttp_session: aiohttp.ClientSession, mock_aioresponse: aioresponses
) -> None:
    """Test returning to schedule with xl1050 single zone."""
    nexia = NexiaHome(aiohttp_session)
    devices_json = json.loads(await load_fixture("single_zone_xl1050.json"))
    nexia.update_from_json(devices_json)

    thermostat = nexia.get_thermostat_by_id(345678)
    zone = thermostat.get_zone_by_id(234567)

    devices = _extract_devices_from_houses_json(devices_json)
    children = extract_children_from_devices_json(devices)
    zone_data = find_dict_with_keyvalue_in_json(children[0]["zones"], "id", 234567)

    mock_aioresponse.post(
        "https://www.mynexia.com/mobile/xxl_zones/234567/return_to_schedule",
        payload={"result": zone_data},
    )
    await zone.call_return_to_schedule()
    requests = mock_aioresponse.requests[
        (
            "POST",
            URL("https://www.mynexia.com/mobile/xxl_zones/234567/return_to_schedule"),
        )
    ]
    assert requests is not None
    first_request = requests[0]
    assert first_request.kwargs["json"] == {}


async def test_set_return_to_schedule_single_zone_xl624(
    aiohttp_session: aiohttp.ClientSession, mock_aioresponse: aioresponses
) -> None:
    """Test returning to schedule with xl624."""
    nexia = NexiaHome(aiohttp_session)
    devices_json = json.loads(await load_fixture("mobile_house_xl624.json"))
    nexia.update_from_json(devices_json)

    thermostat = nexia.get_thermostat_by_id(2222222)
    zone = thermostat.get_zone_by_id(88888888)

    devices = _extract_devices_from_houses_json(devices_json)
    children = extract_children_from_devices_json(devices)
    zone_data = find_dict_with_keyvalue_in_json(children[1]["zones"], "id", 88888888)

    mock_aioresponse.post(
        "https://www.mynexia.com/mobile/xxl_zones/88888888/return_to_schedule",
        payload={"result": zone_data},
    )
    await zone.call_return_to_schedule()
    requests = mock_aioresponse.requests[
        (
            "POST",
            URL("https://www.mynexia.com/mobile/xxl_zones/88888888/return_to_schedule"),
        )
    ]
    assert requests is not None
    first_request = requests[0]
    assert first_request.kwargs["json"] == {}


async def test_set_permanent_hold(
    aiohttp_session: aiohttp.ClientSession, mock_aioresponse: aioresponses
) -> None:
    """Test returning to schedule."""
    nexia = NexiaHome(aiohttp_session)
    devices_json = json.loads(await load_fixture("xl1050.json"))
    nexia.update_from_json(devices_json)

    thermostat = nexia.get_thermostat_by_id(4122267)
    zone = thermostat.get_zone_by_id(84398305)

    devices = _extract_devices_from_houses_json(devices_json)
    children = extract_children_from_devices_json(devices)
    zone_data = find_dict_with_keyvalue_in_json(children[0]["zones"], "id", 84398305)

    mock_aioresponse.post(
        "https://www.mynexia.com/mobile/xxl_zones/84398305/run_mode",
        payload={"result": zone_data},
    )
    await zone.call_permanent_hold()

    requests = mock_aioresponse.requests[
        (
            "POST",
            URL("https://www.mynexia.com/mobile/xxl_zones/84398305/run_mode"),
        )
    ]
    assert requests is not None
    first_request = requests[0]
    assert first_request.kwargs["json"] == {
        "value": "permanent_hold",
    }


async def test_set_zone_mode(
    aiohttp_session: aiohttp.ClientSession, mock_aioresponse: aioresponses
) -> None:
    """Test setting zone mode."""
    nexia = NexiaHome(aiohttp_session)
    devices_json = json.loads(await load_fixture("xl1050.json"))
    nexia.update_from_json(devices_json)

    thermostat = nexia.get_thermostat_by_id(4122267)
    zone = thermostat.get_zone_by_id(84398305)

    devices = _extract_devices_from_houses_json(devices_json)
    children = extract_children_from_devices_json(devices)
    zone_data = find_dict_with_keyvalue_in_json(children[0]["zones"], "id", 84398305)

    mock_aioresponse.post(
        "https://www.mynexia.com/mobile/xxl_zones/84398305/zone_mode",
        payload={"result": zone_data},
    )
    await zone.set_mode("AUTO")

    requests = mock_aioresponse.requests[
        (
            "POST",
            URL("https://www.mynexia.com/mobile/xxl_zones/84398305/zone_mode"),
        )
    ]
    assert requests is not None
    first_request = requests[0]
    assert first_request.kwargs["json"] == {
        "value": "AUTO",
    }


async def test_set_perm_hold_ux360(
    aiohttp_session: aiohttp.ClientSession, mock_aioresponse: aioresponses
) -> None:
    """Test perm hold for a ux360."""
    nexia = NexiaHome(aiohttp_session)
    devices_json = json.loads(await load_fixture("ux360.json"))
    nexia.update_from_json(devices_json)

    thermostat = nexia.get_thermostat_by_id("123456")
    zone = thermostat.get_zone_by_id(1)

    devices = _extract_devices_from_houses_json(devices_json)
    children = extract_children_from_devices_json(devices)
    zone_data = find_dict_with_keyvalue_in_json(children[0]["zones"], "id", 1)

    assert zone.is_in_permanent_hold() is False

    await zone.call_return_to_schedule()

    mock_aioresponse.post(
        "https://www.mynexia.com/mobile/diagnostics/thermostats/123456/run_mode/1",
        payload={"result": zone_data},
    )
    await zone.call_permanent_hold()

    requests = mock_aioresponse.requests[
        (
            "POST",
            URL(
                "https://www.mynexia.com/mobile/diagnostics/thermostats/123456/run_mode/1"
            ),
        )
    ]
    assert requests is not None
    first_request = requests[0]
    assert first_request.kwargs["json"] == {"value": "hold"}


async def test_set_fan_mode_ux360(
    aiohttp_session: aiohttp.ClientSession, mock_aioresponse: aioresponses
) -> None:
    """Test fan mode on a ux360."""
    nexia = NexiaHome(aiohttp_session)
    devices_json = json.loads(await load_fixture("ux360.json"))
    nexia.update_from_json(devices_json)

    thermostat = nexia.get_thermostat_by_id("123456")

    devices = _extract_devices_from_houses_json(devices_json)

    mock_aioresponse.post(
        "https://www.mynexia.com/mobile/diagnostics/thermostats/123456/fan_mode",
        payload={"result": devices[0]},
    )
    await thermostat.set_fan_mode("Circulate")

    requests = mock_aioresponse.requests[
        (
            "POST",
            URL(
                "https://www.mynexia.com/mobile/diagnostics/thermostats/123456/fan_mode"
            ),
        )
    ]
    assert requests is not None
    first_request = requests[0]
    assert first_request.kwargs["json"] == {"value": "circulate"}


async def test_resettable_single_shot() -> None:
    """Test class SingleShot."""
    loop = asyncio.get_running_loop()
    delayed_call = AsyncMock()
    single_shot = SingleShot(loop, 0.01, delayed_call)

    # Fire once.
    single_shot.reset_delayed_action_trigger()
    assert delayed_call.call_count == 0
    assert single_shot.action_pending() is True

    # Fire again while pending.
    single_shot.reset_delayed_action_trigger()
    assert delayed_call.call_count == 0
    assert single_shot.action_pending() is True

    # Wait some time to run.
    await asyncio.sleep(0.02)
    assert delayed_call.call_count == 1
    assert single_shot.action_pending() is False

    # Fire again, then exercise shutdown path.
    single_shot.reset_delayed_action_trigger()
    assert delayed_call.call_count == 1
    assert single_shot.action_pending() is True
    single_shot.async_shutdown()
    single_shot.reset_delayed_action_trigger()
    assert delayed_call.call_count == 1
    assert single_shot.action_pending() is False


@patch.object(NexiaThermostatZone, "select_room_iq_sensors")
async def test_sensor_multi_select(aiohttp_session: aiohttp.ClientSession) -> None:
    """Test class NexiaRoomIQHarmonizer."""
    nexia = NexiaHome(aiohttp_session)
    devices_json = json.loads(await load_fixture("sensors_xl1050_house.json"))
    nexia.update_from_json(devices_json)

    assert nexia.get_thermostat_ids() == [5378307]
    thermostat = nexia.get_thermostat_by_id(5378307)

    assert thermostat.get_zone_ids() == [85034552]
    zone = thermostat.get_zone_by_id(85034552)
    async_request_refetch = AsyncMock()
    signal_updated = MagicMock()
    harm = NexiaRoomIQHarmonizer(zone, async_request_refetch, signal_updated, 0.01)

    # Sensors start out included.
    assert harm.selected_sensor_ids == {17687546, 17687549}
    assert harm.request_pending() is False

    # Exclude one sensor.
    harm.trigger_remove_sensor(17687546)
    assert harm.selected_sensor_ids == {17687549}
    assert harm.request_pending() is True

    # Exclude the other, an invalid combination.
    harm.trigger_remove_sensor(17687549)
    assert len(harm.selected_sensor_ids) == 0
    assert signal_updated.call_count == 0
    assert harm.request_pending() is True

    # Wait some time to run no selected sensor case.
    await asyncio.sleep(0.02)
    assert harm.selected_sensor_ids == {17687546, 17687549}
    assert signal_updated.call_count == 1
    assert harm.request_pending() is False

    # Exclude a sensor.
    harm.trigger_remove_sensor(17687549)
    assert harm.selected_sensor_ids == {17687546}
    assert signal_updated.call_count == 1
    assert harm.request_pending() is True

    # Wait some time to run normal selected sensor case.
    assert async_request_refetch.call_count == 0
    await asyncio.sleep(0.02)
    assert harm.selected_sensor_ids == {17687546}
    assert async_request_refetch.call_count == 1
    assert signal_updated.call_count == 2
    assert harm.request_pending() is False

    # Include one again, then exercise shutdown path.
    harm.trigger_add_sensor(17687549)
    assert harm.selected_sensor_ids == {17687546, 17687549}
    assert signal_updated.call_count == 2
    assert harm.request_pending() is True
    await harm.async_shutdown()
    assert signal_updated.call_count == 3
    assert harm.request_pending() is False
    await asyncio.sleep(0.02)
    assert async_request_refetch.call_count == 1
    assert signal_updated.call_count == 3
