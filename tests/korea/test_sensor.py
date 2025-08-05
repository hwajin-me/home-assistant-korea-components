import pytest
from unittest.mock import MagicMock, AsyncMock
from custom_components.korea_incubator.sensor import (
    get_value_from_path,
    parse_date_value,
    KoreaSensor
)
from custom_components.korea_incubator.kepco.device import KepcoDevice
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from datetime import datetime


@pytest.fixture
def mock_coordinator():
    coordinator = MagicMock(spec=DataUpdateCoordinator)
    coordinator.data = {
        "usage_info": {
            "result": {
                "BILL_LAST_MONTH": "25,000",
                "PREDICT_KWH": "150.5",
                "F_AP_QT": "123.45"
            },
            "SESS_MR_ST_DT": "2025-01-01",
            "SESS_CUSTNO": "123456789"
        },
        "recent_usage": {
            "result": {
                "F_AP_QT": "123.45",
                "ST_TIME": "2025-01-15 14:30:00"
            }
        }
    }
    coordinator.last_update_success = True
    return coordinator


@pytest.fixture
def mock_device():
    device = MagicMock(spec=KepcoDevice)
    device.unique_id = "kepco_test"
    device.available = True
    device.device_info = {
        "identifiers": {("korea_incubator", "kepco_test")},
        "name": "한전 (test)",
        "manufacturer": "한국전력공사"
    }
    return device


class TestGetValueFromPath:
    def test_simple_path(self):
        data = {"key1": {"key2": "value"}}
        assert get_value_from_path(data, "key1.key2") == "value"

    def test_array_index_with_brackets(self):
        data = {"items": ["first", "second", "third"]}
        assert get_value_from_path(data, "items[0]") == "first"
        assert get_value_from_path(data, "items[-1]") == "third"

    def test_array_index_with_dots(self):
        data = {"items": ["first", "second", "third"]}
        assert get_value_from_path(data, "items.0") == "first"
        assert get_value_from_path(data, "items.-1") == "third"

    def test_nested_array_access(self):
        data = {"data": {"history": [{"value": 10}, {"value": 20}]}}
        assert get_value_from_path(data, "data.history[0].value") == 10
        assert get_value_from_path(data, "data.history[-1].value") == 20

    def test_missing_key(self):
        data = {"key1": "value"}
        assert get_value_from_path(data, "missing.key") is None

    def test_index_out_of_range(self):
        data = {"items": ["first"]}
        assert get_value_from_path(data, "items[5]") is None

    def test_none_value(self):
        assert get_value_from_path(None, "any.path") is None


class TestParseDateValue:
    def test_yyyy_mm_dd_format(self):
        result = parse_date_value("2025-01-15")
        assert result.year == 2025
        assert result.month == 1
        assert result.day == 15

    def test_yyyymmdd_format(self):
        result = parse_date_value("20250115")
        assert result.year == 2025
        assert result.month == 1
        assert result.day == 15

    def test_korean_date_format(self):
        result = parse_date_value("2025년 1월 15일")
        assert result.year == 2025
        assert result.month == 1
        assert result.day == 15

    def test_korean_year_month_format(self):
        result = parse_date_value("2025년 1월")
        assert result.year == 2025
        assert result.month == 1
        assert result.day == 1  # Default to 1st day

    def test_us_date_format(self):
        result = parse_date_value("01/15/2025")
        assert result.year == 2025
        assert result.month == 1
        assert result.day == 15

    def test_invalid_date(self):
        assert parse_date_value("invalid date") is None
        assert parse_date_value("") is None
        assert parse_date_value(None) is None

    def test_yyyy_mm_format(self):
        result = parse_date_value("2025-01")
        assert result.year == 2025
        assert result.month == 1
        assert result.day == 1


