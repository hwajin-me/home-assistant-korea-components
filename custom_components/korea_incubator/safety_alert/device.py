"""Safety Alert device for Home Assistant integration."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, Any, Optional, List

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import UpdateFailed

from .api import SafetyAlertApiClient
from .exceptions import SafetyAlertConnectionError, SafetyAlertDataError
from ..const import DOMAIN, LOGGER


class SafetyAlertDevice:
    """Safety Alert device representation with type safety."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        area_code: str,
        area_name: str,
        area_code2: Optional[str] = None,
        area_code3: Optional[str] = None,
        session: aiohttp.ClientSession = None,
    ) -> None:
        """Initialize Safety Alert device."""
        self.hass: HomeAssistant = hass
        self.entry_id: str = entry_id
        self.area_code: str = area_code
        self.area_name: str = area_name
        self.area_code2: Optional[str] = area_code2
        self.area_code3: Optional[str] = area_code3
        self.session: aiohttp.ClientSession = session
        self.api_client: SafetyAlertApiClient = SafetyAlertApiClient(self.session)

        self._name: str = f"안전알림 ({area_name})"
        self._unique_id: str = f"safety_alert_{area_code}"
        self._available: bool = True
        self.data: Dict[str, Any] = {
            "has_data": False,
            "parsed_data": [],
            "count": 0,
            "last_updated": None,
        }
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
            manufacturer="행정안전부",
            model="안전알림서비스",
            configuration_url="https://www.safekorea.go.kr",
        )

    @property
    def available(self) -> bool:
        """Return if device is available."""
        return self._available

    async def async_update(self) -> None:
        """Fetch data from Safety Alert API."""
        try:
            # Get safety alerts
            result: Dict[str, Any] = await self.api_client.async_get_safety_alerts(
                self.area_code, self.area_code2, self.area_code3
            )

            # Parse alert data
            parsed_data: List[Dict[str, Any]] = result.get("disasterSmsList", [])
            count: int = result.get("rtnResult", {}).get("totCnt", 0)

            self.data = {
                "has_data": len(parsed_data) > 0,
                "metadata": {
                    "count": count,
                },
                "parsed_data": {
                    "data": parsed_data,
                },
                "last_updated": datetime.now().isoformat(),
            }

            self._available = True
            self._last_update_success = datetime.now()
            LOGGER.debug(f"Safety Alert data updated successfully for {self.area_name}")

        except (SafetyAlertConnectionError, SafetyAlertDataError) as err:
            self._available = False
            LOGGER.error(
                f"Error updating Safety Alert data for {self.area_name}: {err}"
            )
            raise UpdateFailed(f"Error communicating with Safety Alert API: {err}")

        except Exception as err:
            self._available = False
            LOGGER.error(
                f"Unexpected error updating Safety Alert data for {self.area_name}: {err}"
            )
            raise UpdateFailed(f"Unexpected error: {err}")

    async def async_close_session(self) -> None:
        """Close the aiohttp session."""
        if self.session:
            await self.session.close()
            self.session = None
