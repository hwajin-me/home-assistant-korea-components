import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.setup import async_setup_component
from custom_components.korea_incubator.const import DOMAIN
from custom_components.korea_incubator.sensor import async_setup_entry as sensor_async_setup_entry


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    hass = MagicMock(spec=HomeAssistant)
    hass.data = {DOMAIN: {}}
    return hass


@pytest.fixture
def mock_config_entry():
    """Create a mock config entry."""
    return MagicMock(spec=ConfigEntry)


@pytest.mark.asyncio
async def test_sensor_setup_kepco(mock_hass, mock_config_entry):
    """Test sensor setup for KEPCO service."""
    # Mock coordinator and device
    mock_coordinator = MagicMock()
    mock_coordinator.data = {
        "usage_info": {"result": {"BILL_LAST_MONTH": "10000"}},
        "recent_usage": {"result": {"F_AP_QT": "123.45"}}
    }

    mock_device = MagicMock()
    mock_device.unique_id = "kepco_test"
    mock_device.device_info = {"name": "test"}

    mock_hass.data[DOMAIN]["test_entry"] = {
        "coordinator": mock_coordinator,
        "device": mock_device
    }

    mock_config_entry.entry_id = "test_entry"
    mock_config_entry.data = {"service": "kepco"}

    # Mock async_add_entities
    mock_async_add_entities = AsyncMock()

    # Test the setup
    await sensor_async_setup_entry(mock_hass, mock_config_entry, mock_async_add_entities)

    # Verify that entities were added
    mock_async_add_entities.assert_called_once()
    entities = mock_async_add_entities.call_args[0][0]

    # Should have 13 KEPCO sensors
    assert len(entities) == 13

    # Check some specific sensors
    sensor_names = [entity._attr_name for entity in entities]
    assert "고객번호" in sensor_names
    assert "전월 요금" in sensor_names
    assert "현재 사용량" in sensor_names


@pytest.mark.asyncio
async def test_sensor_setup_kakaomap(mock_hass, mock_config_entry):
    """Test sensor setup for KakaoMap service."""
    # Mock coordinator and device
    mock_coordinator = MagicMock()
    mock_coordinator.data = {
        "transport_route": {
            "routes": [{"steps": []}],
            "summary": {"recommended_route": {"time": 28}}
        },
        "start_address": {"address": "출발지"},
        "end_address": {"address": "도착지"}
    }

    mock_device = MagicMock()
    mock_device.unique_id = "kakaomap_test"
    mock_device.device_info = {"name": "test"}

    mock_hass.data[DOMAIN]["test_entry"] = {
        "coordinator": mock_coordinator,
        "device": mock_device
    }

    mock_config_entry.entry_id = "test_entry"
    mock_config_entry.data = {"service": "kakaomap"}

    # Mock async_add_entities
    mock_async_add_entities = AsyncMock()

    # Test the setup
    await sensor_async_setup_entry(mock_hass, mock_config_entry, mock_async_add_entities)

    # Verify that entities were added
    mock_async_add_entities.assert_called_once()
    entities = mock_async_add_entities.call_args[0][0]

    # Should have many KakaoMap sensors including the detailed steps
    assert len(entities) > 30  # Including all the detailed step sensors

    # Check some specific sensors
    sensor_names = [entity._attr_name for entity in entities]
    assert "출발지 주소" in sensor_names
    assert "도착지 주소" in sensor_names
    assert "첫번째 경로 1단계 정보" in sensor_names
    assert "첫번째 경로 총 단계수" in sensor_names


@pytest.mark.asyncio
async def test_sensor_setup_gasapp(mock_hass, mock_config_entry):
    """Test sensor setup for GasApp service."""
    mock_coordinator = MagicMock()
    mock_coordinator.data = {
        "current_bill": {
            "history": [{"requestYm": "2025-01", "usageQty": 15}],
            "title1": "가스요금"
        }
    }

    mock_device = MagicMock()
    mock_device.unique_id = "gasapp_test"
    mock_device.device_info = {"name": "test"}

    mock_hass.data[DOMAIN]["test_entry"] = {
        "coordinator": mock_coordinator,
        "device": mock_device
    }

    mock_config_entry.entry_id = "test_entry"
    mock_config_entry.data = {"service": "gasapp"}

    mock_async_add_entities = AsyncMock()

    await sensor_async_setup_entry(mock_hass, mock_config_entry, mock_async_add_entities)

    mock_async_add_entities.assert_called_once()
    entities = mock_async_add_entities.call_args[0][0]

    # Should have 10 GasApp sensors
    assert len(entities) == 10

    sensor_names = [entity._attr_name for entity in entities]
    assert "당월 가스 사용량" in sensor_names
    assert "청구서 제목" in sensor_names


@pytest.mark.asyncio
async def test_sensor_setup_safety_alert(mock_hass, mock_config_entry):
    """Test sensor setup for Safety Alert service."""
    mock_coordinator = MagicMock()
    mock_coordinator.data = {
        "parsed_data": {
            "total_alerts": 5,
            "latest_alert": {"type": "기상특보", "message": "강풍주의보"}
        }
    }

    mock_device = MagicMock()
    mock_device.unique_id = "safety_alert_test"
    mock_device.device_info = {"name": "test"}

    mock_hass.data[DOMAIN]["test_entry"] = {
        "coordinator": mock_coordinator,
        "device": mock_device
    }

    mock_config_entry.entry_id = "test_entry"
    mock_config_entry.data = {"service": "safety_alert"}

    mock_async_add_entities = AsyncMock()

    await sensor_async_setup_entry(mock_hass, mock_config_entry, mock_async_add_entities)

    mock_async_add_entities.assert_called_once()
    entities = mock_async_add_entities.call_args[0][0]

    # Should have 4 Safety Alert sensors
    assert len(entities) == 4

    sensor_names = [entity._attr_name for entity in entities]
    assert "총 안전알림 수" in sensor_names
    assert "최신 알림 유형" in sensor_names


@pytest.mark.asyncio
async def test_sensor_setup_unknown_service(mock_hass, mock_config_entry):
    """Test sensor setup with unknown service should not create entities."""
    mock_hass.data[DOMAIN]["test_entry"] = {
        "coordinator": MagicMock(),
        "device": MagicMock()
    }

    mock_config_entry.entry_id = "test_entry"
    mock_config_entry.data = {"service": "unknown_service"}

    mock_async_add_entities = AsyncMock()

    # Should not raise an error, but also shouldn't create entities
    await sensor_async_setup_entry(mock_hass, mock_config_entry, mock_async_add_entities)

    # async_add_entities should not be called for unknown service
    mock_async_add_entities.assert_not_called()
