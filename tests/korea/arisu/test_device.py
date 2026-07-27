"""Test Arisu device with both mock and real scenarios."""

import pytest
import aiohttp
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

from custom_components.korea_incubator.arisu.device import ArisuDevice
from custom_components.korea_incubator.arisu.exceptions import (
    ArisuAuthError,
    ArisuConnectionError,
    ArisuDataError,
)
from homeassistant.helpers.update_coordinator import UpdateFailed


class TestArisuDeviceMock:
    """Test Arisu device with mocked dependencies."""

    @pytest.fixture
    def mock_api_client(self):
        """Create mock API client."""
        return AsyncMock()

    @pytest.fixture
    async def arisu_device(self, mock_hass, mock_session, mock_api_client):
        """Create Arisu device with mocked dependencies."""
        session = aiohttp.ClientSession()
        device = ArisuDevice(mock_hass, "test_entry_id", "042389659", "홍길동", session)
        device.api_client = mock_api_client
        yield device
        await device.async_close_session()

    def test_device_properties(self, arisu_device):
        """Test device basic properties."""
        assert arisu_device.unique_id == "arisu_042389659"
        assert arisu_device._name == "아리수 (042389659)"
        assert arisu_device.available is True

        device_info = arisu_device.device_info
        assert device_info["name"] == "아리수 (042389659)"
        assert device_info["manufacturer"] == "서울시"
        assert device_info["model"] == "아리수 상수도 고객센터"

    @pytest.mark.asyncio
    async def test_async_update_success(
        self, arisu_device, mock_api_client, arisu_mock_response
    ):
        """Test successful data update."""
        mock_api_client.async_get_water_bill_data.return_value = arisu_mock_response

        await arisu_device.async_update()

        assert arisu_device.data["bill_data"] == arisu_mock_response
        assert arisu_device.available is True
        assert arisu_device._last_update_success is not None

    @pytest.mark.asyncio
    async def test_async_update_auth_error(self, arisu_device, mock_api_client):
        """Test update with authentication error."""
        mock_api_client.async_get_water_bill_data.side_effect = ArisuAuthError(
            "Authentication failed"
        )

        with pytest.raises(UpdateFailed, match="Authentication failed"):
            await arisu_device.async_update()

        assert arisu_device.available is False

    @pytest.mark.asyncio
    async def test_async_update_connection_error(self, arisu_device, mock_api_client):
        """Test update with connection error."""
        mock_api_client.async_get_water_bill_data.side_effect = ArisuConnectionError(
            "Connection failed"
        )

        with pytest.raises(UpdateFailed, match="Error communicating with Arisu API"):
            await arisu_device.async_update()

        assert arisu_device.available is False

    @pytest.mark.asyncio
    async def test_async_update_data_error(self, arisu_device, mock_api_client):
        """Test update with data error."""
        mock_api_client.async_get_water_bill_data.side_effect = ArisuDataError(
            "Data parsing failed"
        )

        with pytest.raises(UpdateFailed, match="Error communicating with Arisu API"):
            await arisu_device.async_update()

        assert arisu_device.available is False

    @pytest.mark.asyncio
    async def test_async_update_api_failure(self, arisu_device, mock_api_client):
        """Test update with API returning failure."""
        mock_api_client.async_get_water_bill_data.return_value = {
            "success": False,
            "error": "No data found",
        }

        with pytest.raises(UpdateFailed, match="No data found"):
            await arisu_device.async_update()

        assert arisu_device.available is False

    def test_get_total_amount(self, arisu_device, arisu_mock_response):
        """Test total amount retrieval."""
        arisu_device.data = {"bill_data": arisu_mock_response}

        amount = arisu_device.get_total_amount()
        assert amount == 45000

    def test_get_total_amount_no_data(self, arisu_device):
        """Test total amount with no data."""
        arisu_device.data = {}

        amount = arisu_device.get_total_amount()
        assert amount == 0

    def test_get_current_usage(self, arisu_device, arisu_mock_response):
        """Test current usage retrieval."""
        arisu_device.data = {"bill_data": arisu_mock_response}

        usage = arisu_device.get_current_usage()
        assert usage == 15

    def test_get_customer_address(self, arisu_device, arisu_mock_response):
        """Test customer address retrieval."""
        arisu_device.data = {"bill_data": arisu_mock_response}

        address = arisu_device.get_customer_address()
        assert address == "서울시 강남구 테헤란로 123"

    def test_get_payment_method(self, arisu_device, arisu_mock_response):
        """Test payment method retrieval."""
        arisu_device.data = {"bill_data": arisu_mock_response}

        payment = arisu_device.get_payment_method()
        assert payment == "자동이체"

    def test_get_overdue_amount(self, arisu_device, arisu_mock_response):
        """Test overdue amount retrieval."""
        arisu_device.data = {"bill_data": arisu_mock_response}

        overdue = arisu_device.get_overdue_amount()
        assert overdue == 0

    def test_get_billing_month(self, arisu_device, arisu_mock_response):
        """Test billing month retrieval."""
        arisu_device.data = {"bill_data": arisu_mock_response}

        month = arisu_device.get_billing_month()
        assert month == "2025-01"

    @pytest.mark.asyncio
    async def test_async_close_session(self, mock_hass, mock_session):
        """Test session closure."""
        device = ArisuDevice(
            mock_hass, "test_entry_id", "042389659", "홍길동", mock_session
        )

        await device.async_close_session()

        mock_session.close.assert_called_once()
        assert device.session is None

    def test_device_data_structure(self, arisu_device, arisu_mock_response):
        """Test device data structure integrity."""
        arisu_device.data = {
            "bill_data": arisu_mock_response,
            "last_updated": datetime.now().isoformat(),
        }

        # Test data structure
        assert "bill_data" in arisu_device.data
        assert "last_updated" in arisu_device.data

        # Test bill data structure
        bill_data = arisu_device.data["bill_data"]
        assert "success" in bill_data
        assert "total_amount" in bill_data
        assert "customer_info" in bill_data
        assert "usage_info" in bill_data
        assert "arrears_info" in bill_data


