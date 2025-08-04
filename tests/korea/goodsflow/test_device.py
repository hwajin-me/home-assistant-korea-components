import pytest
import aiohttp
from unittest.mock import AsyncMock, MagicMock
from custom_components.korea_incubator.goodsflow.device import GoodsFlowDevice
from custom_components.korea_incubator.goodsflow.exceptions import GoodsFlowAuthError
from homeassistant.helpers.update_coordinator import UpdateFailed


@pytest.fixture
def mock_hass():
    return MagicMock()


@pytest.fixture
async def goodsflow_device(mock_hass):
    session = aiohttp.ClientSession()
    device = GoodsFlowDevice(mock_hass, "test_entry", "test_token_123", session)
    yield device
    await device.async_close_session()


@pytest.mark.asyncio
async def test_device_initialization(goodsflow_device):
    assert goodsflow_device.unique_id == "goodsflow_test_tok"  # first 8 chars
    assert goodsflow_device._name == "굿스플로우 택배조회"
    assert goodsflow_device.available is True


@pytest.mark.asyncio
async def test_async_update_success(goodsflow_device):
    # Mock API responses
    mock_tracking_data = {
        "success": True,
        "data": {
            "transList": {
                "totalCount": 5,
                "rows": [
                    {"status": "배송중"},
                    {"status": "배송완료"},
                    {"status": "상품준비중"}
                ]
            }
        }
    }

    mock_parsed_data = {
        "total_packages": 5,
        "active_packages": 2,
        "delivered_packages": 1,
        "packages": [
            {"status": "배송중"},
            {"status": "배송완료"},
            {"status": "상품준비중"}
        ]
    }

    goodsflow_device.api_client.async_get_tracking_list = AsyncMock(return_value=mock_tracking_data)
    goodsflow_device.api_client.parse_tracking_data = MagicMock(return_value=mock_parsed_data)

    await goodsflow_device.async_update()

    assert goodsflow_device.available is True
    assert goodsflow_device.data["raw_data"] == mock_tracking_data
    assert goodsflow_device.data["parsed_data"]["total_packages"] == 5


@pytest.mark.asyncio
async def test_async_update_auth_error(goodsflow_device):
    # Mock authentication error
    goodsflow_device.api_client.async_get_tracking_list = AsyncMock(
        side_effect=GoodsFlowAuthError("Auth failed")
    )

    with pytest.raises(UpdateFailed):
        await goodsflow_device.async_update()

    assert goodsflow_device.available is False


@pytest.mark.asyncio
async def test_device_info(goodsflow_device):
    device_info = goodsflow_device.device_info
    assert device_info["name"] == "굿스플로우 택배조회"
    assert device_info["manufacturer"] == "굿스플로우"
    assert device_info["model"] == "택배조회"


@pytest.mark.asyncio
async def test_get_total_packages(goodsflow_device):
    goodsflow_device.data = {
        "parsed_data": {"total_packages": 10}
    }

    total = goodsflow_device.get_total_packages()
    assert total == 10


@pytest.mark.asyncio
async def test_get_active_packages(goodsflow_device):
    goodsflow_device.data = {
        "parsed_data": {"active_packages": 3}
    }

    active = goodsflow_device.get_active_packages()
    assert active == 3


@pytest.mark.asyncio
async def test_get_delivered_packages(goodsflow_device):
    goodsflow_device.data = {
        "parsed_data": {"delivered_packages": 7}
    }

    delivered = goodsflow_device.get_delivered_packages()
    assert delivered == 7


@pytest.mark.asyncio
async def test_get_methods_no_data(goodsflow_device):
    # Test methods when no data is available
    assert goodsflow_device.get_total_packages() == 0
    assert goodsflow_device.get_active_packages() == 0
    assert goodsflow_device.get_delivered_packages() == 0
