"""Integration tests for Korea sensors with all services."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from custom_components.korea_incubator.sensor import async_setup_entry, KoreaSensor
from custom_components.korea_incubator.const import DOMAIN


class TestSensorIntegration:
    """Test sensor integration with all services."""

    @pytest.fixture
    def mock_add_entities(self):
        """Create mock async_add_entities function."""
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_setup_kepco_sensors(
        self,
        mock_hass,
        mock_entry_kepco,
        mock_add_entities,
        mock_coordinator,
        kepco_mock_response,
    ):
        """Test KEPCO sensor setup."""
        # Setup coordinator data
        mock_coordinator.data = kepco_mock_response

        # Setup device mock
        mock_device = MagicMock()
        mock_device.unique_id = "kepco_test"
        mock_device.available = True
        mock_device.device_info = {"name": "한전 (test)"}

        # Setup hass data
        mock_hass.data[DOMAIN] = {
            mock_entry_kepco.entry_id: {
                "coordinator": mock_coordinator,
                "device": mock_device,
            }
        }

        await async_setup_entry(mock_hass, mock_entry_kepco, mock_add_entities)

        # Verify sensors were created
        mock_add_entities.assert_called_once()
        entities = mock_add_entities.call_args[0][0]

        # Should create multiple KEPCO sensors
        assert len(entities) > 10

        # Check specific sensor types
        sensor_names = [entity._attr_name for entity in entities]
        assert "전월 요금" in sensor_names
        assert "현재 사용량" in sensor_names
        assert "당월 예상 요금" in sensor_names

    @pytest.mark.asyncio
    async def test_setup_gasapp_sensors(
        self,
        mock_hass,
        mock_entry_gasapp,
        mock_add_entities,
        mock_coordinator,
        gasapp_mock_response,
    ):
        """Test GasApp sensor setup."""
        mock_coordinator.data = {"current_bill": gasapp_mock_response["cards"]["bill"]}

        mock_device = MagicMock()
        mock_device.unique_id = "gasapp_test"
        mock_device.available = True
        mock_device.device_info = {"name": "가스앱 (test)"}

        mock_hass.data[DOMAIN] = {
            mock_entry_gasapp.entry_id: {
                "coordinator": mock_coordinator,
                "device": mock_device,
            }
        }

        await async_setup_entry(mock_hass, mock_entry_gasapp, mock_add_entities)

        entities = mock_add_entities.call_args[0][0]
        sensor_names = [entity._attr_name for entity in entities]

        assert "당월 가스 사용량" in sensor_names
        assert "당월 가스 요금" in sensor_names
        assert "지난달 가스 사용량" in sensor_names

    @pytest.mark.asyncio
    async def test_setup_safety_alert_sensors(
        self,
        mock_hass,
        mock_entry_safety_alert,
        mock_add_entities,
        mock_coordinator,
        safety_alert_mock_response,
    ):
        """Test Safety Alert sensor setup."""
        mock_coordinator.data = {
            "metadata": {"count": 2},
            "parsed_data": {"data": safety_alert_mock_response["disasterSmsList"]},
        }

        mock_device = MagicMock()
        mock_device.unique_id = "safety_alert_test"
        mock_device.available = True
        mock_device.device_info = {"name": "안전알림 (서울)"}

        mock_hass.data[DOMAIN] = {
            mock_entry_safety_alert.entry_id: {
                "coordinator": mock_coordinator,
                "device": mock_device,
            }
        }

        await async_setup_entry(mock_hass, mock_entry_safety_alert, mock_add_entities)

        entities = mock_add_entities.call_args[0][0]
        sensor_names = [entity._attr_name for entity in entities]

        assert "총 안전알림 수" in sensor_names
        assert "최신 알림 유형" in sensor_names
        assert "최신 알림 내용" in sensor_names

    @pytest.mark.asyncio
    async def test_setup_arisu_sensors(
        self, mock_hass, mock_add_entities, mock_coordinator, arisu_mock_response
    ):
        """Test Arisu sensor setup."""
        entry = MagicMock()
        entry.entry_id = "test_arisu_entry"
        entry.data = {"service": "arisu"}

        mock_coordinator.data = {"bill_data": arisu_mock_response}

        mock_device = MagicMock()
        mock_device.unique_id = "arisu_test"
        mock_device.available = True
        mock_device.device_info = {"name": "아리수 (test)"}

        mock_hass.data[DOMAIN] = {
            entry.entry_id: {"coordinator": mock_coordinator, "device": mock_device}
        }

        await async_setup_entry(mock_hass, entry, mock_add_entities)

        entities = mock_add_entities.call_args[0][0]
        sensor_names = [entity._attr_name for entity in entities]

        assert "총 요금" in sensor_names
        assert "당월 사용량" in sensor_names
        assert "고객 주소" in sensor_names

    @pytest.mark.asyncio
    async def test_setup_kakaomap_sensors(
        self, mock_hass, mock_add_entities, mock_coordinator
    ):
        """Test KakaoMap sensor setup."""
        entry = MagicMock()
        entry.entry_id = "test_kakaomap_entry"
        entry.data = {"service": "kakaomap"}

        mock_route_data = {
            "summary": {
                "recommended_route": {"time": 28, "fare": 1370},
                "total_routes": 3,
            },
            "routes": [{"time": 28, "fare": 1370, "type": "지하철"}],
        }

        mock_coordinator.data = {
            "start_address": {"address": "건대입구역"},
            "end_address": {"address": "강남역"},
            "transport_route": mock_route_data,
        }

        mock_device = MagicMock()
        mock_device.unique_id = "kakaomap_test"
        mock_device.available = True
        mock_device.device_info = {"name": "카카오맵 (집↔회사)"}

        mock_hass.data[DOMAIN] = {
            entry.entry_id: {"coordinator": mock_coordinator, "device": mock_device}
        }

        await async_setup_entry(mock_hass, entry, mock_add_entities)

        entities = mock_add_entities.call_args[0][0]
        sensor_names = [entity._attr_name for entity in entities]

        assert "출발지 주소" in sensor_names
        assert "도착지 주소" in sensor_names
        assert "추천 경로 소요시간" in sensor_names


class TestKoreaSensorEntity:
    """Test KoreaSensor entity functionality."""

    @pytest.fixture
    def mock_device(self):
        """Create mock device."""
        device = MagicMock()
        device.unique_id = "test_device"
        device.available = True
        device.device_info = {
            "identifiers": {("korea_incubator", "test_device")},
            "name": "Test Device",
            "manufacturer": "Test Manufacturer",
        }
        return device

    @pytest.fixture
    def test_sensor(self, mock_coordinator, mock_device):
        """Create test sensor."""
        mock_coordinator.data = {
            "usage_info": {
                "result": {"BILL_LAST_MONTH": "25,000", "PREDICT_KWH": "150.5"}
            }
        }

        return KoreaSensor(
            mock_coordinator,
            mock_device,
            "usage_info",
            "result.BILL_LAST_MONTH",
            "전월 요금",
            SensorDeviceClass.MONETARY,
            "KRW",
            SensorStateClass.TOTAL,
        )

    def test_sensor_properties(self, test_sensor):
        """Test sensor basic properties."""
        assert test_sensor._attr_name == "전월 요금"
        assert test_sensor._attr_device_class == SensorDeviceClass.MONETARY
        assert test_sensor._attr_native_unit_of_measurement == "KRW"
        assert test_sensor._attr_state_class == SensorStateClass.TOTAL

    def test_sensor_unique_id(self, test_sensor):
        """Test sensor unique ID generation."""
        expected_id = "korea_test_device_usage_info_result_BILL_LAST_MONTH"
        assert test_sensor._attr_unique_id == expected_id

    def test_sensor_native_value_monetary(self, test_sensor):
        """Test monetary value parsing."""
        # "25,000" should be converted to 25000
        assert test_sensor.native_value == 25000

    def test_sensor_availability(self, test_sensor, mock_coordinator, mock_device):
        """Test sensor availability logic."""
        # Both device and coordinator available
        assert test_sensor.available is True

        # Device unavailable
        mock_device.available = False
        assert test_sensor.available is False

        # Coordinator update failed
        mock_device.available = True
        mock_coordinator.last_update_success = False
        assert test_sensor.available is False

    def test_sensor_device_info(self, test_sensor, mock_device):
        """Test sensor device info."""
        assert test_sensor.device_info == mock_device.device_info

    def test_sensor_with_no_data(self, mock_coordinator, mock_device):
        """Test sensor behavior with no coordinator data."""
        mock_coordinator.data = None

        sensor = KoreaSensor(
            mock_coordinator,
            mock_device,
            "usage_info",
            "result.BILL_LAST_MONTH",
            "전월 요금",
            SensorDeviceClass.MONETARY,
            "KRW",
            SensorStateClass.TOTAL,
        )

        assert sensor.native_value is None

    def test_sensor_with_missing_path(self, mock_coordinator, mock_device):
        """Test sensor with missing data path."""
        mock_coordinator.data = {"usage_info": {}}  # Missing "result.BILL_LAST_MONTH"

        sensor = KoreaSensor(
            mock_coordinator,
            mock_device,
            "usage_info",
            "result.BILL_LAST_MONTH",
            "전월 요금",
            SensorDeviceClass.MONETARY,
            "KRW",
            SensorStateClass.TOTAL,
        )

        assert sensor.native_value is None

    @pytest.mark.parametrize(
        "device_class,raw_value,expected",
        [
            (SensorDeviceClass.MONETARY, "25,000원", 25000),
            (SensorDeviceClass.DURATION, "28분", 28),
            (SensorDeviceClass.DISTANCE, "1,500m", 1500),
            (SensorDeviceClass.GAS, "15.5m³", 15),
            (
                None,
                "텍스트값",
                "텍스트값",
            ),  # No conversion for non-numeric device classes
        ],
    )
    def test_sensor_value_conversion(
        self, mock_coordinator, mock_device, device_class, raw_value, expected
    ):
        """Test various value conversions based on device class."""
        mock_coordinator.data = {"test_data": {"value": raw_value}}

        sensor = KoreaSensor(
            mock_coordinator,
            mock_device,
            "test_data",
            "value",
            "테스트 센서",
            device_class,
            "unit",
            None,
        )

        assert sensor.native_value == expected
