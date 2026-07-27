"""Subway arrival coordinator - uses bulk API, shared per station."""
from __future__ import annotations
import logging
from datetime import timedelta
from typing import Any
import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from . import SUBWAY_SCAN_INTERVAL
from .subway_api import fetch_bulk_arrivals, filter_arrivals

_LOGGER = logging.getLogger(__name__)

class SubwayCoordinator(DataUpdateCoordinator[dict[str, list[dict[str, Any]]]]):
    """One coordinator per station - fetches bulk, filters per direction/line."""
    def __init__(self, hass: HomeAssistant, api_key: str, station: str,
                 subscriptions: list[dict]) -> None:
        super().__init__(hass, _LOGGER, name=f"subway_{station}",
                         update_interval=timedelta(seconds=SUBWAY_SCAN_INTERVAL))
        self._api_key = api_key
        self._station = station
        self.subscriptions = subscriptions  # [{"direction": ..., "line_id": ...}, ...]

    async def _async_update_data(self):
        async with aiohttp.ClientSession() as session:
            raw = await fetch_bulk_arrivals(session, self._api_key, self._station)
        result = {}
        for sub in self.subscriptions:
            key = f"{sub['direction']}_{sub.get('line_id', '')}"
            result[key] = filter_arrivals(raw, sub["direction"], sub.get("line_id"))
        return result
