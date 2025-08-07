"""Test GasApp device with both mock and real scenarios."""
import pytest
import aiohttp
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

from custom_components.korea_incubator.gasapp.device import GasAppDevice
from custom_components.korea_incubator.gasapp.exceptions import (
    GasAppAuthError,
    GasAppConnectionError,
    GasAppDataError
)
from homeassistant.helpers.update_coordinator import UpdateFailed


class TestGasAppDeviceMock:
    """Test GasApp device with mocked dependencies."""

    @pytest.fixture
    def mock_api_client(self):
        """Create mock API client."""
        return AsyncMock()

    @pytest.fixture
    async def gasapp_device(self, mock_hass, mock_session, mock_api_client):
        """Create GasApp device with mocked dependencies."""
        session = aiohttp.ClientSession()
        device = GasAppDevice(
            mock_hass,
            "test_entry_id",
            "test_token",
            "test_member",
            "test_contract",
            session
        )
        device.api_client = mock_api_client
        yield device
        await device.async_close_session()

    def test_device_properties(self, gasapp_device):
        """Test device basic properties."""
        assert gasapp_device.unique_id == "gasapp_test_contract"
        assert gasapp_device._name == "가스앱 (test_contract)"
        assert gasapp_device.available is True

        device_info = gasapp_device.device_info
        assert device_info["name"] == "가스앱 (test_contract)"
        assert device_info["manufacturer"] == "한국가스공사"
        assert device_info["model"] == "가스앱"

    @pytest.mark.asyncio
    async def test_async_update_success(self, gasapp_device, mock_api_client, gasapp_mock_response):
        """Test successful data update."""
        mock_api_client.async_get_home_data.return_value = gasapp_mock_response
        mock_api_client.async_get_bill_history.return_value = gasapp_mock_response["cards"]["bill"]["history"]
        mock_api_client.async_get_current_bill.return_value = gasapp_mock_response["cards"]["bill"]

        await gasapp_device.async_update()

        assert gasapp_device.data["home_data"] == gasapp_mock_response
        assert gasapp_device.data["bill_history"] == gasapp_mock_response["cards"]["bill"]["history"]
        assert gasapp_device.data["current_bill"] == gasapp_mock_response["cards"]["bill"]
        assert gasapp_device.available is True
        assert gasapp_device._last_update_success is not None

    @pytest.mark.asyncio
    async def test_async_update_auth_error(self, gasapp_device, mock_api_client):
        """Test update with authentication error."""
        mock_api_client.async_get_home_data.side_effect = GasAppAuthError("Authentication failed")

        with pytest.raises(UpdateFailed, match="Authentication failed"):
            await gasapp_device.async_update()

        assert gasapp_device.available is False

    @pytest.mark.asyncio
    async def test_async_update_connection_error(self, gasapp_device, mock_api_client):
        """Test update with connection error."""
        mock_api_client.async_get_home_data.side_effect = GasAppConnectionError("Connection failed")

        with pytest.raises(UpdateFailed, match="Error communicating with GasApp API"):
            await gasapp_device.async_update()

        assert gasapp_device.available is False

    @pytest.mark.asyncio
    async def test_async_update_data_error(self, gasapp_device, mock_api_client):
        """Test update with data error."""
        mock_api_client.async_get_home_data.side_effect = GasAppDataError("Data parsing failed")

        with pytest.raises(UpdateFailed, match="Error communicating with GasApp API"):
            await gasapp_device.async_update()

        assert gasapp_device.available is False

    @pytest.mark.asyncio
    async def test_async_update_general_error(self, gasapp_device, mock_api_client):
        """Test update with general error."""
        mock_api_client.async_get_home_data.side_effect = Exception("Unexpected error")

        with pytest.raises(UpdateFailed, match="Unexpected error"):
            await gasapp_device.async_update()

        assert gasapp_device.available is False

    def test_get_current_month_usage(self, gasapp_device, gasapp_mock_response):
        """Test current month usage retrieval."""
        gasapp_device.data = {"current_bill": gasapp_mock_response["cards"]["bill"]}

        usage = gasapp_device.get_current_month_usage()
        assert usage == "25.5"

    def test_get_current_month_usage_no_data(self, gasapp_device):
        """Test current month usage with no data."""
        gasapp_device.data = {}

        usage = gasapp_device.get_current_month_usage()
        assert usage is None

    def test_get_current_month_charge(self, gasapp_device, gasapp_mock_response):
        """Test current month charge retrieval."""
        gasapp_device.data = {"current_bill": gasapp_mock_response["cards"]["bill"]}

        charge = gasapp_device.get_current_month_charge()
        assert charge == "50000"

    def test_get_bill_title(self, gasapp_device, gasapp_mock_response):
        """Test bill title retrieval."""
        gasapp_device.data = {"current_bill": gasapp_mock_response["cards"]["bill"]}

        title = gasapp_device.get_bill_title()
        assert title == "2025년 1월 청구서"

    def test_get_total_charge(self, gasapp_device, gasapp_mock_response):
        """Test total charge retrieval."""
        gasapp_device.data = {"current_bill": gasapp_mock_response["cards"]["bill"]}

        total = gasapp_device.get_total_charge()
        assert total == "총 50,000원"

    @pytest.mark.asyncio
    async def test_async_close_session(self, mock_hass, mock_session):
        """Test session closure."""
        device = GasAppDevice(
            mock_hass,
            "test_entry_id",
            "test_token",
            "test_member",
            "test_contract",
            mock_session
        )

        await device.async_close_session()

        mock_session.close.assert_called_once()
        assert device.session is None

    def test_device_data_structure(self, gasapp_device, gasapp_mock_response):
        """Test device data structure integrity."""
        gasapp_device.data = {
            "home_data": gasapp_mock_response,
            "bill_history": gasapp_mock_response["cards"]["bill"]["history"],
            "current_bill": gasapp_mock_response["cards"]["bill"],
            "last_updated": datetime.now().isoformat()
        }

        # Test data structure
        assert "home_data" in gasapp_device.data
        assert "bill_history" in gasapp_device.data
        assert "current_bill" in gasapp_device.data
        assert "last_updated" in gasapp_device.data

        # Test bill history structure
        history = gasapp_device.data["bill_history"]
        assert len(history) == 3

        # Test current bill structure
        current_bill = gasapp_device.data["current_bill"]
        assert "title1" in current_bill
        assert "title2" in current_bill
        assert "history" in current_bill


