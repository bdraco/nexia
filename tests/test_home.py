"""Tests for Nexia Home."""

import json
import os
from os.path import dirname
from aioresponses import aioresponses
import pytest
import aiohttp
import asyncio
from nexia.home import NexiaHome, _extract_devices_from_houses_json
from nexia.thermostat import NexiaThermostat

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
    text = await loop.run_in_executor(None, _load_fixture, filename)
    return text


async def test_update(aiohttp_session):
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


async def test_idle_thermo(aiohttp_session):
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
    assert thermostat.has_emergency_heat() is False
    assert thermostat.get_system_status() == "System Idle"
    assert thermostat.has_air_cleaner() is True
    assert thermostat.get_air_cleaner_mode() == "auto"
    assert thermostat.is_blower_active() is False

    zone_ids = thermostat.get_zone_ids()
    assert zone_ids == [83261002, 83261005, 83261008, 83261011]


async def test_idle_thermo_issue_33758(mock_aioresponse: aioresponses):
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
    assert thermostat.get_humidity_setpoint_limits() == (0.35, 0.65)
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


async def test_idle_thermo_issue_33968_thermostat_1690380(aiohttp_session):
    """Get methods for an cooling thermostat."""
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
    assert thermostat.get_humidity_setpoint_limits() == (0.35, 0.65)
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


async def test_xl824_2(aiohttp_session):
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


"""Tests for nexia home."""


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


"""Tests for nexia thermostat zone."""


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


async def test_zone_issue_33968_zone_83037343(aiohttp_session):
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


async def test_zone_issue_33758(aiohttp_session):
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


async def test_single_zone(aiohttp_session):
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


async def test_single_zone_system_off(aiohttp_session):
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


"""Automations tests."""


async def test_automations(aiohttp_session):
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


async def test_x850_grouped(aiohttp_session):
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
    assert thermostat.get_humidity_setpoint_limits() == (0.35, 0.65)
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


async def test_issue_79891(aiohttp_session):
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
    assert thermostat.get_humidity_setpoint_limits() == (0.35, 0.65)
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
