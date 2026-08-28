"""KakaoMap API client for Home Assistant integration."""

from typing import Dict, Any, Optional

import aiohttp
from yarl import URL

from .exceptions import KakaoMapConnectionError, KakaoMapDataError
from ..const import LOGGER


class KakaoMapApiClient:
    """API client for KakaoMap integration."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        api_key: str | None = None,
        web_cookie: str | None = None,
    ):
        self._session = session
        self._base_url = "https://map.kakao.com"
        self._routing_url = "https://dapi.kakao.com/v2/routing/publictraffic"
        self._web_routing_url = f"{self._base_url}/route/pubtrans.json"
        self._gate_token_url = (
            f"{self._base_url}/api/v1/settings/web/gate-token"
        )
        self._api_key = api_key
        self._web_cookie = web_cookie

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

        except (KakaoMapConnectionError, KakaoMapDataError):
            raise
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
        start_name: str = "출발",
        end_name: str = "도착",
        start_id: str = "",
        end_id: str = "",
    ) -> Dict[str, Any]:
        """Get public transport route information."""
        if self._web_cookie:
            return await self._async_get_web_transport_route(
                start_x,
                start_y,
                end_x,
                end_y,
                coord_system,
                start_name,
                end_name,
                start_id,
                end_id,
            )
        if not self._api_key:
            raise KakaoMapConnectionError(
                "A Kakao REST API key or KakaoMap web cookie is required"
            )

        params = {
            "input_coord": coord_system,
            "output_coord": coord_system,
            "start_x": str(start_x),
            "start_y": str(start_y),
            "end_x": str(end_x),
            "end_y": str(end_y),
        }

        headers = {
            "Accept": "application/json",
            "Authorization": f"KakaoAK {self._api_key}",
            "User-Agent": "HomeAssistant-Korea-Components/1.0",
        }

        LOGGER.debug(f"Requesting KakaoMap transport API with params: {params}")

        try:
            async with self._session.get(
                self._routing_url, params=params, headers=headers
            ) as response:
                LOGGER.debug(
                    f"KakaoMap transport API response status: {response.status}"
                )

                if response.status != 200:
                    raise KakaoMapConnectionError(
                        f"HTTP {response.status}: {response.reason}"
                    )

                data = await response.json()
                # Keep compatibility with recorded responses from the retired API.
                if "in_local" in data:
                    return data
                if data.get("status") != "OK":
                    raise KakaoMapDataError(
                        f"Route search failed: {data.get('status', 'unknown')}"
                    )
                return self._normalize_route_response(data)

        except (KakaoMapConnectionError, KakaoMapDataError):
            raise
        except aiohttp.ClientError as e:
            LOGGER.error(f"KakaoMap transport API request failed: {e}")
            raise KakaoMapConnectionError(f"Request failed: {e}")
        except Exception as e:
            LOGGER.error(f"Unexpected error in KakaoMap transport API request: {e}")
            raise KakaoMapDataError(f"Unexpected error: {e}")

    async def _async_get_web_transport_route(
        self,
        start_x: float,
        start_y: float,
        end_x: float,
        end_y: float,
        coord_system: str,
        start_name: str,
        end_name: str,
        start_id: str,
        end_id: str,
    ) -> Dict[str, Any]:
        """Request the KakaoMap web route API with a fresh gate token."""
        params = {
            "sName": start_name,
            "eName": end_name,
            "sX": str(int(start_x)),
            "sY": str(int(start_y)),
            "eX": str(int(end_x)),
            "eY": str(int(end_y)),
            "sid": start_id,
            "eid": end_id,
            "inputCoordSystem": coord_system,
            "outputCoordSystem": coord_system,
            "service": "map.daum.net",
        }
        route_url = URL(self._web_routing_url).with_query(params)
        common_headers = {
            "Accept": "application/json",
            "Cookie": self._web_cookie,
            "Referer": f"{self._base_url}/",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36",
        }

        try:
            async with self._session.post(
                self._gate_token_url,
                json={"method": "GET", "url": str(route_url), "body": ""},
                headers=common_headers,
            ) as response:
                if response.status != 200:
                    raise KakaoMapConnectionError(
                        f"Gate token HTTP {response.status}: {response.reason}"
                    )
                gate_token = (await response.json()).get("token")

            if not gate_token:
                raise KakaoMapDataError("KakaoMap gate token was not returned")

            headers = {
                **common_headers,
                "x-kmap-captcha-token": gate_token,
            }
            async with self._session.get(
                route_url, headers=headers, allow_redirects=False
            ) as response:
                if response.status != 200:
                    raise KakaoMapConnectionError(
                        f"KakaoMap web route HTTP {response.status}: "
                        "refresh the KakaoMap web cookie"
                    )
                content_type = response.headers.get("Content-Type", "")
                if "json" not in content_type.lower():
                    raise KakaoMapDataError(
                        f"Unexpected KakaoMap content type: {content_type}"
                    )
                return await response.json()
        except (KakaoMapConnectionError, KakaoMapDataError):
            raise
        except aiohttp.ClientError as e:
            raise KakaoMapConnectionError(f"Request failed: {e}") from e

    @staticmethod
    def _normalize_route_response(data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert the official routing response to the integration's data shape."""
        routes = []
        for index, route in enumerate(data.get("routes", [])):
            properties = route.get("properties", {})
            steps = route.get("steps", [])
            walking_steps = [
                step
                for step in steps
                if not step.get("properties", {}).get("vehicles")
            ]
            routes.append(
                {
                    "time": {"value": properties.get("totalTime")},
                    "fare": properties.get("fare", {}),
                    "distance": {"value": properties.get("totalDistance")},
                    "type": properties.get("type", ""),
                    "transfers": properties.get("transfers", 0),
                    "walkingDistance": {
                        "value": sum(
                            step.get("properties", {}).get("distance", 0)
                            for step in walking_steps
                        )
                    },
                    "walkingTime": {
                        "value": sum(
                            step.get("properties", {}).get("time", 0)
                            for step in walking_steps
                        )
                    },
                    "recommended": index == 0,
                    "shortestTime": False,
                    "leastTransfer": False,
                    "steps": steps,
                }
            )
        return {"in_local": {"routes": routes}}

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
