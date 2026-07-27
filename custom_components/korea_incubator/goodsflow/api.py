"""GoodsFlow API client for Home Assistant integration."""

from typing import Dict, Any

import aiohttp

from .exceptions import GoodsFlowAuthError, GoodsFlowConnectionError, GoodsFlowDataError
from ..const import LOGGER


class GoodsFlowApiClient:
    """API client for GoodsFlow integration."""

    def __init__(self, session: aiohttp.ClientSession):
        self._session = session
        self._token = None
        self._base_url = "https://ptk.goodsflow.com/ptk/rest"

    def set_token(self, token: str):
        """Set authentication token."""
        self._token = token

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with authentication."""
        if not self._token:
            raise GoodsFlowAuthError("Token not set")

        return {
            "Accept": "*/*",
            "Connection": "keep-alive",
            "Cookie": f"PTK-TOKEN={self._token};Max-Age=1209600;path=/ptk;Secure;HttpOnly",
            "User-Agent": "HomeAssistant-Korea-Components/1.0",
            "Accept-Language": "ko-KR;q=1.0, en-US;q=0.9",
            "Accept-Encoding": "gzip",
            "X-Requested-With": "XMLHttpRequest",
        }

    async def async_validate_token(self) -> bool:
        """Validate the provided token by making a test API call."""
        try:
            data = await self.async_get_tracking_list()
            return True
        except Exception as e:
            LOGGER.error(f"Token validation failed: {e}")
            return False

    async def _request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make an authenticated request to the GoodsFlow API."""
        url = f"{self._base_url}/{endpoint}"
        headers = self._get_headers()

        try:
            async with self._session.request(
                method, url, headers=headers, **kwargs
            ) as response:
                LOGGER.debug(
                    f"GoodsFlow API request to {url} status: {response.status}"
                )

                if response.status == 401:
                    raise GoodsFlowAuthError("Authentication failed")
                elif response.status == 403:
                    raise GoodsFlowAuthError("Access denied")
                elif response.status >= 400:
                    raise GoodsFlowConnectionError(
                        f"HTTP {response.status}: {response.reason}"
                    )

                response.raise_for_status()
                return await response.json()

        except aiohttp.ClientError as e:
            LOGGER.error(f"GoodsFlow API request failed: {e}")
            raise GoodsFlowConnectionError(f"Request failed: {e}")
        except Exception as e:
            LOGGER.error(f"Unexpected error in GoodsFlow API request: {e}")
            raise GoodsFlowDataError(f"Unexpected error: {e}")

    async def async_get_tracking_list(
        self, limit: int = 10, start: int = 0, type_filter: str = "ALL"
    ) -> Dict[str, Any]:
        """Get tracking list from GoodsFlow API."""
        params = {"limit": str(limit), "start": str(start), "type": type_filter}

        return await self._request("GET", "trans/trace/list/v3", params=params)

    def parse_tracking_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse and organize tracking data."""
        if not data or not data.get("success"):
            return {
                "total_packages": 0,
                "active_packages": 0,
                "delivered_packages": 0,
                "packages": [],
            }

        trans_list = data.get("data", {}).get("transList", {})
        packages = trans_list.get("rows", [])
        total_count = trans_list.get("totalCount", 0)

        # Count packages by status
        active_count = 0
        delivered_count = 0

        for package in packages:
            # This would need to be adjusted based on actual package status fields
            # Since the HAR shows empty data, we'll prepare the structure
            status = package.get("status", "unknown")
            if status in ["배송중", "상품준비중", "배송준비중"]:
                active_count += 1
            elif status in ["배송완료", "수령완료"]:
                delivered_count += 1

        return {
            "total_packages": total_count,
            "active_packages": active_count,
            "delivered_packages": delivered_count,
            "packages": packages,
        }
