"""KakaoMap API client for Home Assistant integration."""

from datetime import datetime
from typing import Dict, Any, Optional

import aiohttp

from .exceptions import KakaoMapConnectionError, KakaoMapDataError
from ..const import LOGGER


class KakaoMapApiClient:
    """API client for KakaoMap integration."""

    def __init__(self, session: aiohttp.ClientSession):
        self._session = session
        self._base_url = "https://map.kakao.com"

    async def async_coordinate_to_address(
        self, x: float, y: float, coord_system: str = "WCONGNAMUL"
    ) -> Dict[str, Any]:
        """Convert coordinates to address information."""
        url = f"{self._base_url}/etc/areaAddressInfo.json"

        params = {
            "output": "JSON",
            "inputCoordSystem": coord_system,
            "outputCoordSystem": coord_system,
            "x": str(x),
            "y": str(y),
        }

        headers = {
            "Accept": "application/json",
            "User-Agent": "HomeAssistant-Korea-Components/1.0",
        }

        try:
            async with self._session.get(
                url, params=params, headers=headers
            ) as response:
                LOGGER.debug(
                    f"KakaoMap coordinate API response status: {response.status}"
                )

                if response.status != 200:
                    raise KakaoMapConnectionError(
                        f"HTTP {response.status}: {response.reason}"
                    )

                data = await response.json()
                return self._parse_address_response(data)

        except aiohttp.ClientError as e:
            LOGGER.error(f"KakaoMap coordinate API request failed: {e}")
            raise KakaoMapConnectionError(f"Request failed: {e}")
        except Exception as e:
            LOGGER.error(f"Unexpected error in KakaoMap coordinate API request: {e}")
            raise KakaoMapDataError(f"Unexpected error: {e}")

    async def async_get_public_transport_route(
        self,
        start_x: float,
        start_y: float,
        end_x: float,
        end_y: float,
        coord_system: str = "WCONGNAMUL",
        start_time: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get public transport route information."""
        url = f"{self._base_url}/route/pubtrans.json"

        params = {
            "inputCoordSystem": coord_system,
            "outputCoordSystem": coord_system,
            "sX": int(start_x),
            "sY": int(start_y),
            "eX": int(end_x),
            "eY": int(end_y),
        }

        if start_time:
            params["startAt"] = start_time
        else:
            params["startAt"] = datetime.now().strftime("%Y%m%d%H%M") + "0"

        headers = {
            "Accept": "text/javascript, application/javascript, application/ecmascript, application/x-ecmascript, */*; q=0.01",
            "Accept-Language": "en-US,en;q=0.9,ko;q=0.8,ja;q=0.7",
            "X-Requested-With": "XMLHttpRequest",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
        }

        LOGGER.debug(f"Requesting KakaoMap transport API with params: {params}")

        try:
            async with self._session.get(
                url, params=params, headers=headers
            ) as response:
                LOGGER.debug(
                    f"KakaoMap transport API response status: {response.status}"
                )

                if response.status != 200:
                    raise KakaoMapConnectionError(
                        f"HTTP {response.status}: {response.reason}"
                    )

                data = await response.json()
                return data

        except aiohttp.ClientError as e:
            LOGGER.error(f"KakaoMap transport API request failed: {e}")
            raise KakaoMapConnectionError(f"Request failed: {e}")
        except Exception as e:
            LOGGER.error(f"Unexpected error in KakaoMap transport API request: {e}")
            raise KakaoMapDataError(f"Unexpected error: {e}")

    def _parse_address_response(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse address response data."""
        try:
            result = {
                "success": True,
                "address": None,
                "region": None,
                "coordinates": None,
            }

            if "old" in data and data["old"]:
                old_data = data["old"]
                result["address"] = old_data.get("name", "")
                result["region"] = data.get("region", "")
                result["coordinates"] = {"x": data.get("x"), "y": data.get("y")}

            return result

        except Exception as e:
            LOGGER.error(f"Error parsing address response: {e}")
            raise KakaoMapDataError(f"Address parsing failed: {e}")

    def get_route_summary(self, transport_data: Dict[str, Any]) -> str:
        """Get a summary string of the transport routes."""
        if not transport_data.get("success") or not transport_data.get("routes"):
            return "경로 정보 없음"
        recommended = transport_data["summary"].get("recommended_route")
        if recommended:
            return f"{recommended['time']} ({recommended['fare']}, 환승 {recommended['transfers']}회)"

        # Fall back to first route
        first_route = transport_data["routes"][0]
        return f"{first_route['time']} ({first_route['fare']}, 환승 {first_route['transfers']}회)"
