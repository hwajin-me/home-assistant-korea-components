"""AirKorea coordinator."""
from __future__ import annotations
import logging
from datetime import timedelta
from typing import Any
import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from . import SCAN_INTERVAL, SIDO_AREA_CODE
from .api import fetch_realtime, fetch_forecast, fetch_uv_index, fetch_air_stagnation

_LOGGER = logging.getLogger(__name__)


class AirKoreaCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(self, hass, api_key, stations, living_api_key="", sido=""):
        super().__init__(hass, _LOGGER, name="airkorea",
                         update_interval=timedelta(seconds=SCAN_INTERVAL))
        self._api_key = api_key
        self._stations = stations
        self._living_key = living_api_key or api_key
        self._area_code = SIDO_AREA_CODE.get(sido, "1100000000")

    async def _async_update_data(self):
        result = {"stations": {}, "forecast": [], "uv": {}, "stagnation": {}}
        async with aiohttp.ClientSession() as session:
            for st in self._stations:
                name = st["stationName"]
                try:
                    result["stations"][name] = await fetch_realtime(
                        session, self._api_key, name)
                except Exception as e:
                    _LOGGER.warning("AirKorea realtime %s: %s", name, e)
            try:
                result["forecast"] = await fetch_forecast(session, self._api_key)
            except Exception as e:
                _LOGGER.warning("AirKorea forecast: %s", e)
            # Living indices - shared for the region
            try:
                result["uv"] = await fetch_uv_index(
                    session, self._living_key, self._area_code)
            except Exception:
                pass
            try:
                result["stagnation"] = await fetch_air_stagnation(
                    session, self._living_key, self._area_code)
            except Exception:
                pass
        return result
