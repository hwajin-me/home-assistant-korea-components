"""KakaoMap device for Home Assistant integration."""
from __future__ import annotations

from datetime import datetime
from typing import Dict, Any, Optional
import aiohttp
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.core import HomeAssistant

from .api import KakaoMapApiClient
from .exceptions import KakaoMapConnectionError, KakaoMapDataError
from ..const import DOMAIN, LOGGER


class KakaoMapDevice:
    """KakaoMap device representation with type safety."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        name: str,
        start_coords: Dict[str, float],
        end_coords: Dict[str, float],
        session: aiohttp.ClientSession
    ) -> None:
        """Initialize KakaoMap device."""
        self.hass: HomeAssistant = hass
        self.entry_id: str = entry_id
        self.name: str = name
        self.start_coords: Dict[str, float] = start_coords  # {"x": float, "y": float}
        self.end_coords: Dict[str, float] = end_coords  # {"x": float, "y": float}
        self.session: aiohttp.ClientSession = session
        self.api_client: KakaoMapApiClient = KakaoMapApiClient(self.session)

        self._name: str = f"카카오맵 ({name})"
        self._unique_id: str = f"kakaomap_{entry_id}"
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
            manufacturer="Kakao",
            model="카카오맵",
            configuration_url="https://map.kakao.com",
        )

    @property
    def available(self) -> bool:
        """Return if device is available."""
        return self._available

    async def async_update(self) -> None:
        """Fetch data from KakaoMap API."""
        try:
            # Get address information for start and end coordinates
            start_address: Dict[str, Any] = await self.api_client.async_coordinate_to_address(
                self.start_coords["x"],
                self.start_coords["y"]
            )

            end_address: Dict[str, Any] = await self.api_client.async_coordinate_to_address(
                self.end_coords["x"],
                self.end_coords["y"]
            )

            # Get public transport route
            transport_route: Dict[str, Any] = await self.api_client.async_get_public_transport_route(
                self.start_coords["x"],
                self.start_coords["y"],
                self.end_coords["x"],
                self.end_coords["y"]
            )

            self.data = {
                "start_address": start_address,
                "end_address": end_address,
                "transport_route": transport_route,
                "last_updated": datetime.now().isoformat(),
            }

            self._available = True
            self._last_update_success = datetime.now()
            LOGGER.debug(f"KakaoMap data updated successfully for {self.name}")

        except (KakaoMapConnectionError, KakaoMapDataError) as err:
            self._available = False
            LOGGER.error(f"Error updating KakaoMap data for {self.name}: {err}")
            raise UpdateFailed(f"Error communicating with KakaoMap API: {err}")

        except Exception as err:
            self._available = False
            LOGGER.error(f"Unexpected error updating KakaoMap data for {self.name}: {err}")
            raise UpdateFailed(f"Unexpected error: {err}")

    def get_start_address(self) -> Optional[str]:
        """Get start location address."""
        if not self.data.get("start_address"):
            return None
        return self.data["start_address"].get("address")

    def get_end_address(self) -> Optional[str]:
        """Get end location address."""
        if not self.data.get("end_address"):
            return None
        return self.data["end_address"].get("address")

    def get_recommended_route_time(self) -> Optional[str]:
        """Get recommended route travel time."""
        if not self.data.get("transport_route"):
            return None

        recommended = self.data["transport_route"]["summary"].get("recommended_route")
        if recommended:
            return recommended.get("time")

        # Fall back to first route
        routes = self.data["transport_route"].get("routes", [])
        if routes:
            return routes[0].get("time")

        return None

    def get_recommended_route_fare(self) -> Optional[str]:
        """Get recommended route fare."""
        if not self.data.get("transport_route"):
            return None

        recommended = self.data["transport_route"]["summary"].get("recommended_route")
        if recommended:
            return recommended.get("fare")

        # Fall back to first route
        routes = self.data["transport_route"].get("routes", [])
        if routes:
            return routes[0].get("fare")

        return None

    def get_route_summary(self) -> str:
        """Get route summary."""
        if not self.data.get("transport_route"):
            return "경로 정보 없음"

        return self.api_client.get_route_summary(self.data["transport_route"])

    def get_total_routes(self) -> int:
        """Get total number of available routes."""
        if not self.data.get("transport_route"):
            return 0
        return self.data["transport_route"]["summary"].get("total_routes", 0)

    async def async_get_address_from_coordinates(self, x: float, y: float) -> Optional[str]:
        """Get address from coordinates (can be called externally)."""
        try:
            address_data: Dict[str, Any] = await self.api_client.async_coordinate_to_address(x, y)
            return address_data.get("address")
        except Exception as e:
            LOGGER.error(f"Error getting address from coordinates: {e}")
            return None

    async def async_get_route_between_coordinates(
        self,
        start_x: float,
        start_y: float,
        end_x: float,
        end_y: float
    ) -> Optional[Dict[str, Any]]:
        """Get route between coordinates (can be called externally)."""
        try:
            route_data: Dict[str, Any] = await self.api_client.async_get_public_transport_route(
                start_x, start_y, end_x, end_y
            )
            return route_data
        except Exception as e:
            LOGGER.error(f"Error getting route between coordinates: {e}")
            return None

    async def async_close_session(self) -> None:
        """Close the aiohttp session."""
        if self.session:
            await self.session.close()
            self.session = None
