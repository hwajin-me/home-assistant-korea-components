import pytest
import aiohttp
from unittest.mock import AsyncMock, MagicMock
from custom_components.korea_incubator.kepco.device import KepcoDevice
from custom_components.korea_incubator.kepco.exceptions import KepcoAuthError
from homeassistant.helpers.update_coordinator import UpdateFailed


@pytest.fixture
def mock_hass():
    return MagicMock()


@pytest.fixture
async def kepco_device(mock_hass):
    session = aiohttp.ClientSession()
    device = KepcoDevice(mock_hass, "test_entry", "test_user", "test_password", session)
    yield device
    await device.async_close_session()


@pytest.mark.asyncio
async def test_device_initialization(kepco_device):
    assert kepco_device.unique_id == "kepco_test_user"
    assert kepco_device._name == "한전 (test_user)"
    assert kepco_device.available is True


@pytest.mark.asyncio
async def test_async_update_success(kepco_device):
    # Mock API responses
    kepco_device.api_client.async_get_recent_usage = AsyncMock(return_value={
        "result": {"F_AP_QT": "123.45", "ST_TIME": "2025-01-01"}
    })
    kepco_device.api_client.async_get_usage_info = AsyncMock(return_value={
        "result": {"BILL_LAST_MONTH": "10000", "PREDICT_TOTAL_CHARGE_REV": "15000"}
    })

    await kepco_device.async_update()

    assert kepco_device.available is True
    assert kepco_device.data["recent_usage"]["result"]["F_AP_QT"] == "123.45"
    assert kepco_device.data["usage_info"]["result"]["BILL_LAST_MONTH"] == "10000"


@pytest.mark.asyncio
async def test_async_update_auth_error(kepco_device):
    # Mock authentication error
    kepco_device.api_client.async_get_recent_usage = AsyncMock(side_effect=KepcoAuthError("Auth failed"))

    with pytest.raises(UpdateFailed):
        await kepco_device.async_update()

    assert kepco_device.available is False


@pytest.mark.asyncio
async def test_device_info(kepco_device):
    device_info = kepco_device.device_info
    assert device_info["name"] == "한전 (test_user)"
    assert device_info["manufacturer"] == "한국전력공사"
    assert device_info["model"] == "사이버지점"


@pytest.mark.asyncio
async def test_get_current_usage(kepco_device):
    kepco_device.data = {
        "recent_usage": {"result": {"F_AP_QT": "123.45"}}
    }

    usage = kepco_device.get_current_usage()
    assert usage == "123.45"


@pytest.mark.asyncio
async def test_get_current_usage_no_data(kepco_device):
    usage = kepco_device.get_current_usage()
    assert usage is None


@pytest.mark.asyncio
async def test_get_last_month_bill(kepco_device):
    kepco_device.data = {
        "usage_info": {"result": {"BILL_LAST_MONTH": "10000"}}
    }

    bill = kepco_device.get_last_month_bill()
    assert bill == "10000"
