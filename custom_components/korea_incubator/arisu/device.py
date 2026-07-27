"""Arisu device for Home Assistant integration."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, Any, Optional

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import UpdateFailed

from .api import ArisuApiClient
from .exceptions import ArisuAuthError, ArisuConnectionError, ArisuDataError
from ..const import DOMAIN, LOGGER


class ArisuDevice:
    """Arisu device representation with type safety."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        customer_number: str,
        customer_name: str,
        session: aiohttp.ClientSession,
    ) -> None:
        """Initialize Arisu device."""
        self.hass: HomeAssistant = hass
        self.entry_id: str = entry_id
        self.customer_number: str = customer_number
        self.customer_name: str = customer_name
        self.session: aiohttp.ClientSession = session
        self.api_client: ArisuApiClient = ArisuApiClient(self.session)

        self._name: str = f"아리수 ({customer_number})"
        self._unique_id: str = f"arisu_{customer_number}"
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
            manufacturer="서울시",
            model="아리수 상수도 고객센터",
            configuration_url="https://i121.seoul.go.kr",
        )

    @property
    def available(self) -> bool:
        """Return if device is available."""
        return self._available

    async def async_update(self) -> None:
        """Fetch data from Arisu API."""
        try:
            # Get water bill data (현재 월과 지난달 자동 조회)
            bill_data: Dict[str, Any] = await self.api_client.async_get_water_bill_data(
                self.customer_number, self.customer_name
            )

            if not bill_data.get("success", False):
                raise ArisuDataError(bill_data.get("error", "Unknown error"))

            self.data = {
                "bill_data": bill_data,
                "last_updated": datetime.now().isoformat(),
            }

            self._available = True
            self._last_update_success = datetime.now()
            LOGGER.debug(f"Arisu data updated successfully for {self.customer_number}")

        except ArisuAuthError as err:
            self._available = False
            LOGGER.error(
                f"Authentication error for Arisu {self.customer_number}: {err}"
            )
            raise UpdateFailed(f"Authentication failed: {err}")

        except (ArisuConnectionError, ArisuDataError) as err:
            self._available = False
            LOGGER.error(f"Error updating Arisu data for {self.customer_number}: {err}")
            raise UpdateFailed(f"Error communicating with Arisu API: {err}")

        except Exception as err:
            self._available = False
            LOGGER.error(
                f"Unexpected error updating Arisu data for {self.customer_number}: {err}"
            )
            raise UpdateFailed(f"Unexpected error: {err}")

    def get_total_amount(self) -> int:
        """Get total bill amount."""
        if not self.data.get("bill_data"):
            return 0
        return self.data["bill_data"].get("total_amount", 0)

    def get_current_usage(self) -> Optional[int]:
        """Get current water usage."""
        if not self.data.get("bill_data"):
            return None
        usage_info = self.data["bill_data"].get("usage_info", {})
        return usage_info.get("current_usage")

    def get_customer_address(self) -> Optional[str]:
        """Get customer address."""
        if not self.data.get("bill_data"):
            return None
        customer_info = self.data["bill_data"].get("customer_info", {})
        return customer_info.get("address")

    def get_payment_method(self) -> Optional[str]:
        """Get payment method."""
        if not self.data.get("bill_data"):
            return None
        customer_info = self.data["bill_data"].get("customer_info", {})
        return customer_info.get("payment_method")

    def get_overdue_amount(self) -> int:
        """Get overdue amount."""
        if not self.data.get("bill_data"):
            return 0
        arrears_info = self.data["bill_data"].get("arrears_info", {})
        return arrears_info.get("overdue_amount", 0)

    def get_billing_month(self) -> Optional[str]:
        """Get current billing month."""
        if not self.data.get("bill_data"):
            return None
        return self.data["bill_data"].get("billing_month")

    async def async_close_session(self) -> None:
        """Close the aiohttp session."""
        if self.session:
            await self.session.close()
            self.session = None
