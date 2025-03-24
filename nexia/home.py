"""Nexia Home."""

from __future__ import annotations

import asyncio
import datetime
import logging
from typing import Any

import aiohttp
import orjson
from propcache import cached_property
from yarl import URL

from .automation import NexiaAutomation
from .const import (
    APP_VERSION,
    ASAIR_ROOT_URL,
    BRAND_ASAIR,
    BRAND_NEXIA,
    BRAND_TRANE,
    DEFAULT_DEVICE_NAME,
    MOBILE_URL_TEMPLATE,
    NEXIA_ROOT_URL,
    TRANE_ROOT_URL,
)
from .thermostat import NexiaThermostat
from .util import load_or_create_uuid


class LoginFailedException(Exception):
    """Login failed."""


MAX_LOGIN_ATTEMPTS = 4
TIMEOUT = aiohttp.ClientTimeout(total=20)

_LOGGER = logging.getLogger(__name__)

DEVICES_ELEMENT = 0
AUTOMATIONS_ELEMENT = 1
MAX_REDIRECTS = 3

BRAND_TO_URL = {
    BRAND_ASAIR: ASAIR_ROOT_URL,
    BRAND_TRANE: TRANE_ROOT_URL,
    BRAND_NEXIA: NEXIA_ROOT_URL,
}


