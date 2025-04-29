"""Utils."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Callable, Coroutine
from json import JSONDecodeError
from typing import Any


def is_number(string: str) -> bool:
    """String is a number."""
    try:
        float(string)
    except ValueError:
        return False

    return True


def find_dict_with_keyvalue_in_json(
    json_dict: list[dict[str, Any]], key_in_subdict: str, value_to_find: Any
) -> Any:
    """Searches a json_dict for the key key_in_subdict that matches value_to_find
    :param json_dict: dict
    :param key_in_subdict: str - the name of the key in the subdict to find
    :param value_to_find: str - the value of the key in the subdict to find
    :return: The subdict to find.
    """
    for data_group in json_dict:
        if data_group.get(key_in_subdict) == value_to_find:
            return data_group

    raise KeyError(f"`{key_in_subdict}` with value `{value_to_find}` not found in data")


def load_or_create_uuid(filename: str) -> uuid.UUID | None:
    """Load or create a uuid for the device."""
    try:
        with open(filename, encoding="utf-8") as fptr:
            jsonf = json.loads(fptr.read())
            return uuid.UUID(jsonf["nexia_uuid"], version=4)
    except (JSONDecodeError, FileNotFoundError):
        return _create_uuid(filename)
    except (ValueError, AttributeError):
        return None


def _create_uuid(filename):
    """Create a uuid for the device."""
    with open(filename, "w", encoding="utf-8") as fptr:
        new_uuid = uuid.uuid4()
        fptr.write(json.dumps({"nexia_uuid": str(new_uuid)}))
        return new_uuid


def find_humidity_setpoint(setpoint: float) -> float:
    """Find the closest humidity setpoint."""
    return round(0.05 * round(setpoint / 0.05), 2)


class SingleShot:
    """Provide a single shot timer that can be reset.

    Fire a while following the *last* call to `reset_delayed_action_trigger`.
    Caller should use `async_shutdown` to clean up when no longer needed.
    """

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        delay_seconds: float,
        delayed_coro: Callable[[], Coroutine[Any, Any, None]],
    ) -> None:
        """Initialize this single shot timer.

        :param loop: running event loop
        :param delay_seconds: seconds to delay before scheduling call
        :param delayed_coro: coroutine to call after delay
        """
        self._loop = loop
        self._delay = delay_seconds
        self._delayed_coro = delayed_coro
        self._cancel_delayed_action: asyncio.TimerHandle | None = None
        self._execute_lock = asyncio.Lock()
        self._shutting_down = False

    async def _delayed_action(self) -> None:
        """Perform the action now that the delay has completed."""
        self._cancel_delayed_action = None

        async with self._execute_lock:
            # Abort if rescheduled while waiting for the lock or shutting down.
            if self._cancel_delayed_action or self._shutting_down:
                return

            # Perform the primary action for this timer.
            await self._delayed_coro()

    def reset_delayed_action_trigger(self) -> None:
        """Set or reset the delayed action trigger.

        Perform the action a while after this call.
        """
        if self._shutting_down:
            return
        if self._cancel_delayed_action:
            self._cancel_delayed_action.cancel()

        # Use lambda to defer creating awaitable object until needed
        self._cancel_delayed_action = self._loop.call_later(
            self._delay, lambda: self._loop.create_task(self._delayed_action())
        )

    def action_pending(self) -> bool:
        """Return if a delayed action is pending."""
        return self._cancel_delayed_action is not None

    def async_shutdown(self) -> None:
        """Clean up."""
        self._shutting_down = True
        if self._cancel_delayed_action:
            self._cancel_delayed_action.cancel()
            self._cancel_delayed_action = None
        self._delayed_coro = None  # type: ignore[assignment]
