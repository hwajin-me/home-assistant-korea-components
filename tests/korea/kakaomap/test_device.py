"""Test KakaoMap device with both mock and real scenarios."""

import pytest
import aiohttp
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

from custom_components.korea_incubator.kakaomap.device import KakaoMapDevice
from custom_components.korea_incubator.kakaomap.exceptions import (
    KakaoMapConnectionError,
    KakaoMapDataError,
)
from homeassistant.helpers.update_coordinator import UpdateFailed


class TestKakaoMapDeviceMock:
    """Test KakaoMap device with mocked dependencies."""

    @pytest.fixture
    def mock_api_client(self):
        """Create mock API client."""
        return AsyncMock()

    @pytest.fixture
    async def kakaomap_device(self, mock_hass, mock_session, mock_api_client):
        """Create KakaoMap device with mocked dependencies."""
        session = aiohttp.ClientSession()
        device = KakaoMapDevice(
            mock_hass,
            "test_entry_id",
            "집↔회사",
            {"x": 515290, "y": 1122478},
            {"x": 506190, "y": 1110730},
            session,
        )
        device.api_client = mock_api_client
        yield device
        await device.async_close_session()

    def test_device_properties(self, kakaomap_device):
        """Test device basic properties."""
        assert kakaomap_device.unique_id == "kakaomap_test_entry_id"
        assert kakaomap_device._name == "카카오맵 (집↔회사)"
        assert kakaomap_device.available is True

        device_info = kakaomap_device.device_info
        assert device_info["name"] == "카카오맵 (집↔회사)"
        assert device_info["manufacturer"] == "Kakao"
        assert device_info["model"] == "카카오맵"

    @pytest.mark.asyncio
    async def test_async_update_success(
        self,
        kakaomap_device,
        mock_api_client,
        kakaomap_mock_address_response,
        kakaomap_mock_route_response,
    ):
        """Test successful data update."""
        mock_api_client.async_coordinate_to_address.return_value = (
            kakaomap_mock_address_response
        )
        mock_api_client.async_get_public_transport_route.return_value = (
            kakaomap_mock_route_response
        )

        await kakaomap_device.async_update()

        assert kakaomap_device.data["start_address"] == kakaomap_mock_address_response
        assert kakaomap_device.data["end_address"] == kakaomap_mock_address_response
        assert "transport_route" in kakaomap_device.data
        assert kakaomap_device.available is True

    @pytest.mark.asyncio
    async def test_async_update_connection_error(
        self, kakaomap_device, mock_api_client
    ):
        """Test update with connection error."""
        mock_api_client.async_coordinate_to_address.side_effect = (
            KakaoMapConnectionError("Connection failed")
        )

        with pytest.raises(UpdateFailed, match="Error communicating with KakaoMap API"):
            await kakaomap_device.async_update()

        assert kakaomap_device.available is False

    @pytest.mark.asyncio
    async def test_async_update_data_error(self, kakaomap_device, mock_api_client):
        """Test update with data error."""
        mock_api_client.async_coordinate_to_address.side_effect = KakaoMapDataError(
            "Data parsing failed"
        )

        with pytest.raises(UpdateFailed, match="Error communicating with KakaoMap API"):
            await kakaomap_device.async_update()

        assert kakaomap_device.available is False

    def test_parse_transport_route_success(
        self, kakaomap_device, kakaomap_mock_route_response
    ):
        """Test transport route parsing."""
        result = kakaomap_device._parse_transport_route(kakaomap_mock_route_response)

        assert "summary" in result
        assert "routes" in result
        assert "real_time_info" in result
        assert len(result["routes"]) > 0

        # Test first route structure
        first_route = result["routes"][0]
        assert "time" in first_route
        assert "fare" in first_route
        assert "type" in first_route

    def test_parse_transport_route_empty_data(self, kakaomap_device):
        """Test transport route parsing with empty data."""
        result = kakaomap_device._parse_transport_route({})

        assert result["summary"] == {}
        assert result["routes"] == []
        assert result["real_time_info"] == {}

    def test_extract_minutes_from_time(self, kakaomap_device):
        """Test time extraction from various formats."""
        # Test seconds to minutes conversion
        assert kakaomap_device._extract_minutes_from_time({"value": 1680}) == 28
        assert kakaomap_device._extract_minutes_from_time(3600) == 60
        assert kakaomap_device._extract_minutes_from_time({}) is None

    def test_extract_fare_value(self, kakaomap_device):
        """Test fare value extraction."""
        assert kakaomap_device._extract_fare_value({"value": 1370}) == 1370
        assert kakaomap_device._extract_fare_value(1500) == 1500
        assert kakaomap_device._extract_fare_value({}) is None

    def test_extract_distance_km(self, kakaomap_device):
        """Test distance extraction in kilometers."""
        assert kakaomap_device._extract_distance_km({"value": 15000}) == 15.0
        assert kakaomap_device._extract_distance_km(20000) == 20.0
        assert kakaomap_device._extract_distance_km({}) is None

    @pytest.mark.asyncio
    async def test_async_get_address_from_coordinates(
        self, kakaomap_device, mock_api_client
    ):
        """Test address retrieval from coordinates."""
        mock_api_client.async_coordinate_to_address.return_value = {
            "success": True,
            "address": "서울시 강남구 테헤란로",
        }

        result = await kakaomap_device.async_get_address_from_coordinates(127.0, 37.5)
        assert result == "서울시 강남구 테헤란로"

    @pytest.mark.asyncio
    async def test_async_get_route_between_coordinates(
        self, kakaomap_device, mock_api_client, kakaomap_mock_route_response
    ):
        """Test route retrieval between coordinates."""
        mock_api_client.async_get_public_transport_route.return_value = (
            kakaomap_mock_route_response
        )

        result = await kakaomap_device.async_get_route_between_coordinates(
            515290, 1122478, 506190, 1110730
        )
        assert result == kakaomap_mock_route_response

    def test_device_coordinates_storage(self, mock_hass, mock_session):
        """Test device coordinate storage."""
        start_coords = {"x": 515290, "y": 1122478}
        end_coords = {"x": 506190, "y": 1110730}

        device = KakaoMapDevice(
            mock_hass,
            "test_entry",
            "테스트경로",
            start_coords,
            end_coords,
            mock_session,
        )

        assert device.start_coords == start_coords
        assert device.end_coords == end_coords
        assert device.name == "테스트경로"