def extract_children_from_devices_json(
    devices_json: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Extracts the payload from the devices json endpoint data."""
    children: list[dict[str, Any]] = []
    for child in devices_json:
        type_ = child.get("type")
        if not type_ or "thermostat" in type_:
            children.append(child)
        elif type_ == "group" and "_links" in child and "child" in child["_links"]:
            children.extend(sub_child["data"] for sub_child in child["_links"]["child"])
    return children


class NexiaHome:
    """Nexia Home Access Class."""

    DEFAULT_UPDATE_RATE = 120  # 2 minutes
    DISABLE_AUTO_UPDATE = "Disable"

    thermostats: list[NexiaThermostat]
    automations: list[NexiaAutomation]

    def __init__(
        self,
        session: aiohttp.ClientSession,
        house_id=None,
        username=None,
        password=None,
        device_name=DEFAULT_DEVICE_NAME,
        brand=BRAND_NEXIA,
        state_file=None,
    ):
        """Connects to and provides the ability to get and set parameters of your
        Nexia connected thermostat.

        :param session: ClientSession to use
        :param house_id: int - Your house_id. You can get this from logging in
                and looking at the url once you're looking at your climate device.
                https://www.mynexia.com/houses/<house_id>/climate
        :param username: str - Your login email address
        :param password: str - Your login password
        :param device_name: str - Name of the device running this code
        :param brand: str - Brand of the desired system (from nexia.const)
        :param state_file: str | PathLike - File to use when persisting data
        """
        self.username = username
        self.password = password
        self.house_id = house_id
        self.mobile_id = None
        self.brand = brand
        self.login_attempts_left = MAX_LOGIN_ATTEMPTS
        self._state_file = state_file or f"{brand}_config_{self.username}.conf"
        self.api_key = None
        self.devices_json: list[dict[str, Any]] | None = None
        self.automations_json: list[dict[str, Any]] | None = None
        self.last_update: datetime.datetime | None = None
        self._name: str | None = None
        self.thermostats = None  # type: ignore[assignment]
        self.automations = None  # type: ignore[assignment]
        self._device_name = device_name
        self._last_update_etag = None
        self._uuid = None
        self.session = session
        self.loop = asyncio.get_running_loop()
        self.log_response = True

    @property
    def API_MOBILE_PHONE_URL(self) -> str:  # pylint: disable=invalid-name
        return f"{self.mobile_url}/phones"

    @property
    def API_MOBILE_SESSION_URL(self) -> str:  # pylint: disable=invalid-name
        return f"{self.mobile_url}/session"

    @cached_property
    def mobile_session_url(self) -> URL:
        """The mobile session url."""
        return URL(self.API_MOBILE_SESSION_URL)

    @property
    def API_MOBILE_HOUSES_URL(self) -> str:  # pylint: disable=invalid-name
        return self.mobile_url + "/houses/{house_id}"

    @cached_property
    def update_url(self) -> URL:
        """The url to update the house."""
        return URL(self.API_MOBILE_HOUSES_URL.format(house_id=self.house_id))

    @property
    def API_MOBILE_ACCOUNTS_SIGN_IN_URL(self) -> str:  # pylint: disable=invalid-name
        return f"{self.mobile_url}/accounts/sign_in"

    @cached_property
    def mobile_accounts_sign_in_url(self) -> URL:
        """The mobile accounts sign in url."""
        return URL(self.API_MOBILE_ACCOUNTS_SIGN_IN_URL)

    @property
    def AUTH_FAILED_STRING(self) -> str:  # pylint: disable=invalid-name
        return f"{self.root_url}/login"

    @property
    def AUTH_FORGOTTEN_PASSWORD_STRING(self) -> str:  # pylint: disable=invalid-name
        return f"{self.root_url}/account/forgotten_credentials"

    @cached_property
    def root_url(self) -> str:
        """The root url for the service."""
        return BRAND_TO_URL.get(self.brand, NEXIA_ROOT_URL)

    @cached_property
    def root_url_object(self) -> URL:
        """The root url for the service."""
        return URL(self.root_url)

    @property
    def mobile_url(self) -> str:
        """The mobile url for the service."""
        return MOBILE_URL_TEMPLATE.format(self.root_url)

    def resolve_url(self, raw_path: str) -> URL:
        """Determine the url of the specified raw path on the root host
        :param raw_path: url path with possibly incorrect host
        :return: url resolved on the root host
        """
        root_host = self.root_url_object.host
        root_scheme = self.root_url_object.scheme
        assert root_host is not None
        return URL(raw_path).with_scheme(root_scheme).with_host(root_host)

    def _api_key_headers(self) -> dict[str, str]:
        headers = {
            "X-AppVersion": APP_VERSION,
            "X-AssociatedBrand": self.brand,
        }
        if self.mobile_id:
            headers["X-MobileId"] = str(self.mobile_id)
        if self.api_key:
            headers["X-ApiKey"] = str(self.api_key)
        return headers

    async def _debug_log_resp(self, response: aiohttp.ClientResponse) -> None:
        if _LOGGER.isEnabledFor(logging.DEBUG):
            if self.log_response:
                _LOGGER.debug(
                    "%s: Response from url %s: status: %s:\n%s",
                    response.method,
                    response.url,
                    response.status,
                    (await response.text()).strip(),
                )
            else:
                _LOGGER.debug(
                    "%s: Response from url %s: status: %s: %s",
                    response.method,
                    response.url,
                    response.status,
                    response.content,
                )

    async def post_url(
        self, request_url: URL | str, payload: dict
    ) -> aiohttp.ClientResponse:
        """Posts data to the session from the url and payload
        :param request_url: str
        :param payload: dict
        :return: response.
        """
        headers = self._api_key_headers()
        _LOGGER.debug(
            "POST: Calling url %s with headers: %s and payload: %s",
            request_url,
            headers,
            payload,
        )

        response: aiohttp.ClientResponse = await self.session.post(
            request_url,
            json=payload,
            timeout=TIMEOUT,
            headers=headers,
            max_redirects=MAX_REDIRECTS,
        )

        await self._debug_log_resp(response)
        if response.status == 302:
            # assuming its redirecting to login
            _LOGGER.debug(
                "POST Response returned code 302, re-attempting login and resending request.",
            )
            await self.login()
            return await self.post_url(request_url, payload)

        # no need to sleep anymore as we consume the response and update the thermostat's JSON

        response.raise_for_status()
        return response

    async def _get_url(
        self,
        request_url: URL | str,
        headers: dict[str, str] | None = None,
    ) -> aiohttp.ClientResponse:
        """Returns the full session.get from the URL and headers
        :param request_url: str
        :param headers: headers to include in the get request
        :return: response.
        """
        if not headers:
            headers = {}

        headers.update(self._api_key_headers())
        _LOGGER.debug("GET: Calling url %s", request_url)
        response = await self.session.get(
            request_url,
            allow_redirects=False,
            timeout=TIMEOUT,
            headers=headers,
            max_redirects=MAX_REDIRECTS,
        )
        await self._debug_log_resp(response)

        if response.status == 302:
            _LOGGER.debug(
                "GET Response returned code 302, re-attempting login and resending request.",
            )
            # assuming its redirecting to login
            await self.login()
            return await self._get_url(request_url)

        response.raise_for_status()
        return response

    async def _check_response(
        self,
        error_text: str,
        request: aiohttp.ClientResponse,
    ) -> None:
        """Checks the request response, throws exception with the description text
        :param error_text: str
        :param request: response
        :return: None.
        """
        if request is None or request.status != 200:
            if request is not None:
                text = await request.text()
                raise ValueError(f"{error_text}\n{text}")
            raise ValueError(f"No response from session. {error_text}")

    async def _find_house_id(self) -> None:
        """Finds the house id if none is provided."""
        async with await self.post_url(
            self.mobile_session_url,
            {"app_version": APP_VERSION, "device_uuid": str(self._uuid)},
        ) as request:
            if request and request.status == 200:
                ts_json = await request.json(
                    loads=orjson.loads,  # pylint: disable=no-member
                )
                if ts_json:
                    data = ts_json["result"]["_links"]["child"][0]["data"]
                    self.house_id = data["id"]
                    self._name = data["name"]
                else:
                    raise ValueError("Nothing in the JSON")
            else:
                await self._check_response(
                    "Failed to get house id JSON, session probably timed out",
                    request,
                )

    def update_from_json(self, json_dict: dict[str, Any]) -> None:
        """Update the json from the houses endpoint if fetched externally."""
        self._name = json_dict["result"]["name"]
        self.devices_json = _extract_devices_from_houses_json(json_dict)
        self.automations_json = _extract_automations_from_houses_json(json_dict)
        self._update_devices()
        self._update_automations()

    async def update(self, force_update: bool = True) -> dict[str, Any] | None:
        """Forces a status update from nexia
        :return: None.
        """
        if not self.mobile_id:
            # not yet authenticated
            return None

        headers = {}
        if self._last_update_etag:
            headers["If-None-Match"] = self._last_update_etag

        async with await self._get_url(self.update_url, headers=headers) as response:
            if not response:
                await self._check_response(
                    "Failed to get house JSON, session probably timed out",
                    response,
                )
                return None
            if response.status == 304:
                _LOGGER.debug("Update returned 304")
                # already up to date
                return None
            if response.status != 200:
                await self._check_response(
                    "Unexpected http status while fetching house JSON",
                    response,
                )
                return None

            ts_json = await response.json()
            if ts_json:
                self._name = ts_json["result"]["name"]
                self.devices_json = _extract_devices_from_houses_json(ts_json)
                self.automations_json = _extract_automations_from_houses_json(ts_json)
                self._last_update_etag = response.headers.get("etag")
            else:
                raise ValueError("Nothing in the JSON")
        self._update_devices()
        self._update_automations()
        return ts_json

    def _update_devices(self):
        self.last_update = datetime.datetime.now()
        children = extract_children_from_devices_json(self.devices_json)
        if self.thermostats is None:
            self.thermostats = []
            for child in children:
                nexia_thermostat = NexiaThermostat(self, child)
                if not nexia_thermostat.get_zone_ids():
                    # No zones (likely an xl624 which is not supported at this time)
                    continue
                self.thermostats.append(nexia_thermostat)

        thermostat_updates_by_id = {
            child["id"]: child for child in children if "id" in child
        }
        for thermostat in self.thermostats:
            if thermostat.thermostat_id in thermostat_updates_by_id:
                thermostat.update_thermostat_json(
                    thermostat_updates_by_id[thermostat.thermostat_id],
                )

    def _update_automations(self) -> None:
        self.last_update = datetime.datetime.now()

        if self.automations is None:
            self.automations = []
            for automation_json in self.automations_json:
                self.automations.append(NexiaAutomation(self, automation_json))
            return

        automation_updates_by_id = {}
        assert self.automations_json is not None
        for automation_json in self.automations_json:
            automation_updates_by_id[automation_json["id"]] = automation_json

        for automation in self.automations:
            if automation.automation_id in automation_updates_by_id:
                automation.update_automation_json(
                    automation_updates_by_id[automation.automation_id],
                )

    ########################################################################
    # Session Methods

    async def login(self) -> None:
        """Provides you with a Nexia web session.

        All parameters should be set prior to calling this.
        - username - (str) Your email address
        - password - (str) Your login password
        - house_id - (int) Your house id
        :return: None
        """
        self._uuid = await self.loop.run_in_executor(  # type: ignore
            None,
            load_or_create_uuid,  # type: ignore
            self._state_file,  # type: ignore
        )
        if self.login_attempts_left > 0:
            payload = {
                "login": self.username,
                "password": self.password,
                "children": [],
                "childSchemas": [],
                "commitModel": None,
                "nextHref": None,
                "device_uuid": str(self._uuid),
                "device_name": self._device_name,
                "app_version": APP_VERSION,
                "is_commercial": False,
            }
            async with await self.post_url(
                self.mobile_accounts_sign_in_url, payload
            ) as request:
                if request is None or request.status not in (302, 200):
                    self.login_attempts_left -= 1
                await self._check_response("Failed to login", request)

                if str(request.url) == self.AUTH_FORGOTTEN_PASSWORD_STRING:
                    raise LoginFailedException(
                        f"Failed to login, getting redirected to {request.url}"
                        f". Try to login manually on the website.",
                    )

                json_dict = await request.json(
                    loads=orjson.loads,  # pylint: disable=no-member
                )
            if json_dict.get("success") is not True:
                error_text = json_dict.get("error", "Unknown Error")
                raise LoginFailedException(f"Failed to login, {error_text}")

            self.mobile_id = json_dict["result"]["mobile_id"]
            self.api_key = json_dict["result"]["api_key"]
        else:
            raise LoginFailedException(
                f"Failed to login after {MAX_LOGIN_ATTEMPTS} attempts! Any "
                f"more attempts may lock your account!",
            )

        if not self.house_id:
            await self._find_house_id()

    def get_name(self) -> str:
        """Name of the house."""
        assert self._name is not None
        return self._name

    def get_last_update(self) -> str:
        """Returns a string indicating the ISO formatted time string of the last
        update
        :return: The ISO formatted time string of the last update,
        datetime.datetime.min if never updated.
        """
        if self.last_update is None:
            return datetime.datetime.isoformat(datetime.datetime.min)
        return datetime.datetime.isoformat(self.last_update)

    def get_thermostat_by_id(self, thermostat_id: int | str) -> NexiaThermostat:
        """Get a thermostat by its nexia id."""
        for thermostat in self.thermostats:
            if thermostat.thermostat_id == thermostat_id:
                return thermostat
        raise KeyError(
            f"Thermostat not found: valid values are: {self.get_thermostat_ids()}"
        )

    def get_thermostat_ids(self) -> list[int | str]:
        """Returns the number of thermostats available to Nexia
        :return:
        """
        return [thermostat.thermostat_id for thermostat in self.thermostats]

    def get_automation_by_id(self, automation_id) -> NexiaAutomation:
        """Get an automation by its nexia id."""
        for automation in self.automations:
            if automation.automation_id == automation_id:
                return automation
        raise KeyError

    @cached_property
    def mobile_phone_url(self) -> URL:
        """The mobile phone url."""
        return URL(self.API_MOBILE_PHONE_URL)

    async def get_phone_ids(self) -> list[int]:
        """Get all the mobile phone ids."""
        async with await self._get_url(self.mobile_phone_url) as response:
            data = await response.json()
        items = data["result"]["items"]
        return [phone["phone_id"] for phone in items]

    def get_automation_ids(self) -> list[int]:
        """Returns the number of automations available to Nexia
        :return:
        """
        return [automation.automation_id for automation in self.automations]


def _extract_devices_from_houses_json(json_dict: dict) -> list[dict[str, Any]]:
    """Extracts the payload from the houses json endpoint data."""
    return _extract_items(
        json_dict["result"]["_links"]["child"][DEVICES_ELEMENT]["data"],
    )


def _extract_automations_from_houses_json(json_dict: dict) -> list[dict[str, Any]]:
    """Extracts the payload from the houses json endpoint data."""
    return _extract_items(
        json_dict["result"]["_links"]["child"][AUTOMATIONS_ELEMENT]["data"],
    )


def _extract_items(json_dict: dict) -> list[dict[str, Any]]:
    """Return the items key if it exists, otherwise the top level."""
    return json_dict.get("items", json_dict)