class TestArisuDeviceIntegration:
    """Integration tests for Arisu device."""

    @pytest.fixture
    async def real_session(self):
        """Create real session for integration tests."""
        session = aiohttp.ClientSession()
        yield session
        await session.close()

    @pytest.fixture
    def real_arisu_device(self, mock_hass, real_session):
        """Create Arisu device with real session."""
        return ArisuDevice(
            mock_hass, "test_entry_id", "042389659", "홍길동", real_session
        )

    @pytest.mark.integration
    @pytest.mark.skipif(
        not pytest.config.getoption("--integration", default=False),
        reason="Integration tests disabled",
    )
    async def test_real_device_update(self, real_arisu_device):
        """Test real device update."""
        try:
            await real_arisu_device.async_update()

            # Should have valid data structure even if unsuccessful
            assert "bill_data" in real_arisu_device.data

        except UpdateFailed as e:
            # Expected to fail with test credentials
            assert real_arisu_device.available is False

    @pytest.mark.parametrize(
        "customer_number,customer_name",
        [
            ("042389659", "홍길동"),
            ("123456789", "김철수"),
            ("", "홍길동"),  # Empty customer number
            ("042389659", ""),  # Empty customer name
        ],
    )
    def test_device_creation_various_data(
        self, mock_hass, mock_session, customer_number, customer_name
    ):
        """Test device creation with various customer data."""
        device = ArisuDevice(
            mock_hass, "test_entry", customer_number, customer_name, mock_session
        )

        assert device.customer_number == customer_number
        assert device.customer_name == customer_name
        assert device.unique_id == f"arisu_{customer_number}"
        assert customer_number in device._name
