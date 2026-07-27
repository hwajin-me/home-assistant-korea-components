"""GasApp API client for Home Assistant integration."""

from typing import Dict, Any, Optional

import aiohttp

from .exceptions import GasAppAuthError, GasAppConnectionError, GasAppDataError
from ..const import LOGGER


class GasAppApiClient:
    """API client for GasApp integration."""

    def __init__(self, session: aiohttp.ClientSession):
        self._session = session
        self._token = None
        self._member_id = None
        self._use_contract_num = None
        self._base_url = "https://app.gasapp.co.kr/api"

    def set_credentials(self, token: str, member_id: str, use_contract_num: str):
        """Set authentication credentials."""
        self._token = token
        self._member_id = member_id
        self._use_contract_num = use_contract_num

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with authentication."""
        if not self._token or not self._member_id:
            raise GasAppAuthError("Credentials not set")

        return {
            "X-Token": self._token,
            "X-Member": self._member_id,
            "X-Company": "1",
            "X-Version": "4.2.5.24144",
            "Host": "app.gasapp.co.kr",
            "Connection": "close",
        }

    async def async_validate_credentials(self) -> bool:
        """Validate the provided credentials by making a test API call."""
        try:
            data = await self.async_get_home_data()
            return data is not None
        except Exception as e:
            LOGGER.error(f"Credential validation failed: {e}")
            return False

    async def _request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make an authenticated request to the GasApp API."""
        url = f"{self._base_url}/{endpoint}"
        headers = self._get_headers()

        try:
            async with self._session.request(
                method, url, headers=headers, **kwargs
            ) as response:
                LOGGER.debug(f"GasApp API request to {url} status: {response.status}")

                if response.status == 401:
                    raise GasAppAuthError("Authentication failed")
                elif response.status == 403:
                    raise GasAppAuthError("Access denied")
                elif response.status >= 400:
                    raise GasAppConnectionError(
                        f"HTTP {response.status}: {response.reason}"
                    )

                response.raise_for_status()
                return await response.json()

        except aiohttp.ClientError as e:
            LOGGER.error(f"GasApp API request failed: {e}")
            raise GasAppConnectionError(f"Request failed: {e}")
        except Exception as e:
            LOGGER.error(f"Unexpected error in GasApp API request: {e}")
            raise GasAppDataError(f"Unexpected error: {e}")

    async def async_get_home_data(self) -> Dict[str, Any]:
        """Get home dashboard data including bill information."""
        if not self._use_contract_num:
            raise GasAppAuthError("Use contract number not set")

        params = {
            "useContractNum": self._use_contract_num,
            "customerNum": "",
            "amiYn": "N",
        }

        return await self._request("GET", "home", params=params)

    async def async_get_bill_history(self) -> Optional[list]:
        """Get bill payment history."""
        try:
            home_data = await self.async_get_home_data()
            if "cards" in home_data and "bill" in home_data["cards"]:
                return home_data["cards"]["bill"].get("history", [])
            return None
        except Exception as e:
            LOGGER.error(f"Failed to get bill history: {e}")
            raise GasAppDataError(f"Failed to get bill history: {e}")

    async def async_get_current_bill(self) -> Optional[Dict[str, Any]]:
        """Get current month's bill information."""
        try:
            home_data = await self.async_get_home_data()
            if "cards" in home_data and "bill" in home_data["cards"]:
                return home_data["cards"]["bill"]
            return None
        except Exception as e:
            LOGGER.error(f"Failed to get current bill: {e}")
            raise GasAppDataError(f"Failed to get current bill: {e}")
