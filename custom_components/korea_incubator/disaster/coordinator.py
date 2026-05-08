"""Disaster message coordinator - resilient to intermittent SSL errors."""
from __future__ import annotations
import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from . import DISASTER_SCAN_INTERVAL
from .api import fetch_disaster_messages

_LOGGER = logging.getLogger(__name__)


class DisasterCoordinator(DataUpdateCoordinator[list[dict[str, Any]]]):
    def __init__(self, hass, api_key, region_filter=""):
        super().__init__(hass, _LOGGER, name="disaster",
                         update_interval=timedelta(seconds=DISASTER_SCAN_INTERVAL))
        self._api_key = api_key
        self._region_filter = region_filter
        self._consecutive_failures = 0

    async def _async_update_data(self):
        try:
            all_msgs = await fetch_disaster_messages(self._api_key, count=30)
            self._consecutive_failures = 0
        except Exception as err:
            self._consecutive_failures += 1
            # Tolerate transient TLS/connection errors. If we have stale data,
            # keep serving it; on first load (no stale data), return an empty
            # list so the entry still loads instead of marking the whole
            # integration as failed. UpdateFailed kicks in only after we've
            # observed sustained failures.
            if self._consecutive_failures <= 5:
                _LOGGER.warning(
                    "Disaster API transient error (%d/5): %s",
                    self._consecutive_failures, err)
                return self.data if self.data is not None else []
            raise UpdateFailed(f"Disaster API error: {err}") from err

        if self._region_filter:
            return [m for m in all_msgs
                    if self._region_filter in (m.get("area") or "")]
        return all_msgs
