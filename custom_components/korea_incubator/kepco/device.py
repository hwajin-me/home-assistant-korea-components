from datetime import datetime

import aiohttp
from curl_cffi import AsyncSession
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import UpdateFailed

from .api import KepcoApiClient
from .exceptions import KepcoAuthError
from ..const import DOMAIN, LOGGER


class KepcoDevice:
    def __init__(
        self,
        hass,
        entry_id: str,
        username: str,
        password: str,
        session: aiohttp.ClientSession | AsyncSession,
    ):
        self.hass = hass
        self.entry_id = entry_id
        self.username = username
        self.password = password
        self.session = session
        self.api_client = KepcoApiClient(self.session)
        self.api_client.set_credentials(
            username, password
        )  # Set credentials for re-auth

        self._name = f"한전 ({username})"
        self._unique_id = f"kepco_{username}"
        self._available = True
        self.data = {}  # 초기화 추가

    @property
    def unique_id(self) -> str:
        return self._unique_id

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._unique_id)},
            name=self._name,
            manufacturer="한국전력공사",
            model="KEPCO",
            configuration_url="https://pp.kepco.co.kr",
        )

    @property
    def available(self) -> bool:
        return self._available

    async def async_update(self):
        """Fetch data from KEPCO API."""
        try:
            recent_usage = await self.api_client.async_get_recent_usage()
            usage_info = await self.api_client.async_get_usage_info()
            self.data = {
                "recent_usage": recent_usage,
                "usage_info": usage_info,
            }
            self._available = True
            self._last_update_success = datetime.now()
            LOGGER.debug(f"KEPCO data updated successfully for {self.username}")
        except KepcoAuthError as err:
            self._available = False
            LOGGER.error(
                f"Authentication error updating KEPCO data for {self.username}: {err}"
            )
            raise UpdateFailed(f"Authentication error: {err}")
        except Exception as err:
            self._available = False
            LOGGER.error(f"Error updating KEPCO data for {self.username}: {err}")
            raise UpdateFailed(f"Error communicating with KEPCO API: {err}")

    def get_current_usage(self):
        """현재 사용량 조회"""
        try:
            return self.data.get("recent_usage", {}).get("result", {}).get("F_AP_QT")
        except (KeyError, AttributeError):
            return None

    def get_last_month_bill(self):
        """지난달 요금 조회"""
        try:
            return (
                self.data.get("usage_info", {}).get("result", {}).get("BILL_LAST_MONTH")
            )
        except (KeyError, AttributeError):
            return None

    def get_predicted_bill(self):
        """예상 요금 조회"""
        try:
            return (
                self.data.get("usage_info", {})
                .get("result", {})
                .get("PREDICT_TOTAL_CHARGE_REV")
            )
        except (KeyError, AttributeError):
            return None

    async def async_close_session(self):
        """Close the aiohttp session."""
        if (
            self.session
            and isinstance(self.session, aiohttp.ClientSession)
            and not self.session.closed
        ):
            await self.session.close()
            self.session = None
        elif isinstance(self.session, AsyncSession):
            await self.session.close()
            self.session = None
