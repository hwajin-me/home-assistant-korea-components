import pytest
import aiohttp
from unittest.mock import AsyncMock, MagicMock
from custom_components.korea_incubator.gasapp.device import GasAppDevice
from custom_components.korea_incubator.gasapp.exceptions import GasAppAuthError
from homeassistant.helpers.update_coordinator import UpdateFailed


@pytest.fixture
def mock_hass():
    return MagicMock()


@pytest.fixture
async def gasapp_device(mock_hass):
    session = aiohttp.ClientSession()
    device = GasAppDevice(mock_hass, "test_entry", "test_token", "test_member_id", "test_contract_num", session)
    yield device
    await device.async_close_session()


@pytest.mark.asyncio
async def test_device_initialization(gasapp_device):
    assert gasapp_device.unique_id == "gasapp_test_contract_num"
    assert gasapp_device._name == "가스앱 (test_contract_num)"
    assert gasapp_device.available is True


@pytest.mark.asyncio
async def test_async_update_success(gasapp_device):
    # Mock API responses
    gasapp_device.api_client.async_get_home_data = AsyncMock(return_value={
        "cards": {"bill": {"title1": "가스요금"}}
    })
    gasapp_device.api_client.async_get_bill_history = AsyncMock(return_value=[
        {"requestYm": "2025-01", "usageQty": 15, "chargeAmtQty": 25000}
    ])
    gasapp_device.api_client.async_get_current_bill = AsyncMock(return_value={
        "title1": "가스요금",
        "history": [{"requestYm": "2025-01", "usageQty": 15, "chargeAmtQty": 25000}]
    })

    await gasapp_device.async_update()

    assert gasapp_device.available is True
    assert gasapp_device.data["current_bill"]["title1"] == "가스요금"


@pytest.mark.asyncio
async def test_async_update_auth_error(gasapp_device):
    # Mock authentication error
    gasapp_device.api_client.async_get_home_data = AsyncMock(side_effect=GasAppAuthError("Auth failed"))

    with pytest.raises(UpdateFailed):
        await gasapp_device.async_update()

    assert gasapp_device.available is False


@pytest.mark.asyncio
async def test_device_info(gasapp_device):
    device_info = gasapp_device.device_info
    assert device_info["name"] == "가스앱 (test_contract_num)"
    assert device_info["manufacturer"] == "한국가스공사"
    assert device_info["model"] == "가스앱"


@pytest.mark.asyncio
async def test_get_current_month_usage(gasapp_device):
    gasapp_device.data = {
        "current_bill": {
            "history": [{"usageQty": 15}]
        }
    }

    usage = gasapp_device.get_current_month_usage()
    assert usage == 15


@pytest.mark.asyncio
async def test_get_current_month_charge(gasapp_device):
    gasapp_device.data = {
        "current_bill": {
            "history": [{"chargeAmtQty": 25000}]
        }
    }

    charge = gasapp_device.get_current_month_charge()
    assert charge == 25000


@pytest.mark.asyncio
async def test_get_bill_title(gasapp_device):
    gasapp_device.data = {
        "current_bill": {"title1": "가스요금"}
    }

    title = gasapp_device.get_bill_title()
    assert title == "가스요금"


@pytest.mark.asyncio
async def test_get_methods_no_data(gasapp_device):
    # Test methods when no data is available
    assert gasapp_device.get_current_month_usage() is None
    assert gasapp_device.get_current_month_charge() is None
    assert gasapp_device.get_bill_title() is None
