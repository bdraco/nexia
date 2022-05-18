"""Nexia Automation."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

_LOGGER = logging.getLogger(__name__)


if TYPE_CHECKING:
    from .home import NexiaHome


class NexiaAutomation:
    """A nexia Automation.

    Represents a nexia automation.
    """

    def __init__(self, nexia_home, automation_json):
        """Init nexia Thermostat."""
        self._nexia_home: NexiaHome = nexia_home
        self.automation_id: int = automation_json["id"]
        self._automation_json: dict[str, Any] = automation_json

    @property
    def API_MOBILE_AUTOMATION_URL(self) -> str:  # pylint: disable=invalid-name
        return self._nexia_home.mobile_url + "/automations/{automation_id}/{end_point}"

    @property
    def name(self) -> str:
        """
        Name of the automation.
        """
        return self._get_automation_key("name")

    @property
    def description(self) -> str:
        """
        Description of the automation.
        """
        return self._get_automation_key("description")

    @property
    def enabled(self) -> bool:
        """
        Enabled stat of the automation.
        """
        return self._get_automation_key("enabled")

    async def activate(self) -> None:
        """
        run the automation.
        """
        await self._post_automation_json("activate", "")

    def _get_automation_key(self, key: str) -> Any:
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

    async def _post_automation_json(self, end_point, payload):
        url = self.API_MOBILE_AUTOMATION_URL.format(
            end_point=end_point, automation_id=self._automation_json["id"]
        )
        return await self._nexia_home.post_url(url, payload)

    def update_automation_json(self, automation_json: dict[str, Any]) -> None:
        """Update with new json from the api"""
        if self._automation_json is None:
            return

        _LOGGER.debug(
            "Updated automation_id:%s with new data from post",
            self.automation_id,
        )
        self._automation_json.update(automation_json)
