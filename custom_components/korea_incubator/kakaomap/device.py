"""KakaoMap device for Home Assistant integration."""

from datetime import datetime
from typing import Dict, Any, Optional

import aiohttp
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import UpdateFailed

from .api import KakaoMapApiClient
from .exceptions import KakaoMapConnectionError, KakaoMapDataError
from ..const import DOMAIN, LOGGER


class KakaoMapDevice:
    """KakaoMap device representation."""

    def __init__(
        self,
        hass,
        entry_id: str,
        name: str,
        start_coords: Dict[str, float],
        end_coords: Dict[str, float],
        session: aiohttp.ClientSession,
    ):
        self.hass = hass
        self.entry_id = entry_id
        self.name = name
        self.start_coords = start_coords  # {"x": float, "y": float}
        self.end_coords = end_coords  # {"x": float, "y": float}
        self.session = session
        self.api_client = KakaoMapApiClient(self.session)

        self._name = f"카카오맵 ({name})"
        self._unique_id = f"kakaomap_{entry_id}"
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
            manufacturer="Kakao",
            model="카카오맵",
            configuration_url="https://map.kakao.com",
        )

    @property
    def available(self) -> bool:
        return self._available

    async def async_update(self):
        """Fetch data from KakaoMap API."""
        try:
            # Get address information for start and end coordinates
            start_address = await self.api_client.async_coordinate_to_address(
                self.start_coords["x"], self.start_coords["y"]
            )

            end_address = await self.api_client.async_coordinate_to_address(
                self.end_coords["x"], self.end_coords["y"]
            )

            # Get public transport route
            transport_route_raw = (
                await self.api_client.async_get_public_transport_route(
                    self.start_coords["x"],
                    self.start_coords["y"],
                    self.end_coords["x"],
                    self.end_coords["y"],
                )
            )

            # Parse and enhance the transport route data
            transport_route = self._parse_transport_route(transport_route_raw)
            LOGGER.debug(f"KakaoMap data fetched for {self.name}: {transport_route}")

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
            LOGGER.error(
                f"Unexpected error updating KakaoMap data for {self.name}: {err}"
            )
            raise UpdateFailed(f"Unexpected error: {err}")

    def _parse_transport_route(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse and enhance transport route data for sensor consumption."""
        if not raw_data or "in_local" not in raw_data:
            LOGGER.debug(f"[KakaoMap] No valid route data found for {raw_data}")
            return {"summary": {}, "routes": [], "real_time_info": {}}

        in_local = raw_data["in_local"]
        routes = in_local.get("routes", [])

        # Create enhanced route data based on actual API structure
        enhanced_routes = []
        for route in routes:
            enhanced_route = {
                "time": self._extract_minutes_from_time(route.get("time", {})),
                "fare": self._extract_fare_value(route.get("fare", {})),
                "distance": self._extract_distance_km(route.get("distance", {})),
                "type": route.get("type", ""),
                "transfers": route.get("transfers", 0),
                "walking_distance": self._extract_distance_m(
                    route.get("walkingDistance", {})
                ),
                "walking_time": self._extract_minutes_from_time(
                    route.get("walkingTime", {})
                ),
                "recommended": route.get("recommended", False),
                "shortest_time": route.get("shortestTime", False),
                "least_transfer": route.get("leastTransfer", False),
                "first_departure_info": self._get_first_departure_info(route),
                "next_departure_info": self._get_next_departure_info(route),
                "climate_card": route.get("climateCard", False),
                # Add original steps data for sensor access
                "steps": route.get("steps", []),
            }
            enhanced_routes.append(enhanced_route)

        # Find special routes
        recommended_route = next((r for r in enhanced_routes if r["recommended"]), None)
        fastest_route = next((r for r in enhanced_routes if r["shortest_time"]), None)
        least_transfer_route = next(
            (r for r in enhanced_routes if r["least_transfer"]), None
        )

        # If no explicitly marked routes, use the first ones and analyze
        if not recommended_route and enhanced_routes:
            recommended_route = enhanced_routes[0]  # First route is usually recommended
        if not fastest_route and enhanced_routes:
            # Find route with minimum time
            fastest_route = min(
                enhanced_routes, key=lambda x: x["time"] if x["time"] else 999
            )
        if not least_transfer_route and enhanced_routes:
            # Find route with minimum transfers
            least_transfer_route = min(enhanced_routes, key=lambda x: x["transfers"])

        # Calculate statistics
        total_routes = len(enhanced_routes)
        times = [r["time"] for r in enhanced_routes if r["time"] is not None]
        fares = [r["fare"] for r in enhanced_routes if r["fare"] is not None]

        average_time = sum(times) / len(times) if times else 0
        average_fare = sum(fares) / len(fares) if fares else 0

        # Create route summary
        route_summary = self._create_route_summary(enhanced_routes)

        # Extract real-time info
        real_time_info = self._extract_real_time_info(routes)

        return {
            "summary": {
                "recommended_route": recommended_route,
                "fastest_route": fastest_route,
                "least_transfer_route": least_transfer_route,
                "total_routes": total_routes,
                "average_time": round(average_time) if average_time > 0 else None,
                "average_fare": round(average_fare) if average_fare > 0 else None,
                "route_summary": route_summary,
            },
            "routes": enhanced_routes,
            "real_time_info": real_time_info,
            "last_updated": datetime.now().isoformat(),
        }

    def _extract_minutes_from_time(self, time_data: Dict[str, Any]) -> Optional[int]:
        """Extract minutes from time data."""
        if isinstance(time_data, dict):
            value = time_data.get("value")
            if value:
                return round(value / 60)  # Convert seconds to minutes
        elif isinstance(time_data, (int, float)):
            return round(time_data / 60)
        return None

    def _extract_fare_value(self, fare_data: Dict[str, Any]) -> Optional[int]:
        """Extract fare value from fare data."""
        if isinstance(fare_data, dict):
            return fare_data.get("value")
        elif isinstance(fare_data, (int, float)):
            return int(fare_data)
        return None

    def _extract_distance_km(self, distance_data: Dict[str, Any]) -> Optional[float]:
        """Extract distance in kilometers."""
        if isinstance(distance_data, dict):
            value = distance_data.get("value")
            if value:
                return round(value / 1000, 1)  # Convert meters to kilometers
        elif isinstance(distance_data, (int, float)):
            return round(distance_data / 1000, 1)
        return None

    def _extract_distance_m(self, distance_data: Dict[str, Any]) -> Optional[int]:
        """Extract distance in meters."""
        if isinstance(distance_data, dict):
            return distance_data.get("value")
        elif isinstance(distance_data, (int, float)):
            return int(distance_data)
        return None

    def _get_first_departure_info(self, route: Dict[str, Any]) -> Optional[str]:
        """Get first departure information from route."""
        summaries = route.get("summaries", [])
        if summaries:
            for summary in summaries:
                vehicles = summary.get("vehicles", [])
                if vehicles:
                    vehicle = vehicles[0]
                    return f"{vehicle.get('name', '')} ({summary.get('startLocation', {}).get('name', '')})"
        return None

    def _get_next_departure_info(self, route: Dict[str, Any]) -> Optional[str]:
        """Get next departure information from route."""
        summaries = route.get("summaries", [])
        if summaries:
            for summary in summaries:
                arrivals = summary.get("subwayArrivals", []) or summary.get(
                    "busArrivals", []
                )
                if arrivals and len(arrivals) > 0:
                    next_arrival = arrivals[0]
                    arrival_msg = next_arrival.get("arrivalMsg", "")
                    return arrival_msg
        return None

    def _create_route_summary(self, routes) -> str:
        """Create a summary of all available routes."""
        if not routes:
            return "경로 정보 없음"

        route_types = set()
        min_time = min(r["time"] for r in routes if r["time"])
        max_time = max(r["time"] for r in routes if r["time"])
        min_fare = min(r["fare"] for r in routes if r["fare"])
        max_fare = max(r["fare"] for r in routes if r["fare"])

        for route in routes:
            route_types.add(route["type"])

        summary = f"{len(routes)}개 경로 ("
        summary += ", ".join(route_types)
        summary += f") | 소요시간: {min_time}~{max_time}분"
        if min_fare and max_fare:
            summary += f" | 요금: {min_fare:,}~{max_fare:,}원"

        return summary

    def _extract_real_time_info(self, routes) -> Dict[str, Any]:
        """Extract real-time transportation information."""
        subway_delays = []
        bus_arrivals = []

        for route in routes:
            summaries = route.get("summaries", [])
            for summary in summaries:
                # Extract subway arrival info
                subway_arrivals = summary.get("subwayArrivals", [])
                for arrival in subway_arrivals:
                    if arrival.get("vehicleArrivalState") in [
                        "RUNNING",
                        "PREV_STN_DEPARTURE",
                    ]:
                        arrival_time = arrival.get("arrivalTime", 0)
                        if arrival_time > 0:
                            subway_delays.append(
                                f"{arrival.get('direction', '')}: {arrival.get('arrivalMsg', '')}"
                            )

                # Extract bus arrival info
                bus_arrivals_data = summary.get("busArrivals", [])
                for arrival in bus_arrivals_data:
                    arrival_time = arrival.get("arrivalTime", 0)
                    if arrival_time > 0:
                        bus_arrivals.append(arrival_time // 60)  # Convert to minutes

        return {
            "subway_delay": "; ".join(subway_delays[:3])
            if subway_delays
            else None,  # Limit to first 3
            "bus_arrival_time": min(bus_arrivals) if bus_arrivals else None,
        }

    async def async_get_address_from_coordinates(
        self, x: float, y: float
    ) -> Optional[str]:
        """Get address from coordinates (can be called externally)."""
        try:
            address_data = await self.api_client.async_coordinate_to_address(x, y)
            return address_data.get("address")
        except Exception as e:
            LOGGER.error(f"Error getting address from coordinates: {e}")
            return None

    async def async_get_route_between_coordinates(
        self, start_x: float, start_y: float, end_x: float, end_y: float
    ) -> Optional[Dict[str, Any]]:
        """Get route between coordinates (can be called externally)."""
        try:
            route_data = await self.api_client.async_get_public_transport_route(
                start_x, start_y, end_x, end_y
            )
            return route_data
        except Exception as e:
            LOGGER.error(f"Error getting route between coordinates: {e}")
            return None

    async def async_close_session(self):
        """Close the aiohttp session."""
        if self.session:
            await self.session.close()
            self.session = None
