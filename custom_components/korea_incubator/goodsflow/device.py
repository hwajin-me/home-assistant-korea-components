"""GoodsFlow device for Home Assistant integration."""
from __future__ import annotations

from datetime import datetime
from typing import Dict, Any, Optional
import aiohttp
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.core import HomeAssistant

from .api import GoodsFlowApiClient
from .exceptions import GoodsFlowAuthError, GoodsFlowConnectionError, GoodsFlowDataError
from ..const import DOMAIN, LOGGER


class GoodsFlowDevice:
    """GoodsFlow device representation with type safety."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        token: str,
        session: aiohttp.ClientSession
    ) -> None:
        """Initialize GoodsFlow device."""
        self.hass: HomeAssistant = hass
        self.entry_id: str = entry_id
        self.token: str = token
        self.session: aiohttp.ClientSession = session
        self.api_client: GoodsFlowApiClient = GoodsFlowApiClient(self.session)
        self.api_client.set_token(token)

        self._name: str = "굿스플로우 택배조회"
        self._unique_id: str = f"goodsflow_{token[:8]}"
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
            manufacturer="굿스플로우",
            model="택배조회",
            configuration_url="https://ptk.goodsflow.com",
        )

    @property
    def available(self) -> bool:
        """Return if device is available."""
        return self._available

    async def async_update(self) -> None:
        """Fetch data from GoodsFlow API."""
        try:
            # Get tracking data
            tracking_data: Dict[str, Any] = await self.api_client.async_get_tracking_list()

            # Parse tracking data
            parsed_data: Dict[str, Any] = self.api_client.parse_tracking_data(tracking_data)

            self.data = {
                "raw_data": tracking_data,
                "parsed_data": parsed_data,
                "last_updated": datetime.now().isoformat(),
            }

            self._available = True
            self._last_update_success = datetime.now()
            LOGGER.debug("GoodsFlow data updated successfully")

        except GoodsFlowAuthError as err:
            self._available = False
            LOGGER.error(f"Authentication error for GoodsFlow: {err}")
            raise UpdateFailed(f"Authentication failed: {err}")

        except (GoodsFlowConnectionError, GoodsFlowDataError) as err:
            self._available = False
            LOGGER.error(f"Error updating GoodsFlow data: {err}")
            raise UpdateFailed(f"Error communicating with GoodsFlow API: {err}")

        except Exception as err:
            self._available = False
            LOGGER.error(f"Unexpected error updating GoodsFlow data: {err}")
            raise UpdateFailed(f"Unexpected error: {err}")

    def get_total_packages(self) -> int:
        """Get total number of packages."""
        if not self.data.get("parsed_data"):
            return 0
        return self.data["parsed_data"].get("total_packages", 0)

    def get_active_packages(self) -> int:
        """Get number of active packages (in transit)."""
        if not self.data.get("parsed_data"):
            return 0
        return self.data["parsed_data"].get("active_packages", 0)

    def get_delivered_packages(self) -> int:
        """Get number of delivered packages."""
        if not self.data.get("parsed_data"):
            return 0
        return self.data["parsed_data"].get("delivered_packages", 0)

    async def async_close_session(self) -> None:
        """Close the aiohttp session."""
        if self.session:
            await self.session.close()
            self.session = None
