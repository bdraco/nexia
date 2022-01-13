"""Tests for Nexia Home."""

import json
import os
from os.path import dirname
import unittest

import pytest
import requests_mock

from nexia.home import NexiaHome, _extract_devices_from_houses_json
from nexia.thermostat import NexiaThermostat


def load_fixture(filename):
    """Load a fixture."""
    test_dir = dirname(__file__)

    path = os.path.join(test_dir, "fixtures", filename)
    with open(path) as fptr:
        return fptr.read()


class TestNexiaThermostat(unittest.TestCase):
    """Tests for nexia thermostat."""

    def test_update(self):
        nexia = NexiaHome(auto_login=False)
        devices_json = json.loads(load_fixture("mobile_houses_123456.json"))
        nexia.update_from_json(devices_json)
        thermostat = nexia.get_thermostat_by_id(2059661)
        zone_ids = thermostat.get_zone_ids()
        self.assertEqual(zone_ids, [83261002, 83261005, 83261008, 83261011])
        nexia.update_from_json(devices_json)
        zone_ids = thermostat.get_zone_ids()
        self.assertEqual(zone_ids, [83261002, 83261005, 83261008, 83261011])
        nexia.update_from_json(devices_json)

    def test_idle_thermo(self):
        """Get methods for an idle thermostat."""
        nexia = NexiaHome(auto_login=False)
        devices_json = json.loads(load_fixture("mobile_houses_123456.json"))
        nexia.update_from_json(devices_json)

        thermostat = nexia.get_thermostat_by_id(2059661)

        self.assertEqual(thermostat.get_model(), "XL1050")
        self.assertEqual(thermostat.get_firmware(), "5.9.1")
        self.assertEqual(thermostat.get_dev_build_number(), "1581321824")
        self.assertEqual(thermostat.get_device_id(), "000000")
        self.assertEqual(thermostat.get_type(), "XL1050")
        self.assertEqual(thermostat.get_name(), "Downstairs East Wing")
        self.assertEqual(thermostat.get_deadband(), 3)
        self.assertEqual(thermostat.get_setpoint_limits(), (55, 99))
        self.assertEqual(thermostat.get_variable_fan_speed_limits(), (0.35, 1.0))
        self.assertEqual(thermostat.get_unit(), "F")
        self.assertEqual(thermostat.get_humidity_setpoint_limits(), (0.35, 0.65))
        self.assertEqual(thermostat.get_fan_mode(), "Auto")
        self.assertEqual(thermostat.get_fan_modes(), ["Auto", "On", "Circulate"])
        self.assertEqual(thermostat.get_outdoor_temperature(), 88.0)
        self.assertEqual(thermostat.get_relative_humidity(), 0.36)
        self.assertEqual(thermostat.get_current_compressor_speed(), 0.0)
        self.assertEqual(thermostat.get_requested_compressor_speed(), 0.0)
        self.assertEqual(thermostat.get_fan_speed_setpoint(), 0.35)
        self.assertEqual(thermostat.get_dehumidify_setpoint(), 0.50)
        self.assertEqual(thermostat.has_dehumidify_support(), True)
        self.assertEqual(thermostat.has_dehumidify_support(), True)
        self.assertEqual(thermostat.has_emergency_heat(), False)
        self.assertEqual(thermostat.get_system_status(), "System Idle")
        self.assertEqual(thermostat.has_air_cleaner(), True)
        self.assertEqual(thermostat.get_air_cleaner_mode(), "auto")
        self.assertEqual(thermostat.is_blower_active(), False)

        zone_ids = thermostat.get_zone_ids()
        self.assertEqual(zone_ids, [83261002, 83261005, 83261008, 83261011])

    @requests_mock.Mocker()
    def test_idle_thermo_issue_33758(self, m):
        """Get methods for an idle thermostat."""
        nexia = NexiaHome(auto_login=False)
        devices_json = json.loads(load_fixture("mobile_house_issue_33758.json"))
        nexia.update_from_json(devices_json)

        thermostat: NexiaThermostat = nexia.get_thermostat_by_id(12345678)

        self.assertEqual(thermostat.get_model(), "XL1050")
        self.assertEqual(thermostat.get_firmware(), "5.9.1")
        self.assertEqual(thermostat.get_dev_build_number(), "1581321824")
        self.assertEqual(thermostat.get_device_id(), "xxxxxx")
        self.assertEqual(thermostat.get_type(), "XL1050")
        self.assertEqual(thermostat.get_name(), "Thermostat")
        self.assertEqual(thermostat.get_deadband(), 3)
        self.assertEqual(thermostat.get_setpoint_limits(), (55, 99))
        self.assertEqual(thermostat.get_variable_fan_speed_limits(), (0.35, 1.0))
        self.assertEqual(thermostat.get_unit(), "F")
        self.assertEqual(thermostat.get_humidity_setpoint_limits(), (0.35, 0.65))
        self.assertEqual(thermostat.get_fan_mode(), "Auto")
        self.assertEqual(thermostat.get_fan_modes(), ["Auto", "On", "Circulate"])
        self.assertEqual(thermostat.get_outdoor_temperature(), 55.0)
        self.assertEqual(thermostat.get_relative_humidity(), 0.43)
        self.assertEqual(thermostat.get_current_compressor_speed(), 0.0)
        self.assertEqual(thermostat.get_requested_compressor_speed(), 0.0)
        self.assertEqual(thermostat.get_fan_speed_setpoint(), 1)
        self.assertEqual(thermostat.get_dehumidify_setpoint(), 0.55)
        self.assertEqual(thermostat.has_dehumidify_support(), True)
        self.assertEqual(thermostat.has_humidify_support(), True)
        self.assertEqual(thermostat.has_emergency_heat(), True)
        self.assertEqual(thermostat.is_emergency_heat_active(), False)
        self.assertEqual(thermostat.get_system_status(), "System Idle")
        self.assertEqual(thermostat.has_air_cleaner(), True)
        self.assertEqual(thermostat.get_air_cleaner_mode(), "auto")
        self.assertEqual(thermostat.is_blower_active(), False)

        devices = _extract_devices_from_houses_json(devices_json)
        m.post(
            "https://www.mynexia.com/mobile/xxl_thermostats/12345678/emergency_heat",
            json={"result": devices[0]},
        )
        thermostat.set_emergency_heat(True)
        history = m.request_history
        assert history[0].method == "POST"
        assert history[0].text == "value=true"

        m.post(
            "https://www.mynexia.com/mobile/xxl_thermostats/12345678/emergency_heat",
            json={"result": devices[0]},
        )
        thermostat.set_emergency_heat(False)
        history = m.request_history
        assert history[1].method == "POST"
        assert history[1].text == "value=false"

        zone_ids = thermostat.get_zone_ids()
        self.assertEqual(zone_ids, [12345678])

    def test_idle_thermo_issue_33968_thermostat_1690380(self):
        """Get methods for an cooling thermostat."""
        nexia = NexiaHome(auto_login=False)
        devices_json = json.loads(load_fixture("mobile_house_issue_33968.json"))
        nexia.update_from_json(devices_json)

        thermostat_ids = nexia.get_thermostat_ids()
        self.assertEqual(thermostat_ids, [1690380])

        thermostat = nexia.get_thermostat_by_id(1690380)

        zone_ids = thermostat.get_zone_ids()
        self.assertEqual(zone_ids, [83037337, 83037340, 83037343])

        self.assertEqual(thermostat.get_model(), "XL1050")
        self.assertEqual(thermostat.get_firmware(), "5.9.1")
        self.assertEqual(thermostat.get_dev_build_number(), "1581321824")
        self.assertEqual(thermostat.get_device_id(), "removed")
        self.assertEqual(thermostat.get_type(), "XL1050")
        self.assertEqual(thermostat.get_name(), "Thermostat")
        self.assertEqual(thermostat.get_deadband(), 3)
        self.assertEqual(thermostat.get_setpoint_limits(), (55, 99))
        self.assertEqual(thermostat.get_variable_fan_speed_limits(), (0.35, 1.0))
        self.assertEqual(thermostat.get_unit(), "F")
        self.assertEqual(thermostat.get_humidity_setpoint_limits(), (0.35, 0.65))
        self.assertEqual(thermostat.get_fan_mode(), "Auto")
        self.assertEqual(thermostat.get_fan_modes(), ["Auto", "On", "Circulate"])
        self.assertEqual(thermostat.get_outdoor_temperature(), 80.0)
        self.assertEqual(thermostat.get_relative_humidity(), 0.55)
        self.assertEqual(thermostat.get_current_compressor_speed(), 0.41)
        self.assertEqual(thermostat.get_requested_compressor_speed(), 0.41)
        self.assertEqual(thermostat.get_fan_speed_setpoint(), 0.5)
        self.assertEqual(thermostat.get_dehumidify_setpoint(), 0.55)
        self.assertEqual(thermostat.has_dehumidify_support(), True)
        self.assertEqual(thermostat.has_humidify_support(), False)
        self.assertEqual(thermostat.has_emergency_heat(), True)
        self.assertEqual(thermostat.is_emergency_heat_active(), False)
        self.assertEqual(thermostat.get_system_status(), "Cooling")
        self.assertEqual(thermostat.has_air_cleaner(), True)
        self.assertEqual(thermostat.get_air_cleaner_mode(), "auto")
        self.assertEqual(thermostat.is_blower_active(), True)

    def test_active_thermo(self):
        """Get methods for an active thermostat."""
        nexia = NexiaHome(auto_login=False)
        devices_json = json.loads(load_fixture("mobile_houses_123456.json"))
        nexia.update_from_json(devices_json)

        thermostat = nexia.get_thermostat_by_id(2293892)

        self.assertEqual(thermostat.get_model(), "XL1050")
        self.assertEqual(thermostat.get_firmware(), "5.9.1")
        self.assertEqual(thermostat.get_dev_build_number(), "1581321824")
        self.assertEqual(thermostat.get_device_id(), "0281B02C")
        self.assertEqual(thermostat.get_type(), "XL1050")
        self.assertEqual(thermostat.get_name(), "Master Suite")
        self.assertEqual(thermostat.get_deadband(), 3)
        self.assertEqual(thermostat.get_setpoint_limits(), (55, 99))
        self.assertEqual(thermostat.get_variable_fan_speed_limits(), (0.35, 1.0))
        self.assertEqual(thermostat.get_unit(), "F")
        self.assertEqual(thermostat.get_humidity_setpoint_limits(), (0.35, 0.65))
        self.assertEqual(thermostat.get_fan_mode(), "Auto")
        self.assertEqual(thermostat.get_fan_modes(), ["Auto", "On", "Circulate"])
        self.assertEqual(thermostat.get_outdoor_temperature(), 87.0)
        self.assertEqual(thermostat.get_relative_humidity(), None)
        self.assertEqual(thermostat.get_current_compressor_speed(), 0.69)
        self.assertEqual(thermostat.get_requested_compressor_speed(), 0.69)
        self.assertEqual(thermostat.get_fan_speed_setpoint(), 0.35)
        self.assertEqual(thermostat.get_dehumidify_setpoint(), 0.45)
        self.assertEqual(thermostat.has_dehumidify_support(), True)
        self.assertEqual(thermostat.has_humidify_support(), False)
        self.assertEqual(thermostat.has_emergency_heat(), False)
        self.assertEqual(thermostat.get_system_status(), "Cooling")
        self.assertEqual(thermostat.has_air_cleaner(), True)
        self.assertEqual(thermostat.get_air_cleaner_mode(), "auto")
        self.assertEqual(thermostat.is_blower_active(), True)

        zone_ids = thermostat.get_zone_ids()
        self.assertEqual(zone_ids, [83394133, 83394130, 83394136, 83394127, 83394139])

    @pytest.mark.skip(reason="not yet supported")
    def test_xl624(self):
        """Get methods for an xl624 thermostat."""
        nexia = NexiaHome(auto_login=False)
        devices_json = json.loads(load_fixture("mobile_house_xl624.json"))
        nexia.update_from_json(devices_json)

        thermostat_ids = nexia.get_thermostat_ids()
        self.assertEqual(thermostat_ids, [2222222, 3333333])
        thermostat = nexia.get_thermostat_by_id(1111111)

        self.assertEqual(thermostat.get_model(), None)
        self.assertEqual(thermostat.get_firmware(), "2.8")
        self.assertEqual(thermostat.get_dev_build_number(), "0603340208")
        self.assertEqual(thermostat.get_device_id(), None)
        self.assertEqual(thermostat.get_type(), None)
        self.assertEqual(thermostat.get_name(), "Downstairs Hall")
        self.assertEqual(thermostat.get_deadband(), 3)
        self.assertEqual(thermostat.get_setpoint_limits(), (55, 99))
        self.assertEqual(thermostat.has_variable_fan_speed(), False)
        self.assertEqual(thermostat.get_unit(), "F")
        self.assertEqual(thermostat.get_humidity_setpoint_limits(), (0.35, 0.65))
        self.assertEqual(thermostat.get_fan_mode(), "Auto")
        self.assertEqual(thermostat.get_fan_modes(), ["Auto", "On", "Cycler"])
        self.assertEqual(thermostat.get_current_compressor_speed(), 0.0)
        self.assertEqual(thermostat.get_requested_compressor_speed(), 0.0)
        self.assertEqual(thermostat.has_dehumidify_support(), False)
        self.assertEqual(thermostat.has_humidify_support(), False)
        self.assertEqual(thermostat.has_emergency_heat(), False)
        self.assertEqual(thermostat.get_system_status(), "System Idle")
        self.assertEqual(thermostat.has_air_cleaner(), False)
        self.assertEqual(thermostat.is_blower_active(), False)

        zone_ids = thermostat.get_zone_ids()
        self.assertEqual(zone_ids, [12345678])

    def test_xl824_1(self):
        """Get methods for an xl824 thermostat."""
        nexia = NexiaHome(auto_login=False)
        devices_json = json.loads(load_fixture("mobile_house_xl624.json"))
        nexia.update_from_json(devices_json)

        thermostat_ids = nexia.get_thermostat_ids()
        self.assertEqual(thermostat_ids, [2222222, 3333333])
        thermostat = nexia.get_thermostat_by_id(2222222)

        self.assertEqual(thermostat.get_model(), "XL824")
        self.assertEqual(thermostat.get_firmware(), "5.9.1")
        self.assertEqual(thermostat.get_dev_build_number(), "1581314625")
        self.assertEqual(thermostat.get_device_id(), "0167CA48")
        self.assertEqual(thermostat.get_type(), "XL824")
        self.assertEqual(thermostat.get_name(), "Family Room")
        self.assertEqual(thermostat.get_deadband(), 3)
        self.assertEqual(thermostat.get_setpoint_limits(), (55, 99))
        self.assertEqual(thermostat.has_variable_fan_speed(), True)
        self.assertEqual(thermostat.get_unit(), "F")
        self.assertEqual(thermostat.get_humidity_setpoint_limits(), (0.35, 0.65))
        self.assertEqual(thermostat.get_fan_mode(), "Circulate")
        self.assertEqual(thermostat.get_fan_modes(), ["Auto", "On", "Circulate"])
        self.assertEqual(thermostat.get_current_compressor_speed(), 0.0)
        self.assertEqual(thermostat.get_requested_compressor_speed(), 0.0)
        self.assertEqual(thermostat.has_dehumidify_support(), True)
        self.assertEqual(thermostat.has_humidify_support(), False)
        self.assertEqual(thermostat.has_emergency_heat(), False)
        self.assertEqual(thermostat.get_system_status(), "System Idle")
        self.assertEqual(thermostat.has_air_cleaner(), True)
        self.assertEqual(thermostat.is_blower_active(), False)

        zone_ids = thermostat.get_zone_ids()
        self.assertEqual(zone_ids, [88888888])

    def test_xl824_2(self):
        """Get methods for an xl824 thermostat."""
        nexia = NexiaHome(auto_login=False)
        devices_json = json.loads(load_fixture("mobile_house_xl624.json"))
        nexia.update_from_json(devices_json)

        thermostat_ids = nexia.get_thermostat_ids()
        self.assertEqual(thermostat_ids, [2222222, 3333333])
        thermostat = nexia.get_thermostat_by_id(3333333)

        self.assertEqual(thermostat.get_model(), "XL824")
        self.assertEqual(thermostat.get_firmware(), "5.9.1")
        self.assertEqual(thermostat.get_dev_build_number(), "1581314625")
        self.assertEqual(thermostat.get_device_id(), "01573380")
        self.assertEqual(thermostat.get_type(), "XL824")
        self.assertEqual(thermostat.get_name(), "Upstairs")
        self.assertEqual(thermostat.get_deadband(), 3)
        self.assertEqual(thermostat.get_setpoint_limits(), (55, 99))
        self.assertEqual(thermostat.has_variable_fan_speed(), True)
        self.assertEqual(thermostat.get_unit(), "F")
        self.assertEqual(thermostat.get_humidity_setpoint_limits(), (0.35, 0.65))
        self.assertEqual(thermostat.get_fan_mode(), "Circulate")
        self.assertEqual(thermostat.get_fan_modes(), ["Auto", "On", "Circulate"])
        self.assertEqual(thermostat.get_current_compressor_speed(), 0.0)
        self.assertEqual(thermostat.get_requested_compressor_speed(), 0.0)
        self.assertEqual(thermostat.has_dehumidify_support(), True)
        self.assertEqual(thermostat.has_humidify_support(), False)
        self.assertEqual(thermostat.has_emergency_heat(), False)
        self.assertEqual(thermostat.get_system_status(), "System Idle")
        self.assertEqual(thermostat.has_air_cleaner(), True)
        self.assertEqual(thermostat.is_blower_active(), False)

        zone_ids = thermostat.get_zone_ids()
        self.assertEqual(zone_ids, [99999999])


