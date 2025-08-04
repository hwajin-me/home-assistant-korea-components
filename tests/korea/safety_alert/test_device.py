import pytest
import aiohttp
from unittest.mock import AsyncMock, MagicMock
from custom_components.korea_incubator.safety_alert.device import SafetyAlertDevice
from custom_components.korea_incubator.safety_alert.exceptions import SafetyAlertConnectionError
from homeassistant.helpers.update_coordinator import UpdateFailed


@pytest.fixture
def mock_hass():
    return MagicMock()


@pytest.fixture
async def safety_alert_device(mock_hass):
    session = aiohttp.ClientSession()
    device = SafetyAlertDevice(mock_hass, "test_entry", "1100000000", "서울특별시", "1168000000", "1168010100", session)
    yield device
    await device.async_close_session()


@pytest.mark.asyncio
async def test_device_initialization(safety_alert_device):
    assert safety_alert_device.unique_id == "safety_alert_1100000000"
    assert safety_alert_device._name == "안전알림 (서울특별시)"
    assert safety_alert_device.available is True


@pytest.mark.asyncio
async def test_async_update_success(safety_alert_device):
    # Mock API responses
    mock_alerts = [
        {
            "DSSTR_SE_NM": "기상특보",
            "MSG_CN": "강풍주의보 발효",
            "CREAT_DT": "2025-01-15 10:00:00",
            "RCV_AREA_NM": "서울특별시",
            "EMRGNCY_STEP_NM": "주의보"
        }
    ]

    safety_alert_device.api_client.async_get_safety_alerts = AsyncMock(return_value=mock_alerts)
    await safety_alert_device.async_update()

    assert safety_alert_device.available is True
    assert safety_alert_device.data["raw_alerts"] == mock_alerts
    assert safety_alert_device.data["parsed_data"]["total_alerts"] == 1


@pytest.mark.asyncio
async def test_async_update_connection_error(safety_alert_device):
    # Mock connection error
    safety_alert_device.api_client.async_get_safety_alerts = AsyncMock(
        side_effect=SafetyAlertConnectionError("Connection failed")
    )

    with pytest.raises(UpdateFailed):
        await safety_alert_device.async_update()

    assert safety_alert_device.available is False


@pytest.mark.asyncio
async def test_device_info(safety_alert_device):
    device_info = safety_alert_device.device_info
    assert device_info["name"] == "안전알림 (서울특별시)"
    assert device_info["manufacturer"] == "행정안전부"
    assert device_info["model"] == "안전알림서비스"

