"""Bus arrival coordinator using KakaoMap API."""
from __future__ import annotations
import logging
from datetime import timedelta
from typing import Any
import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from .bus_api import fetch_stop_data, build_bus_dict

_LOGGER = logging.getLogger(__name__)


class BusCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """One coordinator per bus stop - fetches from KakaoMap."""
    def __init__(self, hass: HomeAssistant, stop_id: str, stop_name: str) -> None:
        super().__init__(hass, _LOGGER, name=f"bus_{stop_id}",
                         update_interval=timedelta(seconds=90))
        self.stop_id = stop_id
        self.stop_name = stop_name
        self._session = async_get_clientsession(hass)

    async def _async_update_data(self):
        try:
            data = await fetch_stop_data(self._session, self.stop_id)
            return build_bus_dict(data)
        except Exception as err:
            if self.data:
                _LOGGER.warning("Bus fetch error for %s, keeping stale data: %s",
                                self.stop_id, err)
                return self.data
            raise UpdateFailed(f"Bus API error: {err}") from err
