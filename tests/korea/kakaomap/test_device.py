import pytest
import aiohttp
from unittest.mock import AsyncMock, MagicMock
from custom_components.korea_incubator.kakaomap.device import KakaoMapDevice
from custom_components.korea_incubator.kakaomap.exceptions import KakaoMapConnectionError
from homeassistant.helpers.update_coordinator import UpdateFailed


@pytest.fixture
def mock_hass():
    return MagicMock()


@pytest.fixture
async def kakaomap_device(mock_hass):
    session = aiohttp.ClientSession()
    start_coords = {"x": 515290, "y": 1122478}
    end_coords = {"x": 506190, "y": 1110730}
    device = KakaoMapDevice(mock_hass, "test_entry", "집↔회사", start_coords, end_coords, session)
    yield device
    await device.async_close_session()


@pytest.mark.asyncio
async def test_device_initialization(kakaomap_device):
    assert kakaomap_device.unique_id == "kakaomap_test_entry"
    assert kakaomap_device._name == "카카오맵 (집↔회사)"
    assert kakaomap_device.available is True


@pytest.mark.asyncio
async def test_async_update_success(kakaomap_device):
    # Mock API responses
    mock_start_address = {
        "success": True,
        "address": "서울특별시 광진구 능동 18"
    }

    mock_end_address = {
        "success": True,
        "address": "서울특별시 강남구 역삼동 737"
    }

    mock_transport_route = {
        "in_local": {
            "routes": [
                {
                    "time": {"value": 1680},
                    "fare": {"value": 1550},
                    "distance": {"value": 12500},
                    "type": "지하철+도보",
                    "transfers": 0,
                    "walkingDistance": {"value": 800},
                    "walkingTime": {"value": 600},
                    "recommended": True,
                    "steps": [
                        {"information": "출발", "action": "DEPARTURE"},
                        {"information": "건대입구역 승차", "type": "SUBWAY"},
                        {"information": "강남역 하차", "type": "SUBWAY"},
                        {"information": "도착", "action": "ARRIVAL"}
                    ]
                }
            ]
        }
    }

    kakaomap_device.api_client.async_coordinate_to_address = AsyncMock(
        side_effect=[mock_start_address, mock_end_address]
    )
    kakaomap_device.api_client.async_get_public_transport_route = AsyncMock(
        return_value=mock_transport_route
    )

    await kakaomap_device.async_update()

    assert kakaomap_device.available is True
    assert kakaomap_device.data["start_address"]["address"] == "서울특별시 광진구 능동 18"
    assert kakaomap_device.data["end_address"]["address"] == "서울특별시 강남구 역삼동 737"
    assert len(kakaomap_device.data["transport_route"]["routes"]) == 1


@pytest.mark.asyncio
async def test_async_update_connection_error(kakaomap_device):
    # Mock connection error
    kakaomap_device.api_client.async_coordinate_to_address = AsyncMock(
        side_effect=KakaoMapConnectionError("Connection failed")
    )

    with pytest.raises(UpdateFailed):
        await kakaomap_device.async_update()

    assert kakaomap_device.available is False


@pytest.mark.asyncio
async def test_device_info(kakaomap_device):
    device_info = kakaomap_device.device_info
    assert device_info["name"] == "카카오맵 (집↔회사)"
    assert device_info["manufacturer"] == "Kakao"
    assert device_info["model"] == "카카오맵"


@pytest.mark.asyncio
async def test_parse_transport_route_success(kakaomap_device):
    raw_data = {
        "in_local": {
            "routes": [
                {
                    "time": {"value": 1680},
                    "fare": {"value": 1550},
                    "distance": {"value": 12500},
                    "type": "지하철+도보",
                    "transfers": 0,
                    "walkingDistance": {"value": 800},
                    "walkingTime": {"value": 600},
                    "recommended": True,
                    "steps": [
                        {"information": "출발", "action": "DEPARTURE"},
                        {"information": "건대입구역 승차", "type": "SUBWAY"},
                        {"information": "강남역 하차", "type": "SUBWAY"},
                        {"information": "도착", "action": "ARRIVAL"}
                    ]
                }
            ]
        }
    }

    result = kakaomap_device._parse_transport_route(raw_data)

    assert len(result["routes"]) == 1
    assert result["routes"][0]["time"] == 28  # 1680 seconds -> 28 minutes
    assert result["routes"][0]["fare"] == 1550
    assert result["routes"][0]["distance"] == 12.5  # 12500 meters -> 12.5 km
    assert len(result["routes"][0]["steps"]) == 4
    assert result["summary"]["recommended_route"]["time"] == 28


@pytest.mark.asyncio
async def test_parse_transport_route_no_data(kakaomap_device):
    result = kakaomap_device._parse_transport_route({})

    assert result["summary"] == {}
    assert result["routes"] == []
    assert result["real_time_info"] == {}


@pytest.mark.asyncio
async def test_extract_minutes_from_time(kakaomap_device):
    assert kakaomap_device._extract_minutes_from_time({"value": 1680}) == 28
    assert kakaomap_device._extract_minutes_from_time(120) == 2
    assert kakaomap_device._extract_minutes_from_time({}) is None


@pytest.mark.asyncio
async def test_extract_fare_value(kakaomap_device):
    assert kakaomap_device._extract_fare_value({"value": 1550}) == 1550
    assert kakaomap_device._extract_fare_value(1550) == 1550
    assert kakaomap_device._extract_fare_value({}) is None


@pytest.mark.asyncio
async def test_extract_distance_km(kakaomap_device):
    assert kakaomap_device._extract_distance_km({"value": 12500}) == 12.5
    assert kakaomap_device._extract_distance_km(1000) == 1.0
    assert kakaomap_device._extract_distance_km({}) is None
