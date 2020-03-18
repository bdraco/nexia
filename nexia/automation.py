"""Nexia Automation."""

import logging

from .const import MOBILE_URL

_LOGGER = logging.getLogger(__name__)


class NexiaAutomation:
    """A nexia Automation.

    Represents a nexia automation.
    """

    API_MOBILE_THERMOSTAT_URL = MOBILE_URL + "/automations/{automation_id}/{end_point}"

    def __init__(self, nexia_home, automation_json):
        """Init nexia Thermostat."""
        self._nexia_home = nexia_home
        self.automation_id = automation_json["id"]
        self._automation_json = automation_json

    @property
    def name(self):
        """
        Name of the automation.
        """
        return self._get_automation_key("name")

    @property
    def description(self):
        """
        Description of the automation.
        """
        return self._get_automation_key("description")

    @property
    def enabled(self):
        """
        Enabled stat of the automation.
        """
        return self._get_automation_key("enabled")

    def activate(self):
        """
        run the automation.
        """
        return self._post_automation_json("activate", "")

    def _get_automation_key(self, key):
        """
        Returns the automation value from the provided key in the automation's
        JSON.
        :param key: str
        :return: value
        """
        automation = self._automation_json
        if key in automation:
            return automation[key]
        raise KeyError(f'Key "{key}" not in the automation JSON!')

    def _post_automation_json(self, end_point, payload):
        url = self.API_MOBILE_THERMOSTAT_URL.format(
            end_point=end_point, automation_id=self._automation_json["id"]
        )
        return self._nexia_home.post_url(url, payload)

    def update_automation_json(self, automation_json):
        """Update with new json from the api"""
        if self._automation_json is None:
            return

        _LOGGER.debug(
            "Updated automation_id:%s with new data from post", self.automation_id,
        )
        self._automation_json.update(automation_json)
