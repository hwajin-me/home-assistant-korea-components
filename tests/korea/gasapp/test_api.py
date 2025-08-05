import pytest
import aiohttp
from aiohttp_mock import AioHTTPMock
from custom_components.korea_incubator.gasapp.api import GasAppApiClient
from custom_components.korea_incubator.gasapp.exceptions import GasAppAuthError, GasAppConnectionError


@pytest.fixture
async def api_client():
    async with aiohttp.ClientSession() as session:
        yield GasAppApiClient(session)


@pytest.mark.asyncio
async def test_set_credentials(api_client):
    api_client.set_credentials("test_token", "test_member_id", "test_contract_num")
    assert api_client._token == "test_token"
    assert api_client._member_id == "test_member_id"
    assert api_client._use_contract_num == "test_contract_num"


@pytest.mark.asyncio
async def test_async_validate_credentials_success(api_client, aiohttp_mock: AioHTTPMock):
    api_client.set_credentials("test_token", "test_member_id", "test_contract_num")

    aiohttp_mock.get("https://app.gasapp.co.kr/api/home", status=200, payload={
        "cards": {
            "bill": {
                "title1": "가스요금",
                "history": [
                    {"requestYm": "2025-01", "usageQty": 15, "chargeAmtQty": 25000}
                ]
            }
        }
    })

    result = await api_client.async_validate_credentials()
    assert result is True


@pytest.mark.asyncio
async def test_async_validate_credentials_failure(api_client, aiohttp_mock: AioHTTPMock):
    api_client.set_credentials("invalid_token", "invalid_member", "invalid_contract")

    aiohttp_mock.get("https://app.gasapp.co.kr/api/home", status=401)

    result = await api_client.async_validate_credentials()
    assert result is False


@pytest.mark.asyncio
async def test_async_get_home_data(api_client, aiohttp_mock: AioHTTPMock):
    api_client.set_credentials("test_token", "test_member_id", "test_contract_num")

    expected_response = {
        "cards": {
            "bill": {
                "title1": "가스요금",
                "title2": "총 25,000원",
                "history": [
                    {"requestYm": "2025-01", "usageQty": 15, "chargeAmtQty": 25000}
                ]
            }
        }
    }

    aiohttp_mock.get("https://app.gasapp.co.kr/api/home", status=200, payload=expected_response)

    data = await api_client.async_get_home_data()
    assert data == expected_response
    assert data["cards"]["bill"]["title1"] == "가스요금"


@pytest.mark.asyncio
async def test_async_get_bill_history(api_client, aiohttp_mock: AioHTTPMock):
    api_client.set_credentials("test_token", "test_member_id", "test_contract_num")

    expected_response = {
        "cards": {
            "bill": {
                "history": [
                    {"requestYm": "2025-01", "usageQty": 15, "chargeAmtQty": 25000},
                    {"requestYm": "2024-12", "usageQty": 20, "chargeAmtQty": 30000}
                ]
            }
        }
    }

    aiohttp_mock.get("https://app.gasapp.co.kr/api/home", status=200, payload=expected_response)

    history = await api_client.async_get_bill_history()
    assert len(history) == 2
    assert history[0]["requestYm"] == "2025-01"
    assert history[1]["requestYm"] == "2024-12"


@pytest.mark.asyncio
async def test_async_get_current_bill(api_client, aiohttp_mock: AioHTTPMock):
    api_client.set_credentials("test_token", "test_member_id", "test_contract_num")

    expected_response = {
        "cards": {
            "bill": {
                "title1": "가스요금",
                "title2": "총 25,000원",
                "history": [
                    {"requestYm": "2025-01", "usageQty": 15, "chargeAmtQty": 25000}
                ]
            }
        }
    }

    aiohttp_mock.get("https://app.gasapp.co.kr/api/home", status=200, payload=expected_response)

    bill = await api_client.async_get_current_bill()
    assert bill["title1"] == "가스요금"
    assert bill["title2"] == "총 25,000원"


@pytest.mark.asyncio
async def test_auth_error_without_credentials(api_client):
    with pytest.raises(GasAppAuthError):
        await api_client.async_get_home_data()


@pytest.mark.asyncio
async def test_http_error_handling(api_client, aiohttp_mock: AioHTTPMock):
    api_client.set_credentials("test_token", "test_member_id", "test_contract_num")

    aiohttp_mock.get("https://app.gasapp.co.kr/api/home", status=500)

    with pytest.raises(GasAppConnectionError):
        await api_client.async_get_home_data()
