import pytest
import aiohttp
from unittest.mock import AsyncMock, MagicMock
from custom_components.korea_incubator.arisu.device import ArisuDevice
from custom_components.korea_incubator.arisu.exceptions import ArisuAuthError
from homeassistant.helpers.update_coordinator import UpdateFailed


@pytest.fixture
def mock_hass():
    return MagicMock()


@pytest.fixture
async def arisu_device(mock_hass):
    session = aiohttp.ClientSession()
    device = ArisuDevice(mock_hass, "test_entry", "042389659", "홍길동", session)
    yield device
    await device.async_close_session()


@pytest.mark.asyncio
async def test_device_initialization(arisu_device):
    assert arisu_device.unique_id == "arisu_042389659"
    assert arisu_device._name == "아리수 (042389659)"
    assert arisu_device.available is True


@pytest.mark.asyncio
async def test_async_update_success(arisu_device):
    # Mock API response
    mock_bill_data = {
        "success": True,
        "total_amount": 25000,
        "customer_info": {
            "customer_number": "042389659",
            "address": "서울특별시 강남구",
            "payment_method": "계좌이체"
        },
        "usage_info": {
            "current_usage": 15
        },
        "arrears_info": {
            "overdue_amount": 0
        },
        "billing_month": "2025-01"
    }

    arisu_device.api_client.async_get_water_bill_data = AsyncMock(return_value=mock_bill_data)

    await arisu_device.async_update()

    assert arisu_device.available is True
    assert arisu_device.data["bill_data"]["total_amount"] == 25000
    assert arisu_device.data["bill_data"]["billing_month"] == "2025-01"


@pytest.mark.asyncio
async def test_async_update_auth_error(arisu_device):
    # Mock authentication error
    arisu_device.api_client.async_get_water_bill_data = AsyncMock(
        side_effect=ArisuAuthError("Auth failed")
    )

    with pytest.raises(UpdateFailed):
        await arisu_device.async_update()

    assert arisu_device.available is False


@pytest.mark.asyncio
async def test_async_update_no_success(arisu_device):
    # Mock API response with no success
    mock_bill_data = {
        "success": False,
        "error": "No data found"
    }

    arisu_device.api_client.async_get_water_bill_data = AsyncMock(return_value=mock_bill_data)

    with pytest.raises(UpdateFailed):
        await arisu_device.async_update()

    assert arisu_device.available is False


@pytest.mark.asyncio
async def test_device_info(arisu_device):
    device_info = arisu_device.device_info
    assert device_info["name"] == "아리수 (042389659)"
    assert device_info["manufacturer"] == "서울시"
    assert device_info["model"] == "아리수 상수도 고객센터"


@pytest.mark.asyncio
async def test_get_total_amount(arisu_device):
    arisu_device.data = {
        "bill_data": {"total_amount": 25000}
    }

    amount = arisu_device.get_total_amount()
    assert amount == 25000


@pytest.mark.asyncio
async def test_get_current_usage(arisu_device):
    arisu_device.data = {
        "bill_data": {
            "usage_info": {"current_usage": 15}
        }
    }

    usage = arisu_device.get_current_usage()
    assert usage == 15


@pytest.mark.asyncio
async def test_get_customer_address(arisu_device):
    arisu_device.data = {
        "bill_data": {
            "customer_info": {"address": "서울특별시 강남구"}
        }
    }

    address = arisu_device.get_customer_address()
    assert address == "서울특별시 강남구"


@pytest.mark.asyncio
async def test_get_payment_method(arisu_device):
    arisu_device.data = {
        "bill_data": {
            "customer_info": {"payment_method": "계좌이체"}
        }
    }

    method = arisu_device.get_payment_method()
    assert method == "계좌이체"


@pytest.mark.asyncio
async def test_get_overdue_amount(arisu_device):
    arisu_device.data = {
        "bill_data": {
            "arrears_info": {"overdue_amount": 5000}
        }
    }

    overdue = arisu_device.get_overdue_amount()
    assert overdue == 5000


@pytest.mark.asyncio
async def test_get_billing_month(arisu_device):
    arisu_device.data = {
        "bill_data": {"billing_month": "2025-01"}
    }

    month = arisu_device.get_billing_month()
    assert month == "2025-01"


@pytest.mark.asyncio
async def test_get_methods_no_data(arisu_device):
    # Test methods when no data is available
    assert arisu_device.get_total_amount() == 0
    assert arisu_device.get_current_usage() is None
    assert arisu_device.get_customer_address() is None
    assert arisu_device.get_payment_method() is None
    assert arisu_device.get_overdue_amount() == 0
    assert arisu_device.get_billing_month() is None
