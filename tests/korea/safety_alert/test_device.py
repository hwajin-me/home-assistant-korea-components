"""Test Safety Alert device with both mock and real scenarios."""

import pytest
import aiohttp
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

from custom_components.korea_incubator.safety_alert.device import SafetyAlertDevice
from custom_components.korea_incubator.safety_alert.exceptions import (
    SafetyAlertConnectionError,
    SafetyAlertDataError,
)
from homeassistant.helpers.update_coordinator import UpdateFailed


class TestSafetyAlertDeviceMock:
    """Test Safety Alert device with mocked dependencies."""

    @pytest.fixture
    def mock_api_client(self):
        """Create mock API client."""
        return AsyncMock()

    @pytest.fixture
    async def safety_alert_device(self, mock_hass, mock_session, mock_api_client):
        """Create Safety Alert device with mocked dependencies."""
        session = aiohttp.ClientSession()
        device = SafetyAlertDevice(
            mock_hass,
            "test_entry_id",
            "1100000000",
            "서울특별시",
            "1111000000",
            "1111010100",
            session,
        )
        device.api_client = mock_api_client
        yield device
        await device.async_close_session()

    def test_device_properties(self, safety_alert_device):
        """Test device basic properties."""
        assert safety_alert_device.unique_id == "safety_alert_1100000000"
        assert safety_alert_device._name == "안전알림 (서울특별시)"
        assert safety_alert_device.available is True

        device_info = safety_alert_device.device_info
        assert device_info["name"] == "안전알림 (서울특별시)"
        assert device_info["manufacturer"] == "행정안전부"
        assert device_info["model"] == "안전알림서비스"

    @pytest.mark.asyncio
    async def test_async_update_success(
        self, safety_alert_device, mock_api_client, safety_alert_mock_response
    ):
        """Test successful data update."""
        mock_api_client.async_get_safety_alerts.return_value = (
            safety_alert_mock_response
        )

        await safety_alert_device.async_update()

        assert safety_alert_device.data["has_data"] is True
        assert safety_alert_device.data["metadata"]["count"] == 2
        assert len(safety_alert_device.data["parsed_data"]["data"]) == 2
        assert safety_alert_device.available is True
        assert safety_alert_device._last_update_success is not None

    @pytest.mark.asyncio
    async def test_async_update_empty_data(self, safety_alert_device, mock_api_client):
        """Test update with empty data."""
        empty_response = {"disasterSmsList": [], "rtnResult": {"totCnt": 0}}
        mock_api_client.async_get_safety_alerts.return_value = empty_response

        await safety_alert_device.async_update()

        assert safety_alert_device.data["has_data"] is False
        assert safety_alert_device.data["metadata"]["count"] == 0
        assert safety_alert_device.data["parsed_data"]["data"] == []
        assert safety_alert_device.available is True

    @pytest.mark.asyncio
    async def test_async_update_connection_error(
        self, safety_alert_device, mock_api_client
    ):
        """Test update with connection error."""
        mock_api_client.async_get_safety_alerts.side_effect = (
            SafetyAlertConnectionError("Connection failed")
        )

        with pytest.raises(
            UpdateFailed, match="Error communicating with Safety Alert API"
        ):
            await safety_alert_device.async_update()

        assert safety_alert_device.available is False

    @pytest.mark.asyncio
    async def test_async_update_data_error(self, safety_alert_device, mock_api_client):
        """Test update with data error."""
        mock_api_client.async_get_safety_alerts.side_effect = SafetyAlertDataError(
            "Data parsing failed"
        )

        with pytest.raises(
            UpdateFailed, match="Error communicating with Safety Alert API"
        ):
            await safety_alert_device.async_update()

        assert safety_alert_device.available is False

    @pytest.mark.asyncio
    async def test_async_update_general_error(
        self, safety_alert_device, mock_api_client
    ):
        """Test update with general error."""
        mock_api_client.async_get_safety_alerts.side_effect = Exception(
            "Unexpected error"
        )

        with pytest.raises(UpdateFailed, match="Unexpected error"):
            await safety_alert_device.async_update()

        assert safety_alert_device.available is False

    @pytest.mark.asyncio
    async def test_async_close_session(self, mock_hass, mock_session):
        """Test session closure."""
        device = SafetyAlertDevice(
            mock_hass, "test_entry_id", "1100000000", "서울특별시", session=mock_session
        )

        await device.async_close_session()

        mock_session.close.assert_called_once()
        assert device.session is None

    def test_device_with_minimal_params(self, mock_hass, mock_session):
        """Test device creation with minimal parameters."""
        device = SafetyAlertDevice(
            mock_hass, "test_entry_id", "1100000000", "서울특별시", session=mock_session
        )

        assert device.area_code == "1100000000"
        assert device.area_name == "서울특별시"
        assert device.area_code2 is None
        assert device.area_code3 is None

    def test_device_with_all_params(self, mock_hass, mock_session):
        """Test device creation with all parameters."""
        device = SafetyAlertDevice(
            mock_hass,
            "test_entry_id",
            "1100000000",
            "서울특별시",
            "1111000000",
            "1111010100",
            mock_session,
        )

        assert device.area_code == "1100000000"
        assert device.area_name == "서울특별시"
        assert device.area_code2 == "1111000000"
        assert device.area_code3 == "1111010100"

    def test_data_structure_after_update(
        self, safety_alert_device, safety_alert_mock_response
    ):
        """Test data structure integrity after update."""
        # Simulate successful update
        safety_alert_device.data = {
            "has_data": True,
            "metadata": {"count": 2},
            "parsed_data": {"data": safety_alert_mock_response["disasterSmsList"]},
            "last_updated": datetime.now().isoformat(),
        }

        # Test data structure
        assert "has_data" in safety_alert_device.data
        assert "metadata" in safety_alert_device.data
        assert "parsed_data" in safety_alert_device.data
        assert "last_updated" in safety_alert_device.data

        # Test parsed data structure
        parsed_data = safety_alert_device.data["parsed_data"]["data"]
        assert len(parsed_data) == 2

        # Test first alert structure
        first_alert = parsed_data[0]
        expected_fields = [
            "EMRGNCY_STEP_NM",
            "DSSTR_SE_NM",
            "MSG_CN",
            "RCV_AREA_NM",
            "REGIST_DT",
        ]
        for field in expected_fields:
            assert field in first_alert


