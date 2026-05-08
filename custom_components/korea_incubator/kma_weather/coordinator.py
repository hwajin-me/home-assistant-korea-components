"""KMA Weather coordinator - fetches forecast + O3 + UV in sync."""
from __future__ import annotations
import logging
from datetime import timedelta
from typing import Any
import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from . import KMA_SCAN_INTERVAL
from .api import fetch_vilage_forecast, parse_weather

_LOGGER = logging.getLogger(__name__)


class KMAWeatherCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(self, hass, api_key, regions,
                 air_api_key="", air_station="",
                 living_api_key="", area_no=""):
        super().__init__(hass, _LOGGER, name="kma_weather",
                         update_interval=timedelta(seconds=KMA_SCAN_INTERVAL))
        self._api_key = api_key
        self._regions = regions
        self._air_key = air_api_key or api_key
        self._air_station = air_station
        self._living_key = living_api_key or api_key
        self._area_no = area_no

    async def _async_update_data(self):
        result = {}
        async with aiohttp.ClientSession() as session:
            # 1. Fetch weather forecast per region
            for reg in self._regions:
                name = reg["name"]
                try:
                    items = await fetch_vilage_forecast(
                        session, self._api_key, reg["nx"], reg["ny"])
                    result[name] = parse_weather(items)
                except Exception as e:
                    _LOGGER.warning("KMA weather %s: %s", name, e)
                    result[name] = {}

            # 2. Fetch O3 from AirKorea (same session, same update cycle)
            if self._air_station:
                try:
                    from ..airkorea.api import fetch_realtime
                    air = await fetch_realtime(session, self._air_key, self._air_station)
                    if air:
                        o3 = air.get("o3Value")
                        if o3 and o3 != "-":
                            for name in result:
                                result[name]["ozone"] = float(o3)
                except Exception as e:
                    _LOGGER.debug("KMA O3 fetch: %s", e)

            # 3. Fetch UV index from Living Weather V4 (same session)
            if self._area_no:
                try:
                    from ..airkorea.api import fetch_uv_index
                    uv = await fetch_uv_index(session, self._living_key, self._area_no)
                    if uv:
                        from datetime import datetime
                        from zoneinfo import ZoneInfo
                        now = datetime.now(ZoneInfo("Asia/Seoul"))
                        h = (now.hour // 3) * 3
                        for field in [f"h{h}", "h0"]:
                            val = uv.get(field)
                            if val and str(val).strip():
                                try:
                                    uv_val = float(val)
                                    for name in result:
                                        result[name]["uv_index"] = uv_val
                                    break
                                except (ValueError, TypeError):
                                    pass
                except Exception as e:
                    _LOGGER.debug("KMA UV fetch: %s", e)

        return result