class TestKoreaSensor:
    def test_sensor_initialization(self, mock_coordinator, mock_device):
        sensor = KoreaSensor(
            mock_coordinator,
            mock_device,
            "usage_info",
            "result.BILL_LAST_MONTH",
            "전월 요금",
            SensorDeviceClass.MONETARY,
            "KRW",
            SensorStateClass.TOTAL
        )

        assert sensor._attr_name == "전월 요금"
        assert sensor._attr_device_class == SensorDeviceClass.MONETARY
        assert sensor._attr_native_unit_of_measurement == "KRW"
        assert sensor._attr_state_class == SensorStateClass.TOTAL
        assert sensor._attr_unique_id == "kepco_test_usage_info_result_BILL_LAST_MONTH"

    def test_native_value_monetary(self, mock_coordinator, mock_device):
        sensor = KoreaSensor(
            mock_coordinator,
            mock_device,
            "usage_info",
            "result.BILL_LAST_MONTH",
            "전월 요금",
            SensorDeviceClass.MONETARY,
            "KRW",
            SensorStateClass.TOTAL
        )

        # "25,000" should be converted to 25000
        assert sensor.native_value == 25000

    def test_native_value_energy(self, mock_coordinator, mock_device):
        sensor = KoreaSensor(
            mock_coordinator,
            mock_device,
            "usage_info",
            "result.F_AP_QT",
            "사용량",
            SensorDeviceClass.ENERGY,
            "kWh",
            SensorStateClass.TOTAL
        )

        # Should return the string value as-is for energy
        assert sensor.native_value == "123.45"

    def test_native_value_date(self, mock_coordinator, mock_device):
        sensor = KoreaSensor(
            mock_coordinator,
            mock_device,
            "usage_info",
            "SESS_MR_ST_DT",
            "검침시작일",
            SensorDeviceClass.DATE,
            None,
            None
        )

        result = sensor.native_value
        assert result.year == 2025
        assert result.month == 1
        assert result.day == 1

    def test_native_value_timestamp(self, mock_coordinator, mock_device):
        sensor = KoreaSensor(
            mock_coordinator,
            mock_device,
            "recent_usage",
            "result.ST_TIME",
            "최근 사용량 시간",
            SensorDeviceClass.TIMESTAMP,
            None,
            None
        )

        result = sensor.native_value
        assert isinstance(result, datetime)

    def test_native_value_no_data(self, mock_device):
        # Mock coordinator with no data
        empty_coordinator = MagicMock(spec=DataUpdateCoordinator)
        empty_coordinator.data = None
        empty_coordinator.last_update_success = True

        sensor = KoreaSensor(
            empty_coordinator,
            mock_device,
            "usage_info",
            "result.BILL_LAST_MONTH",
            "전월 요금",
            SensorDeviceClass.MONETARY,
            "KRW",
            SensorStateClass.TOTAL
        )

        assert sensor.native_value is None

    def test_available_property(self, mock_coordinator, mock_device):
        sensor = KoreaSensor(
            mock_coordinator,
            mock_device,
            "usage_info",
            "result.BILL_LAST_MONTH",
            "전월 요금",
            SensorDeviceClass.MONETARY,
            "KRW",
            SensorStateClass.TOTAL
        )

        assert sensor.available is True

        # Test when device is not available
        mock_device.available = False
        assert sensor.available is False

    def test_device_info_property(self, mock_coordinator, mock_device):
        sensor = KoreaSensor(
            mock_coordinator,
            mock_device,
            "usage_info",
            "result.BILL_LAST_MONTH",
            "전월 요금",
            SensorDeviceClass.MONETARY,
            "KRW",
            SensorStateClass.TOTAL
        )

        assert sensor.device_info == mock_device.device_info

    def test_native_value_duration(self, mock_coordinator, mock_device):
        # Add duration test data to coordinator
        mock_coordinator.data["transport_route"] = {
            "routes": [{"time": "28분"}]
        }

        sensor = KoreaSensor(
            mock_coordinator,
            mock_device,
            "transport_route",
            "routes[0].time",
            "소요시간",
            SensorDeviceClass.DURATION,
            "min",
            None
        )

        # "28분" should be converted to 28
        assert sensor.native_value == 28

    def test_native_value_distance(self, mock_coordinator, mock_device):
        # Add distance test data to coordinator
        mock_coordinator.data["transport_route"] = {
            "routes": [{"distance": "1,500m"}]
        }

        sensor = KoreaSensor(
            mock_coordinator,
            mock_device,
            "transport_route",
            "routes[0].distance",
            "거리",
            SensorDeviceClass.DISTANCE,
            "m",
            None
        )

        # "1,500m" should be converted to 1500
        assert sensor.native_value == 1500