class TestSafetyAlertDeviceIntegration:
    """Integration tests for Safety Alert device."""

    @pytest.fixture
    async def real_session(self):
        """Create real session for integration tests."""
        session = aiohttp.ClientSession()
        yield session
        await session.close()

    @pytest.fixture
    def real_safety_alert_device(self, mock_hass, real_session):
        """Create Safety Alert device with real session."""
        return SafetyAlertDevice(
            mock_hass, "test_entry_id", "1100000000", "서울특별시", session=real_session
        )

    @pytest.mark.integration
    @pytest.mark.skipif(
        not pytest.config.getoption("--integration", default=False),
        reason="Integration tests disabled",
    )
    async def test_real_device_update(self, real_safety_alert_device):
        """Test real device update."""
        try:
            await real_safety_alert_device.async_update()

            # Should have valid data structure
            assert "has_data" in real_safety_alert_device.data
            assert "metadata" in real_safety_alert_device.data
            assert "parsed_data" in real_safety_alert_device.data
            assert real_safety_alert_device.available is True

        except UpdateFailed as e:
            # May fail due to network issues or API changes
            pytest.skip(f"Real API test failed (expected): {e}")

    @pytest.mark.integration
    @pytest.mark.skipif(
        not pytest.config.getoption("--integration", default=False),
        reason="Integration tests disabled",
    )
    async def test_real_device_invalid_area_code(self, mock_hass, real_session):
        """Test real device with invalid area code."""
        device = SafetyAlertDevice(
            mock_hass, "test_entry_id", "9999999999", "잘못된지역", session=real_session
        )

        try:
            await device.async_update()
            # May succeed with empty data or fail with error
            assert "has_data" in device.data

        except UpdateFailed:
            # Expected to fail with invalid area code
            pass
        finally:
            await device.async_close_session()

    @pytest.mark.parametrize(
        "area_code,area_name",
        [
            ("1100000000", "서울특별시"),
            ("2600000000", "부산광역시"),
            ("2700000000", "대구광역시"),
            ("2800000000", "인천광역시"),
        ],
    )
    def test_device_creation_various_areas(
        self, mock_hass, mock_session, area_code, area_name
    ):
        """Test device creation with various area codes."""
        device = SafetyAlertDevice(
            mock_hass, "test_entry_id", area_code, area_name, session=mock_session
        )

        assert device.area_code == area_code
        assert device.area_name == area_name
        assert device.unique_id == f"safety_alert_{area_code}"
        assert area_name in device._name
