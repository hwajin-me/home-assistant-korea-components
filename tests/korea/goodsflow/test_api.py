"""Test GoodsFlow API client with both mock and real API calls."""
import pytest
import aiohttp
from unittest.mock import AsyncMock

from custom_components.korea_incubator.goodsflow.api import GoodsFlowApiClient
from custom_components.korea_incubator.goodsflow.exceptions import (
    GoodsFlowAuthError,
    GoodsFlowConnectionError,
    GoodsFlowDataError
)


class TestGoodsFlowApiMock:
    """Test GoodsFlow API with mocked responses."""

    @pytest.fixture
    async def api_client(self, mock_session):
        """Create GoodsFlow API client with mock session."""
        client = GoodsFlowApiClient(mock_session)
        client.set_token("test_token")
        return client

    @pytest.mark.asyncio
    async def test_validate_token_success(self, api_client, mock_session, goodsflow_mock_response):
        """Test successful token validation."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = goodsflow_mock_response
        mock_session.get.return_value.__aenter__.return_value = mock_response

        result = await api_client.async_validate_token()
        assert result is True

    @pytest.mark.asyncio
    async def test_validate_token_failure(self, api_client, mock_session):
        """Test token validation failure."""
        mock_response = AsyncMock()
        mock_response.status = 401
        mock_response.reason = "Unauthorized"
        mock_session.get.return_value.__aenter__.return_value = mock_response

        result = await api_client.async_validate_token()
        assert result is False

    @pytest.mark.asyncio
    async def test_get_tracking_list_success(self, api_client, mock_session, goodsflow_mock_response):
        """Test successful tracking list retrieval."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = goodsflow_mock_response
        mock_session.get.return_value.__aenter__.return_value = mock_response

        result = await api_client.async_get_tracking_list()
        assert result == goodsflow_mock_response
        assert "success" in result
        assert "data" in result

    @pytest.mark.asyncio
    async def test_get_tracking_list_with_params(self, api_client, mock_session, goodsflow_mock_response):
        """Test tracking list with custom parameters."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = goodsflow_mock_response
        mock_session.get.return_value.__aenter__.return_value = mock_response

        result = await api_client.async_get_tracking_list(limit=20, start=10, type_filter="DELIVERY")

        # Verify parameters were passed correctly
        call_args = mock_session.get.call_args
        params = call_args[1]["params"]
        assert params["limit"] == "20"
        assert params["start"] == "10"
        assert params["type"] == "DELIVERY"

    @pytest.mark.asyncio
    async def test_get_tracking_list_auth_error(self, api_client, mock_session):
        """Test tracking list with authentication error."""
        mock_response = AsyncMock()
        mock_response.status = 401
        mock_response.reason = "Unauthorized"
        mock_session.get.return_value.__aenter__.return_value = mock_response

        with pytest.raises(GoodsFlowAuthError):
            await api_client.async_get_tracking_list()

    @pytest.mark.asyncio
    async def test_get_tracking_list_forbidden(self, api_client, mock_session):
        """Test tracking list with forbidden error."""
        mock_response = AsyncMock()
        mock_response.status = 403
        mock_response.reason = "Forbidden"
        mock_session.get.return_value.__aenter__.return_value = mock_response

        with pytest.raises(GoodsFlowAuthError):
            await api_client.async_get_tracking_list()

    @pytest.mark.asyncio
    async def test_get_tracking_list_connection_error(self, api_client, mock_session):
        """Test tracking list with connection error."""
        mock_session.get.side_effect = aiohttp.ClientError("Connection failed")

        with pytest.raises(GoodsFlowConnectionError):
            await api_client.async_get_tracking_list()

    @pytest.mark.asyncio
    async def test_token_not_set(self, mock_session):
        """Test API call without setting token."""
        client = GoodsFlowApiClient(mock_session)

        with pytest.raises(GoodsFlowAuthError, match="Token not set"):
            await client.async_get_tracking_list()

    def test_parse_tracking_data_success(self, api_client, goodsflow_mock_response):
        """Test tracking data parsing."""
        result = api_client.parse_tracking_data(goodsflow_mock_response)

        assert "total_packages" in result
        assert "active_packages" in result
        assert "delivered_packages" in result
        assert "packages" in result
        assert result["total_packages"] == 5

    def test_parse_tracking_data_empty(self, api_client):
        """Test tracking data parsing with empty data."""
        result = api_client.parse_tracking_data({})

        assert result["total_packages"] == 0
        assert result["active_packages"] == 0
        assert result["delivered_packages"] == 0
        assert result["packages"] == []

    def test_parse_tracking_data_no_success(self, api_client):
        """Test tracking data parsing with unsuccessful response."""
        data = {"success": False}
        result = api_client.parse_tracking_data(data)

        assert result["total_packages"] == 0
        assert result["active_packages"] == 0
        assert result["delivered_packages"] == 0

    def test_get_headers_with_token(self, api_client):
        """Test header generation with token."""
        headers = api_client._get_headers()

        assert "Cookie" in headers
        assert "PTK-TOKEN=test_token" in headers["Cookie"]
        assert "User-Agent" in headers

    def test_set_token(self, mock_session):
        """Test token setting."""
        client = GoodsFlowApiClient(mock_session)
        client.set_token("new_token")

        assert client._token == "new_token"

    @pytest.mark.parametrize("limit,start,type_filter", [
        (10, 0, "ALL"),
        (20, 10, "DELIVERY"),
        (5, 5, "PICKUP"),
        (100, 0, "CUSTOM"),
    ])
    @pytest.mark.asyncio
    async def test_various_tracking_params(self, api_client, mock_session, goodsflow_mock_response,
                                         limit, start, type_filter):
        """Test tracking list with various parameters."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = goodsflow_mock_response
        mock_session.get.return_value.__aenter__.return_value = mock_response

        result = await api_client.async_get_tracking_list(limit, start, type_filter)

        # Should handle various parameters
        assert "success" in result or "data" in result


class TestGoodsFlowApiIntegration:
    """Integration tests with real API calls."""

    @pytest.fixture
    async def real_session(self):
        """Create real aiohttp session."""
        session = aiohttp.ClientSession()
        yield session
        await session.close()

    @pytest.fixture
    def real_api_client(self, real_session):
        """Create GoodsFlow API client with real session."""
        return GoodsFlowApiClient(real_session)

    @pytest.mark.integration
    @pytest.mark.skipif(
        not pytest.config.getoption("--integration", default=False),
        reason="Integration tests disabled"
    )
    async def test_real_api_invalid_token(self, real_api_client):
        """Test real API with invalid token."""
        real_api_client.set_token("invalid_token")

        with pytest.raises((GoodsFlowAuthError, GoodsFlowConnectionError)):
            await real_api_client.async_get_tracking_list()

    @pytest.mark.integration
    @pytest.mark.skipif(
        not pytest.config.getoption("--integration", default=False),
        reason="Integration tests disabled"
    )
    async def test_real_token_validation_failure(self, real_api_client):
        """Test real token validation with invalid token."""
        real_api_client.set_token("invalid_token")

        result = await real_api_client.async_validate_token()
        assert result is False

    @pytest.mark.integration
    @pytest.mark.skipif(
        not pytest.config.getoption("--integration", default=False),
        reason="Integration tests disabled"
    )
    async def test_real_api_connection(self, real_api_client):
        """Test real API connection (should fail without valid token)."""
        real_api_client.set_token("test")

        try:
            await real_api_client.async_get_tracking_list()
            assert False, "Should have raised an exception"
        except (GoodsFlowAuthError, GoodsFlowConnectionError):
            # Expected to fail without proper authentication
            pass
