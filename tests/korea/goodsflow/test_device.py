"""Test GoodsFlow device with both mock and real scenarios."""
import pytest
import aiohttp
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

from custom_components.korea_incubator.goodsflow.device import GoodsFlowDevice
from custom_components.korea_incubator.goodsflow.exceptions import (
    GoodsFlowAuthError,
    GoodsFlowConnectionError,
    GoodsFlowDataError
)
from homeassistant.helpers.update_coordinator import UpdateFailed


class TestGoodsFlowDeviceMock:
    """Test GoodsFlow device with mocked dependencies."""

    @pytest.fixture
    def mock_api_client(self):
        """Create mock API client."""
        return AsyncMock()

    @pytest.fixture
    async def goodsflow_device(self, mock_hass, mock_session, mock_api_client):
        """Create GoodsFlow device with mocked dependencies."""
        session = aiohttp.ClientSession()
        device = GoodsFlowDevice(
            mock_hass,
            "test_entry_id",
            "test_token",
            session
        )
        device.api_client = mock_api_client
        yield device
        await device.async_close_session()

    def test_device_properties(self, goodsflow_device):
        """Test device basic properties."""
        assert goodsflow_device.unique_id == "goodsflow_test_tok"
        assert goodsflow_device._name == "굿스플로우 택배조회"
        assert goodsflow_device.available is True

        device_info = goodsflow_device.device_info
        assert device_info["name"] == "굿스플로우 택배조회"
        assert device_info["manufacturer"] == "굿스플로우"
        assert device_info["model"] == "택배조회"

    @pytest.mark.asyncio
    async def test_async_update_success(self, goodsflow_device, mock_api_client, goodsflow_mock_response):
        """Test successful data update."""
        parsed_data = {
            "total_packages": 5,
            "active_packages": 2,
            "delivered_packages": 3,
            "packages": goodsflow_mock_response["data"]["transList"]["rows"]
        }

        mock_api_client.async_get_tracking_list.return_value = goodsflow_mock_response
        mock_api_client.parse_tracking_data.return_value = parsed_data

        await goodsflow_device.async_update()

        assert goodsflow_device.data["raw_data"] == goodsflow_mock_response
        assert goodsflow_device.data["parsed_data"] == parsed_data
        assert goodsflow_device.available is True
        assert goodsflow_device._last_update_success is not None

    @pytest.mark.asyncio
    async def test_async_update_auth_error(self, goodsflow_device, mock_api_client):
        """Test update with authentication error."""
        mock_api_client.async_get_tracking_list.side_effect = GoodsFlowAuthError("Authentication failed")

        with pytest.raises(UpdateFailed, match="Authentication failed"):
            await goodsflow_device.async_update()

        assert goodsflow_device.available is False

    @pytest.mark.asyncio
    async def test_async_update_connection_error(self, goodsflow_device, mock_api_client):
        """Test update with connection error."""
        mock_api_client.async_get_tracking_list.side_effect = GoodsFlowConnectionError("Connection failed")

        with pytest.raises(UpdateFailed, match="Error communicating with GoodsFlow API"):
            await goodsflow_device.async_update()

        assert goodsflow_device.available is False

    @pytest.mark.asyncio
    async def test_async_update_data_error(self, goodsflow_device, mock_api_client):
        """Test update with data error."""
        mock_api_client.async_get_tracking_list.side_effect = GoodsFlowDataError("Data parsing failed")

        with pytest.raises(UpdateFailed, match="Error communicating with GoodsFlow API"):
            await goodsflow_device.async_update()

        assert goodsflow_device.available is False

    def test_get_total_packages(self, goodsflow_device):
        """Test total packages retrieval."""
        goodsflow_device.data = {
            "parsed_data": {
                "total_packages": 10,
                "active_packages": 4,
                "delivered_packages": 6
            }
        }

        total = goodsflow_device.get_total_packages()
        assert total == 10

    def test_get_total_packages_no_data(self, goodsflow_device):
        """Test total packages with no data."""
        goodsflow_device.data = {}

        total = goodsflow_device.get_total_packages()
        assert total == 0

    def test_get_active_packages(self, goodsflow_device):
        """Test active packages retrieval."""
        goodsflow_device.data = {
            "parsed_data": {
                "total_packages": 10,
                "active_packages": 4,
                "delivered_packages": 6
            }
        }

        active = goodsflow_device.get_active_packages()
        assert active == 4

    def test_get_delivered_packages(self, goodsflow_device):
        """Test delivered packages retrieval."""
        goodsflow_device.data = {
            "parsed_data": {
                "total_packages": 10,
                "active_packages": 4,
                "delivered_packages": 6
            }
        }

        delivered = goodsflow_device.get_delivered_packages()
        assert delivered == 6

    @pytest.mark.asyncio
    async def test_async_close_session(self, mock_hass, mock_session):
        """Test session closure."""
        device = GoodsFlowDevice(
            mock_hass,
            "test_entry_id",
            "test_token",
            mock_session
        )

        await device.async_close_session()

        mock_session.close.assert_called_once()
        assert device.session is None

    def test_device_data_structure(self, goodsflow_device, goodsflow_mock_response):
        """Test device data structure integrity."""
        parsed_data = {
            "total_packages": 5,
            "active_packages": 2,
            "delivered_packages": 3,
            "packages": []
        }

        goodsflow_device.data = {
            "raw_data": goodsflow_mock_response,
            "parsed_data": parsed_data,
            "last_updated": datetime.now().isoformat()
        }

        # Test data structure
        assert "raw_data" in goodsflow_device.data
        assert "parsed_data" in goodsflow_device.data
        assert "last_updated" in goodsflow_device.data

        # Test parsed data structure
        parsed = goodsflow_device.data["parsed_data"]
        assert "total_packages" in parsed
        assert "active_packages" in parsed
        assert "delivered_packages" in parsed
        assert "packages" in parsed


class TestGoodsFlowDeviceIntegration:
    """Integration tests for GoodsFlow device."""

    @pytest.fixture
    async def real_session(self):
        """Create real session for integration tests."""
        session = aiohttp.ClientSession()
        yield session
        await session.close()

    @pytest.fixture
    def real_goodsflow_device(self, mock_hass, real_session):
        """Create GoodsFlow device with real session."""
        return GoodsFlowDevice(
            mock_hass,
            "test_entry_id",
            "test_token",
            real_session
        )

    @pytest.mark.integration
    @pytest.mark.skipif(
        not pytest.config.getoption("--integration", default=False),
        reason="Integration tests disabled"
    )
    async def test_real_device_update_auth_failure(self, real_goodsflow_device):
        """Test real device update with invalid token."""
        with pytest.raises(UpdateFailed):
            await real_goodsflow_device.async_update()

        assert real_goodsflow_device.available is False

    def test_device_token_storage(self, mock_hass, mock_session):
        """Test device token storage."""
        device = GoodsFlowDevice(
            mock_hass,
            "test_entry",
            "my_secret_token",
            mock_session
        )

        assert device.token == "my_secret_token"
        assert device.unique_id == "goodsflow_my_secre"  # First 8 chars

    @pytest.mark.parametrize("token", [
        "short",
        "very_long_token_that_exceeds_eight_characters",
        "12345678",
        "",
    ])
    def test_device_various_tokens(self, mock_hass, mock_session, token):
        """Test device creation with various token lengths."""
        device = GoodsFlowDevice(
            mock_hass,
            "test_entry",
            token,
            mock_session
        )

        assert device.token == token
        # unique_id should be first 8 chars or less
        expected_id = f"goodsflow_{token[:8]}"
        assert device.unique_id == expected_id
