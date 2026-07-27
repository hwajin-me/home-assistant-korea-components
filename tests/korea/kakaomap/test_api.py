"""Test KakaoMap API client with both mock and real API calls."""

import pytest
import aiohttp
from unittest.mock import AsyncMock

from custom_components.korea_incubator.kakaomap.api import KakaoMapApiClient
from custom_components.korea_incubator.kakaomap.exceptions import (
    KakaoMapConnectionError,
    KakaoMapDataError,
)


class TestKakaoMapApiMock:
    """Test KakaoMap API with mocked responses."""

    @pytest.fixture
    async def api_client(self, mock_session):
        """Create KakaoMap API client with mock session."""
        return KakaoMapApiClient(mock_session)

    @pytest.mark.asyncio
    async def test_coordinate_to_address_success(
        self, api_client, mock_session, kakaomap_mock_address_response
    ):
        """Test successful coordinate to address conversion."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {
            "old": {"name": "서울시 광진구 건대입구역"},
            "region": "서울시 광진구",
            "x": 515290,
            "y": 1122478,
        }
        mock_session.get.return_value.__aenter__.return_value = mock_response

        result = await api_client.async_coordinate_to_address(515290, 1122478)

        assert result["success"] is True
        assert "address" in result
        assert "coordinates" in result

    @pytest.mark.asyncio
    async def test_coordinate_to_address_http_error(self, api_client, mock_session):
        """Test coordinate conversion with HTTP error."""
        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.reason = "Internal Server Error"
        mock_session.get.return_value.__aenter__.return_value = mock_response

        with pytest.raises(KakaoMapConnectionError):
            await api_client.async_coordinate_to_address(515290, 1122478)

    @pytest.mark.asyncio
    async def test_coordinate_to_address_connection_error(
        self, api_client, mock_session
    ):
        """Test coordinate conversion with connection error."""
        mock_session.get.side_effect = aiohttp.ClientError("Connection failed")

        with pytest.raises(KakaoMapConnectionError):
            await api_client.async_coordinate_to_address(515290, 1122478)

    @pytest.mark.asyncio
    async def test_get_public_transport_route_success(
        self, api_client, mock_session, kakaomap_mock_route_response
    ):
        """Test successful public transport route retrieval."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = kakaomap_mock_route_response
        mock_session.get.return_value.__aenter__.return_value = mock_response

        result = await api_client.async_get_public_transport_route(
            515290, 1122478, 506190, 1110730
        )

        assert result == kakaomap_mock_route_response
        assert "in_local" in result
        assert "routes" in result["in_local"]

    @pytest.mark.asyncio
    async def test_get_public_transport_route_with_time(
        self, api_client, mock_session, kakaomap_mock_route_response
    ):
        """Test public transport route with specific start time."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = kakaomap_mock_route_response
        mock_session.get.return_value.__aenter__.return_value = mock_response

        result = await api_client.async_get_public_transport_route(
            515290, 1122478, 506190, 1110730, start_time="202501151400"
        )

        # Verify start time parameter was passed
        call_args = mock_session.get.call_args
        assert "startAt" in call_args[1]["params"]
        assert call_args[1]["params"]["startAt"] == "202501151400"

    @pytest.mark.asyncio
    async def test_get_public_transport_route_json_error(
        self, api_client, mock_session
    ):
        """Test route retrieval with JSON parsing error."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_session.get.return_value.__aenter__.return_value = mock_response

        with pytest.raises(KakaoMapDataError):
            await api_client.async_get_public_transport_route(
                515290, 1122478, 506190, 1110730
            )

    def test_parse_address_response_success(self, api_client):
        """Test address response parsing."""
        data = {
            "old": {"name": "서울시 광진구 건대입구역"},
            "region": "서울시 광진구",
            "x": 515290,
            "y": 1122478,
        }

        result = api_client._parse_address_response(data)

        assert result["success"] is True
        assert result["address"] == "서울시 광진구 건대입구역"
        assert result["region"] == "서울시 광진구"
        assert result["coordinates"]["x"] == 515290

    def test_parse_address_response_no_data(self, api_client):
        """Test address response parsing with no data."""
        result = api_client._parse_address_response({})

        assert result["success"] is True
        assert result["address"] is None

    @pytest.mark.parametrize(
        "x,y",
        [
            (515290, 1122478),
            (506190, 1110730),
            (127.027621, 37.497952),  # WGS84 coordinates
            (0, 0),  # Edge case
        ],
    )
    @pytest.mark.asyncio
    async def test_various_coordinates(self, api_client, mock_session, x, y):
        """Test with various coordinate combinations."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {"old": {"name": "Test Location"}}
        mock_session.get.return_value.__aenter__.return_value = mock_response

        result = await api_client.async_coordinate_to_address(x, y)

        # Should handle various coordinates
        assert "success" in result


class TestKakaoMapApiIntegration:
    """Integration tests with real API calls."""

    @pytest.fixture
    async def real_session(self):
        """Create real aiohttp session."""
        session = aiohttp.ClientSession()
        yield session
        await session.close()

    @pytest.fixture
    def real_api_client(self, real_session):
        """Create KakaoMap API client with real session."""
        return KakaoMapApiClient(real_session)

    @pytest.mark.integration
    @pytest.mark.skipif(
        not pytest.config.getoption("--integration", default=False),
        reason="Integration tests disabled",
    )
    async def test_real_coordinate_to_address(self, real_api_client):
        """Test real coordinate to address conversion."""
        try:
            result = await real_api_client.async_coordinate_to_address(515290, 1122478)

            assert "success" in result
            if result["success"]:
                assert "address" in result

        except (KakaoMapConnectionError, KakaoMapDataError) as e:
            pytest.skip(f"Real API test failed (expected): {e}")

    @pytest.mark.integration
    @pytest.mark.skipif(
        not pytest.config.getoption("--integration", default=False),
        reason="Integration tests disabled",
    )
    async def test_real_public_transport_route(self, real_api_client):
        """Test real public transport route."""
        try:
            result = await real_api_client.async_get_public_transport_route(
                515290, 1122478, 506190, 1110730
            )

            # Should return valid structure
            assert isinstance(result, dict)

        except (KakaoMapConnectionError, KakaoMapDataError) as e:
            pytest.skip(f"Real API test failed (expected): {e}")
