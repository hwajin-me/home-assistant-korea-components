"""Fuel price coordinator - fetches for all configured sido/fuel combos."""
from __future__ import annotations
import logging
from datetime import timedelta
from typing import Any
import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from . import FUEL_SCAN_INTERVAL
from .api import fetch_avg_price, fetch_low_price

_LOGGER = logging.getLogger(__name__)


class FuelCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(self, hass: HomeAssistant, api_key: str,
                 configs: list[dict[str, str]]) -> None:
        super().__init__(hass, _LOGGER, name="fuel",
                         update_interval=timedelta(seconds=FUEL_SCAN_INTERVAL))
        self._api_key = api_key
        self._configs = configs  # [{"sido_code": ..., "fuel_code": ...}, ...]

    async def _async_update_data(self):
        result: dict[str, Any] = {}
        async with aiohttp.ClientSession() as session:
            # Average price (전국) - one call
            try:
                result["average"] = await fetch_avg_price(session, self._api_key)
            except Exception as e:
                _LOGGER.warning("Fuel avg fetch error: %s", e)
                result["average"] = []

            # Low price per sido/fuel combo
            for cfg in self._configs:
                key = f"{cfg['sido_code']}_{cfg['fuel_code']}"
                try:
                    result[f"low_{key}"] = await fetch_low_price(
                        session, self._api_key, cfg["sido_code"], cfg["fuel_code"])
                except Exception as e:
                    _LOGGER.warning("Fuel low price fetch error %s: %s", key, e)
                    result[f"low_{key}"] = []

        return result
