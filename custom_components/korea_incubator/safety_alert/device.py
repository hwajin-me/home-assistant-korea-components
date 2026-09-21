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
from ..const import DOMAIN, LOGGER, TZ_ASIA_SEOUL


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
        session: aiohttp.ClientSession = None,  # __init__.py에서 항상 전달됨
        area_name2: Optional[str] = None,
        area_name3: Optional[str] = None,
    ) -> None:
        """Initialize Safety Alert device."""
        self.hass: HomeAssistant = hass
        self.entry_id: str = entry_id
        self.area_code: str = area_code
        self.area_name: str = area_name
        self.area_code2: Optional[str] = area_code2
        self.area_code3: Optional[str] = area_code3
        self.area_name2: Optional[str] = area_name2
        self.area_name3: Optional[str] = area_name3
        self.session: aiohttp.ClientSession = session  # 타입 힌트 수정
        self.api_client: SafetyAlertApiClient = SafetyAlertApiClient(self.session)

        self._name: str = f"안전알림 ({area_name})"
        # A single config entry represents one selected administrative region.
        # The previous ID used only the sido code, so every sgg/emd below the
        # same sido produced identical entity and device IDs. Prefer numeric
        # region codes and retain names as a fallback for manual region input.
        region_identifiers = [
            area_code,
            area_code2 or area_name2,
            area_code3 or area_name3,
        ]
        self._unique_id = "safety_alert_" + "_".join(
            identifier for identifier in region_identifiers if identifier
        )
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
                "last_updated": datetime.now(TZ_ASIA_SEOUL).isoformat(),
            }

            self._available = True
            self._last_update_success = datetime.now(TZ_ASIA_SEOUL)
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