class TestGasAppDeviceIntegration:
    """Integration tests for GasApp device."""

    @pytest.fixture
    async def real_session(self):
        """Create real session for integration tests."""
        session = aiohttp.ClientSession()
        yield session
        await session.close()

    @pytest.fixture
    def real_gasapp_device(self, mock_hass, real_session):
        """Create GasApp device with real session."""
        return GasAppDevice(
            mock_hass,
            "test_entry_id",
            "test_token",
            "test_member",
            "test_contract",
            real_session
        )

    @pytest.mark.integration
    @pytest.mark.skipif(
        not pytest.config.getoption("--integration", default=False),
        reason="Integration tests disabled"
    )
    async def test_real_device_update_auth_failure(self, real_gasapp_device):
        """Test real device update with invalid credentials."""
        with pytest.raises(UpdateFailed):
            await real_gasapp_device.async_update()

        assert real_gasapp_device.available is False

    @pytest.mark.parametrize("token,member_id,contract_num", [
        ("", "member", "contract"),
        ("token", "", "contract"),
        ("token", "member", ""),
    ])
    def test_device_with_invalid_credentials(self, mock_hass, mock_session, token, member_id, contract_num):
        """Test device creation with invalid credentials."""
        device = GasAppDevice(mock_hass, "test_entry", token, member_id, contract_num, mock_session)

        assert device.token == token
        assert device.member_id == member_id
        assert device.use_contract_num == contract_num
        # Device should still be created but will fail on API calls

    def test_device_credentials_storage(self, mock_hass, mock_session):
        """Test device credential storage."""
        device = GasAppDevice(
            mock_hass,
            "test_entry",
            "test_token",
            "test_member",
            "test_contract",
            mock_session
        )

        assert device.token == "test_token"
        assert device.member_id == "test_member"
        assert device.use_contract_num == "test_contract"
        assert device.unique_id == "gasapp_test_contract"
