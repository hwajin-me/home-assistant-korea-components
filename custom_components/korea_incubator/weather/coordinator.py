"""Weather warning coordinator."""
from __future__ import annotations
import logging
from datetime import timedelta
from typing import Any
import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from . import WARNING_SCAN_SEC, WARNING_TYPES, EVENT_TYPE_NONE
from .api import fetch_warning

_LOGGER = logging.getLogger(__name__)

class WeatherWarningCoordinator(DataUpdateCoordinator[dict[str, dict[int, dict[str, Any]]]]):
    """Fetches warnings for ALL configured areas in one coordinator."""
    def __init__(self, hass: HomeAssistant, api_key: str, area_codes: list[str]) -> None:
        super().__init__(hass, _LOGGER, name="kr_weather",
                         update_interval=timedelta(seconds=WARNING_SCAN_SEC))
        self._api_key = api_key
        self._area_codes = area_codes

    async def _async_update_data(self):
        results: dict[str, dict[int, dict[str, Any]]] = {}
        async with aiohttp.ClientSession() as session:
            for ac in self._area_codes:
                results[ac] = {}
                for wt in WARNING_TYPES:
                    try:
                        results[ac][wt] = await fetch_warning(session, self._api_key, ac, wt)
                    except Exception:
                        results[ac][wt] = {"event_type": EVENT_TYPE_NONE, "raw": None}
        return results
