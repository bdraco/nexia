"""Nexia Home."""

import datetime
import logging

import requests

from .automation import NexiaAutomation
from .const import MOBILE_URL, DEFAULT_DEVICE_NAME
from .thermostat import NexiaThermostat
from .util import load_or_create_uuid

MAX_LOGIN_ATTEMPTS = 4
TIMEOUT = 20

_LOGGER = logging.getLogger(__name__)

DEVICES_ELEMENT = 0
AUTOMATIONS_ELEMENT = 1


class NexiaHome:
    """Nexia Home Access Class."""

    AUTH_FAILED_STRING = "https://www.mynexia.com/login"

    API_MOBILE_PHONE_URL = MOBILE_URL + "/phones"
    API_MOBILE_SESSION_URL = MOBILE_URL + "/session"
    API_MOBILE_HOUSES_URL = MOBILE_URL + "/houses/{house_id}"
    API_MOBILE_ACCOUNTS_SIGN_IN_URL = MOBILE_URL + "/accounts/sign_in"
    AUTH_FORGOTTEN_PASSWORD_STRING = (
        "https://www.mynexia.com/account/" "forgotten_credentials"
    )
    DEFAULT_UPDATE_RATE = 120  # 2 minutes
    DISABLE_AUTO_UPDATE = "Disable"

    def __init__(
        self,
        house_id=None,
        username=None,
        password=None,
        auto_login=True,
        auto_update=True,
        device_name=DEFAULT_DEVICE_NAME,
    ):
        """
        Connects to and provides the ability to get and set parameters of your
        Nexia connected thermostat.

        :param house_id: int - Your house_id. You can get this from logging in
        and looking at the url once you're looking at your climate device.
        https://www.mynexia.com/houses/<house_id>/climate
        :param username: str - Your login email address
        :param password: str - Your login password
        :param auto_login: bool - Default is True, Login now (True), or login
        manually later (False)
        :param auto_update: bool - Default is True, Update now (True), or update
        manually later (False)

        JSON update. Default is 300s.
        """

        self.username = username
        self.password = password
        self.house_id = house_id
        self.mobile_id = None
        self.login_attempts_left = MAX_LOGIN_ATTEMPTS
        self.api_key = None
        self.devices_json = None
        self.automations_json = None
        self.last_update = None
        self._name = None
        self.thermostats = None
        self.automations = None
        self._device_name = device_name
        self._last_update_etag = None

        # Create a session
        self.session = requests.session()
        self.session.max_redirects = 3

        # Login if requested
        if auto_login:
            self.login()

            if auto_update:
                self.update()

    def _api_key_headers(self):
        return {"X-MobileId": str(self.mobile_id), "X-ApiKey": str(self.api_key)}

    def post_url(self, request_url: str, payload: dict):
        """
        Posts data to the session from the url and payload
        :param url: str
        :param payload: dict
        :return: response
        """
        _LOGGER.debug("POST: Calling url %s with payload: %s", request_url, payload)

        request = self.session.post(
            request_url, payload, timeout=TIMEOUT, headers=self._api_key_headers()
        )

        if request.status_code == 302:
            # assuming its redirecting to login
            self.login()
            return self.post_url(request_url, payload)

        _LOGGER.debug("POST: Response from url %s: %s", request_url, request.content)
        # no need to sleep anymore as we consume the response and update the thermostat's JSON

        request.raise_for_status()
        return request

    def _get_url(self, request_url, headers=None):
        """
        Returns the full session.get from the URL (ROOT_URL + url)
        :param url: str
        :return: response
        """
        if not headers:
            headers = {}

        headers.update(self._api_key_headers())
        _LOGGER.debug("GET: Calling url %s", request_url)
        request = self.session.get(
            request_url, allow_redirects=False, timeout=TIMEOUT, headers=headers,
        )
        _LOGGER.debug(
            "GET: RESPONSE %s: request.status_code %s", request_url, request.status_code
        )

        if request.status_code == 302:
            # assuming its redirecting to login
            self.login()
            return self._get_url(request_url)

        request.raise_for_status()
        return request

    @staticmethod
    def _check_response(error_text, request):
        """
        Checks the request response, throws exception with the description text
        :param error_text: str
        :param request: response
        :return: None
        """
        if request is None or request.status_code != 200:
            if request is not None:
                response = ""
                for key in request.__attrs__:
                    response += f"  {key}: {getattr(request, key)}\n"
                raise Exception(f"{error_text}\n{response}")
            raise Exception(f"No response from session. {error_text}")

    def _find_house_id(self):
        """Finds the house id if none is provided."""
        request = self.post_url(self.API_MOBILE_SESSION_URL, {})
        if request and request.status_code == 200:
            ts_json = request.json()
            if ts_json:
                data = ts_json["result"]["_links"]["child"][0]["data"]
                self.house_id = data["id"]
                self._name = data["name"]
            else:
                raise Exception("Nothing in the JSON")
        else:
            self._check_response(
                "Failed to get house id JSON, session probably timed" " out", request,
            )

    def update_from_json(self, json_dict: dict):
        """Update the json from the houses endpoint if fetched externally."""
        self._name = json_dict["result"]["name"]
        self.devices_json = _extract_devices_from_houses_json(json_dict)
        self.automations_json = _extract_automations_from_houses_json(json_dict)
        self._update_devices()
        self._update_automations()

    def update(self, force_update=True):
        """
        Forces a status update from nexia
        :return: None
        """
        if not self.mobile_id:
            # not yet authenticated
            return

        headers = {}
        if self._last_update_etag:
            headers["If-None-Match"] = self._last_update_etag

        response = self._get_url(
            self.API_MOBILE_HOUSES_URL.format(house_id=self.house_id), headers=headers
        )

        if not response or response.status_code != 200:
            self._check_response(
                "Failed to get house JSON, session probably timed" " out", response,
            )
            return

        if response.status_code == 304:
            # already up to date
            return

        ts_json = response.json()
        if ts_json:
            self._name = ts_json["result"]["name"]
            self.devices_json = _extract_devices_from_houses_json(ts_json)
            self.automations_json = _extract_automations_from_houses_json(ts_json)
            self._last_update_etag = response.headers["etag"]
        else:
            raise Exception("Nothing in the JSON")
        self._update_devices()
        self._update_automations()
        return

    def _update_devices(self):
        self.last_update = datetime.datetime.now()

        if self.thermostats is None:
            self.thermostats = []
            for thermostat_json in self.devices_json:
                self.thermostats.append(NexiaThermostat(self, thermostat_json))
            return

        thermostat_updates_by_id = {}
        for thermostat_json in self.devices_json:
            thermostat_updates_by_id[thermostat_json["id"]] = thermostat_json

        for thermostat in self.thermostats:
            if thermostat.thermostat_id in thermostat_updates_by_id:
                thermostat.update_thermostat_json(
                    thermostat_updates_by_id[thermostat.thermostat_id]
                )

    def _update_automations(self):
        self.last_update = datetime.datetime.now()

        if self.automations is None:
            self.automations = []
            for automation_json in self.automations_json:
                self.automations.append(NexiaAutomation(self, automation_json))
            return

        automation_updates_by_id = {}
        for automation_json in self.automations_json:
            automation_updates_by_id[automation_json["id"]] = automation_json

        for automation in self.automations:
            if automation.automation_id in automation_updates_by_id:
                automation.update_automation_json(
                    automation_updates_by_id[automation.automation_id]
                )

    ########################################################################
    # Session Methods

    def login(self):
        """
        Provides you with a Nexia web session.

        All parameters should be set prior to calling this.
        - username - (str) Your email address
        - password - (str) Your login password
        - house_id - (int) Your house id
        :return: None
        """
        uuid = load_or_create_uuid(f"nexia_config_{self.username}.conf")
        if self.login_attempts_left > 0:
            payload = {
                "login": self.username,
                "password": self.password,
                "children": [],
                "childSchemas": [],
                "commitModel": None,
                "nextHref": None,
                "device_uuid": str(uuid),
                "device_name": self._device_name,
                "app_version": "5.9.0",
                "is_commercial": False,
            }
            request = self.post_url(self.API_MOBILE_ACCOUNTS_SIGN_IN_URL, payload)

            if (
                request is None
                or request.status_code != 200
                and request.status_code != 302
            ):
                self.login_attempts_left -= 1
            self._check_response("Failed to login", request)

            if request.url == self.AUTH_FORGOTTEN_PASSWORD_STRING:
                raise Exception(
                    f"Failed to login, getting redirected to {request.url}"
                    f". Try to login manually on the website."
                )

            json_dict = request.json()
            if json_dict.get("success") is not True:
                error_text = json_dict.get("error", "Unknown Error")
                raise Exception(f"Failed to login, {error_text}")

            self.mobile_id = json_dict["result"]["mobile_id"]
            self.api_key = json_dict["result"]["api_key"]
        else:
            raise Exception(
                f"Failed to login after {MAX_LOGIN_ATTEMPTS} attempts! Any "
                f"more attempts may lock your account!"
            )

        if not self.house_id:
            self._find_house_id()

    def get_name(self):
        """Name of the house"""
        return self._name

    def get_last_update(self):
        """
        Returns a string indicating the ISO formatted time string of the last
        update
        :return: The ISO formatted time string of the last update,
        datetime.datetime.min if never updated
        """
        if self.last_update is None:
            return datetime.datetime.isoformat(datetime.datetime.min)
        return datetime.datetime.isoformat(self.last_update)

    def get_thermostat_by_id(self, thermostat_id):
        """Get a thermostat by its nexia id."""
        for thermostat in self.thermostats:
            if thermostat.thermostat_id == thermostat_id:
                return thermostat
        raise KeyError

    def get_thermostat_ids(self):
        """
        Returns the number of thermostats available to Nexia
        :return:
        """
        ids = list()
        for thermostat in self.thermostats:
            ids.append(thermostat.thermostat_id)
        return ids

    def get_automation_by_id(self, automation_id):
        """Get a automation by its nexia id."""
        for automation in self.automations:
            if automation.automation_id == automation_id:
                return automation
        raise KeyError

    def get_phone_ids(self):
        """Get all the mobile phone ids."""
        response = self._get_url(self.API_MOBILE_PHONE_URL)
        data = response.json()
        items = data["result"]["items"]
        phones = []
        for phone in items:
            phones.append(phone["phone_id"])
        return phones

    def get_automation_ids(self):
        """
        Returns the number of automations available to Nexia
        :return:
        """
        ids = list()
        for automation in self.automations:
            ids.append(automation.automation_id)
        return ids


def _extract_devices_from_houses_json(json_dict: dict):
    """Extras the payload from the houses json endpoint data."""
    return json_dict["result"]["_links"]["child"][DEVICES_ELEMENT]["data"]["items"]


def _extract_automations_from_houses_json(json_dict: dict):
    """Extras the payload from the houses json endpoint data."""
    return json_dict["result"]["_links"]["child"][AUTOMATIONS_ELEMENT]["data"]["items"]
