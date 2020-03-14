"""Nexia Home."""

import datetime
import logging
import pprint
from threading import Lock

import requests

from .const import MOBILE_URL
from .thermostat import NexiaThermostat

MAX_LOGIN_ATTEMPTS = 4
TIMEOUT = 20

_LOGGER = logging.getLogger(__name__)


class NexiaHome:
    """Nexia Home Access Class."""

    AUTH_FAILED_STRING = "https://www.mynexia.com/login"

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
        update_rate=None,
        offline_json=None,
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
        :param update_rate: int - How many seconds between requesting a new
        JSON update. Default is 300s.
        """

        self.username = username
        self.password = password
        self.house_id = house_id
        self.mobile_id = None
        self.login_attempts_left = MAX_LOGIN_ATTEMPTS
        self.api_key = None
        self.house_json = None
        self.last_update = None
        self.mutex = Lock()
        self.thermostats = None

        self.offline_json = offline_json

        # Control the update rate
        if update_rate is None:
            self.update_rate = datetime.timedelta(seconds=self.DEFAULT_UPDATE_RATE)
        elif update_rate == self.DISABLE_AUTO_UPDATE:
            self.update_rate = self.DISABLE_AUTO_UPDATE
        else:
            self.update_rate = datetime.timedelta(seconds=update_rate)

        if self.offline_json:
            self.update()
            return

        # Create a session
        self.session = requests.session()
        self.session.max_redirects = 3

        # Login if requested
        if auto_login:
            self.login()
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

        if self.offline_json:
            print(
                f"POST:\n"
                f"  URL: {request_url}\n"
                f"  Data: {pprint.pformat(payload)}"
            )
            return None

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

        self._check_response("Failed to POST url", request)
        return request

    def _get_url(self, request_url):
        """
        Returns the full session.get from the URL (ROOT_URL + url)
        :param url: str
        :return: response
        """
        _LOGGER.debug("GET: Calling url %s", request_url)
        request = self.session.get(
            request_url,
            allow_redirects=False,
            timeout=TIMEOUT,
            headers=self._api_key_headers(),
        )
        # _LOGGER.debug(f"GET: RESPONSE {request_url}: request.content {request.content}")

        if request.status_code == 302:
            # assuming its redirecting to login
            self.login()
            return self._get_url(request_url)

        self._check_response("Failed to GET url", request)
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

    def _needs_update(self):
        """
        Returns True if an update is needed
        :return: bool
        """
        if self.update_rate == self.DISABLE_AUTO_UPDATE:
            return False
        if self.last_update is None:
            return True
        return datetime.datetime.now() - self.last_update > self.update_rate

    def _find_house_id(self):
        """Finds the house id if none is provided."""
        request = self.post_url(self.API_MOBILE_SESSION_URL, {})
        if request and request.status_code == 200:
            ts_json = request.json()
            if ts_json:
                self.house_id = ts_json["result"]["_links"]["child"][0]["data"]["id"]
            else:
                raise Exception("Nothing in the JSON")
        else:
            self._check_response(
                "Failed to get house id JSON, session probably timed" " out", request,
            )

    def update(self, force_update=True):
        """
        Forces a status update from nexia
        :return: None
        """
        if self.offline_json:
            self.house_json = self.offline_json["result"]["_links"]["child"][0]["data"][
                "items"
            ]
            self._update_devices()
            return

        if not self.mobile_id:
            # not yet authenticated
            return

        if (
            self.house_json is not None
            and not self._needs_update()
            and force_update is False
        ):
            return

        with self.mutex:
            # Now that we have the mutex we check again
            # to make an update did not happen elsewhere
            if (
                self.house_json is not None
                and not self._needs_update()
                and force_update is False
            ):
                return

            request = self._get_url(
                self.API_MOBILE_HOUSES_URL.format(house_id=self.house_id)
            )
            if request and request.status_code == 200:
                ts_json = request.json()
                if ts_json:
                    self.house_json = ts_json["result"]["_links"]["child"][0]["data"][
                        "items"
                    ]
                    self.last_update = datetime.datetime.now()
                else:
                    raise Exception("Nothing in the JSON")
            else:
                self._check_response(
                    "Failed to get thermostat JSON, session probably timed" " out",
                    request,
                )
            self._update_devices()

    def _update_devices(self):
        if self.thermostats is None:
            self.thermostats = []
            for thermostat_json in self.house_json:
                self.thermostats.append(NexiaThermostat(self, thermostat_json))
        else:
            for themostat in self.thermostats:
                themostat.update_thermostat_json(self.house_json)

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
        if self.login_attempts_left > 0:
            payload = {
                "login": self.username,
                "password": self.password,
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
