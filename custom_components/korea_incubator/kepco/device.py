from __future__ import annotations

from datetime import datetime
from typing import Dict, Any, Optional

import aiohttp
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.core import HomeAssistant

from .api import KepcoApiClient
from ..const import DOMAIN, LOGGER


class KepcoDevice:
    """KEPCO device representation with type safety."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        username: str,
        password: str,
        session: aiohttp.ClientSession
    ) -> None:
        """Initialize KEPCO device."""
        self.hass: HomeAssistant = hass
        self.entry_id: str = entry_id
        self.username: str = username
        self.password: str = password
        self.session: aiohttp.ClientSession = session
        self.api_client: KepcoApiClient = KepcoApiClient(self.session)
        self.api_client.set_credentials(username, password)  # Set credentials for re-auth

        self._name: str = f"한전 ({username})"
        self._unique_id: str = f"kepco_{username}"
        self._available: bool = True
        self.data: Dict[str, Any] = {}
        self._last_update_success: Optional[datetime] = None

    @property
    def unique_id(self) -> str:
        """Return unique ID."""
        return self._unique_id

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._unique_id)},
            name=self._name,
            manufacturer="KEPCO",
            model="Power Planner",
            configuration_url="https://pp.kepco.co.kr",
        )

    @property
    def available(self) -> bool:
        """Return if device is available."""
        return self._available

    async def async_update(self) -> None:
        """Fetch data from KEPCO API."""
        try:
            recent_usage: Dict[str, Any] = await self.api_client.async_get_recent_usage()
            usage_info: Dict[str, Any] = await self.api_client.async_get_usage_info()
            self.data = {
                "recent_usage": recent_usage,
                "usage_info": usage_info,
            }
            self._available = True
            self._last_update_success = datetime.now()
            LOGGER.debug(f"KEPCO data updated successfully for {self.username}")
        except Exception as err:
            self._available = False
            LOGGER.error(f"Error updating KEPCO data for {self.username}: {err}")
            raise UpdateFailed(f"Error communicating with KEPCO API: {err}")

    async def async_close_session(self) -> None:
        """Close the aiohttp session."""
        if self.session:
            await self.session.close()
            self.session = None
