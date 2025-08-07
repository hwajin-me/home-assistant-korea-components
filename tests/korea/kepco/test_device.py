"""Test KEPCO device with both mock and real scenarios."""
import pytest
import aiohttp
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from custom_components.korea_incubator.kepco.device import KepcoDevice
from custom_components.korea_incubator.kepco.exceptions import KepcoAuthError
from homeassistant.helpers.update_coordinator import UpdateFailed


class TestKepcoDeviceMock:
    """Test KEPCO device with mocked dependencies."""

    @pytest.fixture
    def mock_api_client(self):
        """Create mock API client."""
        return AsyncMock()

    @pytest.fixture
    async def kepco_device(self, mock_hass, mock_session, mock_api_client):
        """Create KEPCO device with mocked dependencies."""
        session = aiohttp.ClientSession()
        device = KepcoDevice(
            mock_hass,
            "test_entry",
            "test_user",
            "test_password",
            session
        )
        device.api_client = mock_api_client
        yield device
        await device.async_close_session()

    def test_device_properties(self, kepco_device):
        """Test device basic properties."""
        assert kepco_device.unique_id == "kepco_test_user"
        assert kepco_device._name == "한전 (test_user)"
        assert kepco_device.available is True

        device_info = kepco_device.device_info
        assert device_info["name"] == "한전 (test_user)"
        assert device_info["manufacturer"] == "한국전력공사"
        assert device_info["model"] == "KEPCO"

    @pytest.mark.asyncio
    async def test_async_update_success(self, kepco_device, mock_api_client, kepco_mock_response):
        """Test successful data update."""
        mock_api_client.async_get_recent_usage.return_value = kepco_mock_response["recent_usage"]
        mock_api_client.async_get_usage_info.return_value = kepco_mock_response["usage_info"]

        await kepco_device.async_update()

        assert kepco_device.data["recent_usage"] == kepco_mock_response["recent_usage"]
        assert kepco_device.data["usage_info"] == kepco_mock_response["usage_info"]
        assert kepco_device.available is True
        assert kepco_device._last_update_success is not None

    @pytest.mark.asyncio
    async def test_async_update_auth_error(self, kepco_device, mock_api_client):
        """Test update with authentication error."""
        mock_api_client.async_get_recent_usage.side_effect = KepcoAuthError("Authentication failed")

        with pytest.raises(UpdateFailed, match="Authentication error"):
            await kepco_device.async_update()

        assert kepco_device.available is False

    @pytest.mark.asyncio
    async def test_async_update_general_error(self, kepco_device, mock_api_client):
        """Test update with general error."""
        mock_api_client.async_get_recent_usage.side_effect = Exception("Network error")

        with pytest.raises(UpdateFailed, match="Error communicating with KEPCO API"):
            await kepco_device.async_update()

        assert kepco_device.available is False

    def test_get_current_usage(self, kepco_device, kepco_mock_response):
        """Test current usage retrieval."""
        kepco_device.data = kepco_mock_response

        usage = kepco_device.get_current_usage()
        assert usage == "123.45"

    def test_get_current_usage_no_data(self, kepco_device):
        """Test current usage with no data."""
        kepco_device.data = {}

        usage = kepco_device.get_current_usage()
        assert usage is None

    def test_get_last_month_bill(self, kepco_device, kepco_mock_response):
        """Test last month bill retrieval."""
        kepco_device.data = kepco_mock_response

        bill = kepco_device.get_last_month_bill()
        assert bill == "25000"

    def test_get_predicted_bill(self, kepco_device, kepco_mock_response):
        """Test predicted bill retrieval."""
        kepco_device.data = kepco_mock_response

        bill = kepco_device.get_predicted_bill()
        assert bill == "30000"

    @pytest.mark.asyncio
    async def test_async_close_session(self, kepco_device):
        """Test session closure."""
        kepco_device.session.closed = False

        await kepco_device.async_close_session()

        kepco_device.session.close.assert_called_once()
        assert kepco_device.session is None

    @pytest.mark.asyncio
    async def test_async_close_session_already_closed(self, kepco_device):
        """Test session closure when already closed."""
        kepco_device.session.closed = True

        await kepco_device.async_close_session()

        kepco_device.session.close.assert_not_called()


class TestKepcoDeviceIntegration:
    """Integration tests for KEPCO device."""

    @pytest.fixture
    async def real_session(self):
        """Create real session for integration tests."""
        from curl_cffi import AsyncSession
        session = AsyncSession()
        yield session
        await session.close()

    @pytest.fixture
    def real_kepco_device(self, mock_hass, real_session):
        """Create KEPCO device with real session."""
        return KepcoDevice(
            mock_hass,
            "test_entry_id",
            "test_user",
            "test_password",
            real_session
        )

    @pytest.mark.integration
    @pytest.mark.skipif(
        not pytest.config.getoption("--integration", default=False),
        reason="Integration tests disabled"
    )
    async def test_real_device_update_auth_failure(self, real_kepco_device):
        """Test real device update with invalid credentials."""
        with pytest.raises(UpdateFailed):
            await real_kepco_device.async_update()

        assert real_kepco_device.available is False

    @pytest.mark.parametrize("username,password", [
        ("", "password"),
        ("username", ""),
        (None, None),
    ])
    def test_device_with_invalid_credentials(self, mock_hass, mock_session, username, password):
        """Test device creation with invalid credentials."""
        device = KepcoDevice(mock_hass, "test_entry", username, password, mock_session)
        assert device.username == username
        assert device.password == password
        # Device should still be created but will fail on API calls

    def test_device_data_structure(self, kepco_device, kepco_mock_response):
        """Test device data structure integrity."""
        kepco_device.data = kepco_mock_response

        # Test data structure
        assert "recent_usage" in kepco_device.data
        assert "usage_info" in kepco_device.data
        assert "result" in kepco_device.data["recent_usage"]
        assert "result" in kepco_device.data["usage_info"]

        # Test required fields exist
        recent_result = kepco_device.data["recent_usage"]["result"]
        assert "F_AP_QT" in recent_result
        assert "ST_TIME" in recent_result

        usage_result = kepco_device.data["usage_info"]["result"]
        assert "BILL_LAST_MONTH" in usage_result
        assert "PREDICT_TOTAL_CHARGE_REV" in usage_result
