"""Pharmacy coordinator."""
from __future__ import annotations
import logging
from datetime import timedelta
from typing import Any
import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from . import PHARMACY_SCAN_INTERVAL
from .api import fetch_pharmacies

_LOGGER = logging.getLogger(__name__)

class PharmacyCoordinator(DataUpdateCoordinator[list[dict[str, Any]]]):
    def __init__(self, hass, api_key, q0, q1=""):
        super().__init__(hass, _LOGGER, name="pharmacy",
                         update_interval=timedelta(seconds=PHARMACY_SCAN_INTERVAL))
        self._api_key = api_key
        self._q0 = q0
        self._q1 = q1

    async def _async_update_data(self):
        try:
            async with aiohttp.ClientSession() as session:
                return await fetch_pharmacies(session, self._api_key, self._q0, self._q1)
        except Exception as e:
            raise UpdateFailed(f"Pharmacy error: {e}") from e
