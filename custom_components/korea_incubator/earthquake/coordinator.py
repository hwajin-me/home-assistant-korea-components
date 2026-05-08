"""Earthquake coordinator."""
from __future__ import annotations
import logging
from datetime import timedelta
from typing import Any
import aiohttp
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from . import SCAN_INTERVAL
from .api import fetch_earthquakes

_LOGGER = logging.getLogger(__name__)

class EarthquakeCoordinator(DataUpdateCoordinator[list[dict[str, Any]]]):
    def __init__(self, hass, api_key):
        super().__init__(hass, _LOGGER, name="earthquake",
                         update_interval=timedelta(seconds=SCAN_INTERVAL))
        self._api_key = api_key

    async def _async_update_data(self):
        try:
            async with aiohttp.ClientSession() as session:
                return await fetch_earthquakes(session, self._api_key)
        except Exception as e:
            raise UpdateFailed(f"Earthquake error: {e}") from e