class TestKakaoMapDeviceIntegration:
    """Integration tests for KakaoMap device."""

    @pytest.fixture
    async def real_session(self):
        """Create real session for integration tests."""
        session = aiohttp.ClientSession()
        yield session
        await session.close()

    @pytest.fixture
    def real_kakaomap_device(self, mock_hass, real_session):
        """Create KakaoMap device with real session."""
        return KakaoMapDevice(
            mock_hass,
            "test_entry_id",
            "집↔회사",
            {"x": 515290, "y": 1122478},
            {"x": 506190, "y": 1110730},
            real_session,
        )

    @pytest.mark.integration
    @pytest.mark.skipif(
        not pytest.config.getoption("--integration", default=False),
        reason="Integration tests disabled",
    )
    async def test_real_device_update(self, real_kakaomap_device):
        """Test real device update."""
        try:
            await real_kakaomap_device.async_update()

            # Should have valid data structure
            assert "start_address" in real_kakaomap_device.data
            assert "end_address" in real_kakaomap_device.data
            assert "transport_route" in real_kakaomap_device.data

        except UpdateFailed as e:
            # May fail due to API limitations or network issues
            pytest.skip(f"Real API test failed (expected): {e}")

    @pytest.mark.parametrize(
        "name,start_x,start_y,end_x,end_y",
        [
            ("집↔회사", 515290, 1122478, 506190, 1110730),
            ("학교↔도서관", 127.0, 37.5, 127.1, 37.6),
            ("테스트", 0, 0, 1, 1),  # Edge case
        ],
    )
    def test_device_creation_various_coords(
        self, mock_hass, mock_session, name, start_x, start_y, end_x, end_y
    ):
        """Test device creation with various coordinates."""
        start_coords = {"x": start_x, "y": start_y}
        end_coords = {"x": end_x, "y": end_y}

        device = KakaoMapDevice(
            mock_hass, "test_entry", name, start_coords, end_coords, mock_session
        )

        assert device.name == name
        assert device.start_coords == start_coords
        assert device.end_coords == end_coords
        assert name in device._name