class TestNexiaHome(unittest.TestCase):
    """Tests for nexia home."""

    def test_basic(self):
        """Basic tests for NexiaHome."""
        nexia = NexiaHome(auto_login=False)
        devices_json = json.loads(load_fixture("mobile_houses_123456.json"))
        nexia.update_from_json(devices_json)

        self.assertEqual(nexia.get_name(), "Hidden")
        thermostat_ids = nexia.get_thermostat_ids()
        self.assertEqual(thermostat_ids, [2059661, 2059676, 2293892, 2059652])

    def test_basic_issue_33758(self):
        """Basic tests for NexiaHome."""
        nexia = NexiaHome(auto_login=False)
        devices_json = json.loads(load_fixture("mobile_house_issue_33758.json"))
        nexia.update_from_json(devices_json)

        self.assertEqual(nexia.get_name(), "Hidden")
        thermostat_ids = nexia.get_thermostat_ids()
        self.assertEqual(thermostat_ids, [12345678])


class TestNexiaThermostatZone(unittest.TestCase):
    """Tests for nexia thermostat zone."""

    def test_zone_issue_33968_zone_83037337(self):
        """Tests for nexia thermostat zone that is cooling."""
        nexia = NexiaHome(auto_login=False)
        devices_json = json.loads(load_fixture("mobile_house_issue_33968.json"))
        nexia.update_from_json(devices_json)

        thermostat = nexia.get_thermostat_by_id(1690380)
        zone = thermostat.get_zone_by_id(83037337)

        self.assertEqual(zone.thermostat, thermostat)

        self.assertEqual(zone.get_name(), "Family Room")
        self.assertEqual(zone.get_cooling_setpoint(), 77)
        self.assertEqual(zone.get_heating_setpoint(), 74)
        self.assertEqual(zone.get_current_mode(), "COOL")
        self.assertEqual(
            zone.get_requested_mode(),
            "COOL",
        )
        self.assertEqual(
            zone.get_presets(),
            ["None", "Home", "Away", "Sleep"],
        )
        self.assertEqual(
            zone.get_preset(),
            "None",
        )
        self.assertEqual(
            zone.get_status(),
            "Damper Closed",
        )
        self.assertEqual(
            zone.get_setpoint_status(),
            "Permanent Hold",
        )
        self.assertEqual(zone.is_calling(), False)
        self.assertEqual(zone.is_in_permanent_hold(), True)

    def test_zone_issue_33968_zone_83037340(self):
        """Tests for nexia thermostat zone that is cooling."""
        nexia = NexiaHome(auto_login=False)
        devices_json = json.loads(load_fixture("mobile_house_issue_33968.json"))
        nexia.update_from_json(devices_json)

        thermostat = nexia.get_thermostat_by_id(1690380)
        zone = thermostat.get_zone_by_id(83037340)

        self.assertEqual(zone.thermostat, thermostat)

        self.assertEqual(zone.get_name(), "Office")
        self.assertEqual(zone.get_cooling_setpoint(), 77)
        self.assertEqual(zone.get_heating_setpoint(), 74)
        self.assertEqual(zone.get_current_mode(), "COOL")
        self.assertEqual(
            zone.get_requested_mode(),
            "COOL",
        )
        self.assertEqual(
            zone.get_presets(),
            ["None", "Home", "Away", "Sleep"],
        )
        self.assertEqual(
            zone.get_preset(),
            "None",
        )
        self.assertEqual(
            zone.get_status(),
            "Damper Open",
        )
        self.assertEqual(
            zone.get_setpoint_status(),
            "Permanent Hold",
        )
        self.assertEqual(zone.is_calling(), True)
        self.assertEqual(zone.is_in_permanent_hold(), True)

    def test_zone_issue_33968_zone_83037343(self):
        """Tests for nexia thermostat zone that is cooling."""
        nexia = NexiaHome(auto_login=False)
        devices_json = json.loads(load_fixture("mobile_house_issue_33968.json"))
        nexia.update_from_json(devices_json)

        thermostat = nexia.get_thermostat_by_id(1690380)
        zone = thermostat.get_zone_by_id(83037343)

        self.assertEqual(zone.thermostat, thermostat)

        self.assertEqual(zone.get_name(), "Master")
        self.assertEqual(zone.get_cooling_setpoint(), 77)
        self.assertEqual(zone.get_heating_setpoint(), 68)
        self.assertEqual(zone.get_current_mode(), "COOL")
        self.assertEqual(
            zone.get_requested_mode(),
            "COOL",
        )
        self.assertEqual(
            zone.get_presets(),
            ["None", "Home", "Away", "Sleep"],
        )
        self.assertEqual(
            zone.get_preset(),
            "None",
        )
        self.assertEqual(
            zone.get_status(),
            "Damper Open",
        )
        self.assertEqual(
            zone.get_setpoint_status(),
            "Permanent Hold",
        )
        self.assertEqual(zone.is_calling(), True)
        self.assertEqual(zone.is_in_permanent_hold(), True)

    def test_zone_issue_33758(self):
        """Tests for nexia thermostat zone relieving air."""
        nexia = NexiaHome(auto_login=False)
        devices_json = json.loads(load_fixture("mobile_house_issue_33758.json"))
        nexia.update_from_json(devices_json)

        thermostat = nexia.get_thermostat_by_id(12345678)
        zone = thermostat.get_zone_by_id(12345678)

        self.assertEqual(zone.thermostat, thermostat)

        self.assertEqual(zone.get_name(), "Thermostat NativeZone")
        self.assertEqual(zone.get_cooling_setpoint(), 73)
        self.assertEqual(zone.get_heating_setpoint(), 68)
        self.assertEqual(zone.get_current_mode(), "AUTO")
        self.assertEqual(
            zone.get_requested_mode(),
            "AUTO",
        )
        self.assertEqual(
            zone.get_presets(),
            ["None", "Home", "Away", "Sleep"],
        )
        self.assertEqual(
            zone.get_preset(),
            "None",
        )
        self.assertEqual(
            zone.get_status(),
            "Idle",
        )
        self.assertEqual(
            zone.get_setpoint_status(),
            "Run Schedule - None",
        )
        self.assertEqual(zone.is_calling(), False)
        self.assertEqual(zone.is_in_permanent_hold(), False)

    def test_zone_relieving_air(self):
        """Tests for nexia thermostat zone relieving air."""
        nexia = NexiaHome(auto_login=False)
        devices_json = json.loads(load_fixture("mobile_houses_123456.json"))
        nexia.update_from_json(devices_json)

        thermostat = nexia.get_thermostat_by_id(2293892)
        zone = thermostat.get_zone_by_id(83394133)

        self.assertEqual(zone.thermostat, thermostat)

        self.assertEqual(zone.get_name(), "Bath Closet")
        self.assertEqual(zone.get_cooling_setpoint(), 79)
        self.assertEqual(zone.get_heating_setpoint(), 63)
        self.assertEqual(zone.get_current_mode(), "AUTO")
        self.assertEqual(
            zone.get_requested_mode(),
            "AUTO",
        )
        self.assertEqual(
            zone.get_presets(),
            ["None", "Home", "Away", "Sleep"],
        )
        self.assertEqual(
            zone.get_preset(),
            "None",
        )
        self.assertEqual(
            zone.get_status(),
            "Relieving Air",
        )
        self.assertEqual(
            zone.get_setpoint_status(),
            "Permanent Hold",
        )
        self.assertEqual(zone.is_calling(), True)
        self.assertEqual(zone.is_in_permanent_hold(), True)

    def test_zone_cooling_air(self):
        """Tests for nexia thermostat zone cooling."""
        nexia = NexiaHome(auto_login=False)
        devices_json = json.loads(load_fixture("mobile_houses_123456.json"))
        nexia.update_from_json(devices_json)

        thermostat = nexia.get_thermostat_by_id(2293892)
        zone = thermostat.get_zone_by_id(83394130)

        self.assertEqual(zone.get_name(), "Master")
        self.assertEqual(zone.get_cooling_setpoint(), 71)
        self.assertEqual(zone.get_heating_setpoint(), 63)
        self.assertEqual(zone.get_current_mode(), "AUTO")
        self.assertEqual(
            zone.get_requested_mode(),
            "AUTO",
        )
        self.assertEqual(
            zone.get_presets(),
            ["None", "Home", "Away", "Sleep"],
        )
        self.assertEqual(
            zone.get_preset(),
            "None",
        )
        self.assertEqual(
            zone.get_status(),
            "Damper Open",
        )
        self.assertEqual(
            zone.get_setpoint_status(),
            "Permanent Hold",
        )
        self.assertEqual(zone.is_calling(), True)
        self.assertEqual(zone.is_in_permanent_hold(), True)

    def test_zone_idle(self):
        """Tests for nexia thermostat zone idle."""
        nexia = NexiaHome(auto_login=False)
        devices_json = json.loads(load_fixture("mobile_houses_123456.json"))
        nexia.update_from_json(devices_json)

        thermostat = nexia.get_thermostat_by_id(2059661)
        zone = thermostat.get_zone_by_id(83261002)

        self.assertEqual(zone.get_name(), "Living East")
        self.assertEqual(zone.get_cooling_setpoint(), 79)
        self.assertEqual(zone.get_heating_setpoint(), 63)
        self.assertEqual(zone.get_current_mode(), "AUTO")
        self.assertEqual(
            zone.get_requested_mode(),
            "AUTO",
        )
        self.assertEqual(
            zone.get_presets(),
            ["None", "Home", "Away", "Sleep"],
        )
        self.assertEqual(
            zone.get_preset(),
            "None",
        )
        self.assertEqual(
            zone.get_status(),
            "Idle",
        )
        self.assertEqual(
            zone.get_setpoint_status(),
            "Permanent Hold",
        )
        self.assertEqual(zone.is_calling(), False)
        self.assertEqual(zone.is_in_permanent_hold(), True)

    def test_xl824_idle(self):
        """Tests for nexia xl824 zone idle."""
        nexia = NexiaHome(auto_login=False)
        devices_json = json.loads(load_fixture("mobile_house_xl624.json"))
        nexia.update_from_json(devices_json)

        thermostat_ids = nexia.get_thermostat_ids()
        self.assertEqual(thermostat_ids, [2222222, 3333333])
        thermostat = nexia.get_thermostat_by_id(3333333)
        zone = thermostat.get_zone_by_id(99999999)

        self.assertEqual(zone.get_name(), "Upstairs NativeZone")
        self.assertEqual(zone.get_cooling_setpoint(), 74)
        self.assertEqual(zone.get_heating_setpoint(), 62)
        self.assertEqual(zone.get_current_mode(), "COOL")
        self.assertEqual(
            zone.get_requested_mode(),
            "COOL",
        )
        self.assertEqual(
            zone.get_presets(),
            ["None", "Home", "Away", "Sleep"],
        )
        self.assertEqual(
            zone.get_preset(),
            "None",
        )
        self.assertEqual(
            zone.get_status(),
            "Idle",
        )
        self.assertEqual(
            zone.get_setpoint_status(),
            "Permanent Hold",
        )
        self.assertEqual(zone.is_calling(), False)
        self.assertEqual(zone.is_in_permanent_hold(), True)

    def test_single_zone(self):
        """Test thermostat with only a single (Native) zone."""
        nexia = NexiaHome(auto_login=False)
        devices_json = json.loads(load_fixture("single_zone_xl1050.json"))
        nexia.update_from_json(devices_json)

        thermostat_ids = nexia.get_thermostat_ids()
        self.assertEqual(thermostat_ids, [345678])
        thermostat = nexia.get_thermostat_by_id(345678)
        zone = thermostat.get_zone_by_id(234567)

        self.assertEqual(zone.get_name(), "Thermostat 1 NativeZone")
        self.assertEqual(zone.get_cooling_setpoint(), 73)
        self.assertEqual(zone.get_heating_setpoint(), 68)
        self.assertEqual(zone.get_current_mode(), "AUTO")
        self.assertEqual(
            zone.get_requested_mode(),
            "AUTO",
        )
        self.assertEqual(
            zone.get_presets(),
            ["None", "Home", "Away", "Sleep"],
        )
        self.assertEqual(
            zone.get_preset(),
            "None",
        )
        self.assertEqual(
            zone.get_status(),
            "Idle",
        )
        self.assertEqual(
            zone.get_setpoint_status(),
            "Permanent Hold",
        )
        self.assertEqual(zone.is_calling(), True)
        self.assertEqual(zone.is_in_permanent_hold(), True)


class TestNexiaAutomation(unittest.TestCase):
    def test_automations(self):
        """Get methods for an active thermostat."""
        nexia = NexiaHome(auto_login=False)
        devices_json = json.loads(load_fixture("mobile_houses_123456.json"))
        nexia.update_from_json(devices_json)

        automation_ids = nexia.get_automation_ids()
        self.assertEqual(
            automation_ids,
            [3467876, 3467870, 3452469, 3452472, 3454776, 3454774, 3486078, 3486091],
        )

        automation_one = nexia.get_automation_by_id(3467876)

        self.assertEqual(automation_one.name, "Away for 12 Hours")
        self.assertEqual(
            automation_one.description,
            "When IFTTT activates the automation Upstairs West Wing will "
            "permanently hold the heat to 62.0 and cool to 83.0 AND "
            "Downstairs East Wing will permanently hold the heat to 62.0 "
            "and cool to 83.0 AND Downstairs West Wing will permanently "
            "hold the heat to 62.0 and cool to 83.0 AND Activate the mode "
            "named 'Away 12' AND Master Suite will permanently hold the "
            "heat to 62.0 and cool to 83.0",
        )
        self.assertEqual(automation_one.enabled, True)
        self.assertEqual(automation_one.automation_id, 3467876)
