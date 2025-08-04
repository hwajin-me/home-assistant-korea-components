import pytest
import aiohttp
from aiohttp_mock import AioHTTPMock
from custom_components.korea_incubator.goodsflow.api import GoodsFlowApiClient
from custom_components.korea_incubator.goodsflow.exceptions import GoodsFlowAuthError, GoodsFlowConnectionError


@pytest.fixture
async def api_client():
    async with aiohttp.ClientSession() as session:
        yield GoodsFlowApiClient(session)


@pytest.mark.asyncio
async def test_set_token(api_client):
    api_client.set_token("test_token_123")
    assert api_client._token == "test_token_123"


@pytest.mark.asyncio
async def test_async_validate_token_success(api_client, aiohttp_mock: AioHTTPMock):
    api_client.set_token("valid_token")

    aiohttp_mock.get("https://ptk.goodsflow.com/ptk/rest/trans/trace/list/v3", status=200, payload={
        "success": True,
        "data": {
            "transList": {
                "totalCount": 5,
                "rows": []
            }
        }
    })

    result = await api_client.async_validate_token()
    assert result is True


@pytest.mark.asyncio
async def test_async_validate_token_failure(api_client, aiohttp_mock: AioHTTPMock):
    api_client.set_token("invalid_token")

    aiohttp_mock.get("https://ptk.goodsflow.com/ptk/rest/trans/trace/list/v3", status=401)

    result = await api_client.async_validate_token()
    assert result is False


@pytest.mark.asyncio
async def test_async_get_tracking_list_success(api_client, aiohttp_mock: AioHTTPMock):
    api_client.set_token("test_token")

    expected_response = {
        "success": True,
        "data": {
            "transList": {
                "totalCount": 3,
                "rows": [
                    {
                        "transId": "123456789",
                        "companyName": "CJ대한통운",
                        "status": "배송중",
                        "recipientName": "홍길동"
                    },
                    {
                        "transId": "987654321",
                        "companyName": "한진택배",
                        "status": "배송완료",
                        "recipientName": "김철수"
                    }
                ]
            }
        }
    }

    aiohttp_mock.get("https://ptk.goodsflow.com/ptk/rest/trans/trace/list/v3",
                     status=200, payload=expected_response)

    result = await api_client.async_get_tracking_list()

    assert result == expected_response
    assert result["data"]["transList"]["totalCount"] == 3
    assert len(result["data"]["transList"]["rows"]) == 2


@pytest.mark.asyncio
async def test_async_get_tracking_list_with_params(api_client, aiohttp_mock: AioHTTPMock):
    api_client.set_token("test_token")

    expected_response = {
        "success": True,
        "data": {
            "transList": {
                "totalCount": 1,
                "rows": []
            }
        }
    }

    aiohttp_mock.get("https://ptk.goodsflow.com/ptk/rest/trans/trace/list/v3",
                     status=200, payload=expected_response)

    result = await api_client.async_get_tracking_list(limit=5, start=10, type_filter="DELIVERED")

    assert result == expected_response


@pytest.mark.asyncio
async def test_async_get_tracking_list_auth_error(api_client, aiohttp_mock: AioHTTPMock):
    api_client.set_token("invalid_token")

    aiohttp_mock.get("https://ptk.goodsflow.com/ptk/rest/trans/trace/list/v3", status=401)

    with pytest.raises(GoodsFlowAuthError):
        await api_client.async_get_tracking_list()


@pytest.mark.asyncio
async def test_async_get_tracking_list_connection_error(api_client, aiohttp_mock: AioHTTPMock):
    api_client.set_token("test_token")

    aiohttp_mock.get("https://ptk.goodsflow.com/ptk/rest/trans/trace/list/v3", status=500)

    with pytest.raises(GoodsFlowConnectionError):
        await api_client.async_get_tracking_list()


@pytest.mark.asyncio
async def test_parse_tracking_data_success(api_client):
    data = {
        "success": True,
        "data": {
            "transList": {
                "totalCount": 5,
                "rows": [
                    {"status": "배송중"},
                    {"status": "배송완료"},
                    {"status": "상품준비중"},
                    {"status": "배송완료"},
                    {"status": "배송중"}
                ]
            }
        }
    }

    result = api_client.parse_tracking_data(data)

    assert result["total_packages"] == 5
    assert result["active_packages"] == 3  # 배송중 + 상품준비중
    assert result["delivered_packages"] == 2  # 배송완료
    assert len(result["packages"]) == 5


@pytest.mark.asyncio
async def test_parse_tracking_data_no_success(api_client):
    data = {"success": False}

    result = api_client.parse_tracking_data(data)

    assert result["total_packages"] == 0
    assert result["active_packages"] == 0
    assert result["delivered_packages"] == 0
    assert result["packages"] == []


@pytest.mark.asyncio
async def test_parse_tracking_data_empty(api_client):
    result = api_client.parse_tracking_data({})

    assert result["total_packages"] == 0
    assert result["active_packages"] == 0
    assert result["delivered_packages"] == 0
    assert result["packages"] == []


@pytest.mark.asyncio
async def test_auth_error_without_token(api_client):
    with pytest.raises(GoodsFlowAuthError):
        await api_client.async_get_tracking_list()
