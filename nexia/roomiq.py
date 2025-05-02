"""Nexia RoomIQ utility class."""

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any

from .util import SingleShot
from .zone import NexiaThermostatZone


class NexiaRoomIQHarmonizer:
    """Controller to track which RoomIQ sensors are to be
    selected for a zone and make the selection after inactivity.

    This helps coordinate separate manual actions taken to select active sensors.
    """

    def __init__(
        self,
        zone: NexiaThermostatZone,
        async_request_refetch: Callable[[], Coroutine[Any, Any, None]],
        signal_updated: Callable[[], None],
        after_last_change_seconds=4.0,
    ) -> None:
        """Initialize this instance.

        :param zone: zone to control
        :param async_request_refetch: coroutine to request a refetch of zone status
        :param signal_updated: function to signal that our state has changed
        :param after_last_change_seconds: seconds to delay before selecting sensors
        """
        self.selected_sensor_ids = zone.get_active_sensor_ids()
        self._zone = zone
        self._async_request_refetch = async_request_refetch
        self._signal_updated = signal_updated
        self._loop = asyncio.get_running_loop()
        self._request_time: float | None = None
        self._single_shot = SingleShot(
            self._loop, after_last_change_seconds, self._select_sensors
        )

    def trigger_add_sensor(self, sensor_id: int) -> None:
        """Trigger selecting the specified sensor for the zone."""
        self._request_time = self._loop.time()
        self.selected_sensor_ids.add(sensor_id)
        self._single_shot.reset_delayed_action_trigger()

    def trigger_remove_sensor(self, sensor_id: int) -> None:
        """Trigger removing the specified sensor from the zone selection."""
        self._request_time = self._loop.time()
        self.selected_sensor_ids.discard(sensor_id)
        self._single_shot.reset_delayed_action_trigger()

    async def _select_sensors(self) -> None:
        """Select the RoomIQ sensors now that the delay has completed.

        Fires a while following the *last* trigger in the zone's sensor selections.
        """
        active_sensors = self._zone.get_active_sensor_ids()

        # At least one sensor must be selected and the request should differ.
        if not self.selected_sensor_ids or self.selected_sensor_ids == active_sensors:
            self.selected_sensor_ids = active_sensors
            self._request_time = None
            self._signal_updated()
            return

        select_time = self._request_time
        try:
            await self._zone.select_room_iq_sensors(self.selected_sensor_ids)
        finally:
            if self._request_time == select_time:
                # No new requests have triggered.
                self._request_time = None
            await self._async_request_refetch()
            self._signal_updated()

    def request_pending(self) -> bool:
        """Return if a triggered sensor selection is pending."""
        return self._request_time is not None

    async def async_shutdown(self) -> None:
        """Clean up before stopping."""
        self._single_shot.async_shutdown()
        self._request_time = None
        self._signal_updated()
