"""GasApp device for Home Assistant integration."""

from datetime import datetime
from typing import Optional

import aiohttp
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import UpdateFailed

from .api import GasAppApiClient
from .exceptions import GasAppAuthError, GasAppConnectionError, GasAppDataError
from ..const import DOMAIN, LOGGER


class GasAppDevice:
    """GasApp device representation."""

    def __init__(
        self,
        hass,
        entry_id: str,
        token: str,
        member_id: str,
        use_contract_num: str,
        session: aiohttp.ClientSession,
    ):
        self.hass = hass
        self.entry_id = entry_id
        self.token = token
        self.member_id = member_id
        self.use_contract_num = use_contract_num
        self.session = session
        self.api_client = GasAppApiClient(self.session)
        self.api_client.set_credentials(token, member_id, use_contract_num)

        self._name = f"가스앱 ({use_contract_num})"
        self._unique_id = f"gasapp_{use_contract_num}"
        self._available = True
        self.data = {}
        self._last_update_success = None

    @property
    def unique_id(self) -> str:
        return self._unique_id

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._unique_id)},
            name=self._name,
            manufacturer="한국가스공사",
            model="가스앱",
            configuration_url="https://app.gasapp.co.kr",
        )

    @property
    def available(self) -> bool:
        return self._available

    async def async_update(self):
        """Fetch data from GasApp API."""
        try:
            # Get home data including bill information
            home_data = await self.api_client.async_get_home_data()

            # Get bill history
            bill_history = await self.api_client.async_get_bill_history()

            # Get current bill
            current_bill = await self.api_client.async_get_current_bill()

            self.data = {
                "home_data": home_data,
                "bill_history": bill_history,
                "current_bill": current_bill,
                "last_updated": datetime.now().isoformat(),
            }

            self._available = True
            self._last_update_success = datetime.now()
            LOGGER.debug(
                f"GasApp data updated successfully for {self.use_contract_num}"
            )

        except GasAppAuthError as err:
            self._available = False
            LOGGER.error(
                f"Authentication error for GasApp {self.use_contract_num}: {err}"
            )
            raise UpdateFailed(f"Authentication failed: {err}")

        except (GasAppConnectionError, GasAppDataError) as err:
            self._available = False
            LOGGER.error(
                f"Error updating GasApp data for {self.use_contract_num}: {err}"
            )
            raise UpdateFailed(f"Error communicating with GasApp API: {err}")

        except Exception as err:
            self._available = False
            LOGGER.error(
                f"Unexpected error updating GasApp data for {self.use_contract_num}: {err}"
            )
            raise UpdateFailed(f"Unexpected error: {err}")

    def get_current_month_usage(self) -> Optional[str]:
        """Get current month's gas usage."""
        if not self.data.get("current_bill"):
            return None

        history = self.data["current_bill"].get("history", [])
        if history:
            # Get the most recent entry (usually the first one)
            latest = history[0]
            return latest.get("usageQty")
        return None

    def get_current_month_charge(self) -> Optional[int]:
        """Get current month's gas charge amount."""
        if not self.data.get("current_bill"):
            return None

        history = self.data["current_bill"].get("history", [])
        if history:
            latest = history[0]
            return latest.get("chargeAmtQty")
        return None

    def get_bill_title(self) -> Optional[str]:
        """Get bill title."""
        if not self.data.get("current_bill"):
            return None
        return self.data["current_bill"].get("title1")

    def get_total_charge(self) -> Optional[str]:
        """Get total charge for current month."""
        if not self.data.get("current_bill"):
            return None
        return self.data["current_bill"].get("title2")

    async def async_close_session(self):
        """Close the aiohttp session."""
        if self.session:
            await self.session.close()
            self.session = None
