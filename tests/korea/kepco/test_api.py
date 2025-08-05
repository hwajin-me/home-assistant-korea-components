import pytest
import aiohttp
from aiohttp_mock import AioHTTPMock
from custom_components.korea_incubator.kepco.api import KepcoApiClient
from custom_components.korea_incubator.kepco.exceptions import KepcoAuthError, KepcoConnectionError

@pytest.fixture
async def api_client():
    async with aiohttp.ClientSession() as session:
        yield KepcoApiClient(session)

@pytest.mark.asyncio
async def test_async_get_session_and_rsa_key(api_client, aiohttp_mock: AioHTTPMock):
    aiohttp_mock.get("https://pp.kepco.co.kr:8030/intro.do", status=200, headers={
        "Set-Cookie": "JSESSIONID=test_jsessionid; Path=/; HttpOnly, cookieRsa=test_cookie_rsa; Path=/; HttpOnly"
    }, payload="<input type=\"hidden\" id=\"RSAExponent\" value=\"10001\">")

    jsessionid, cookie_rsa, rsa_exponent = await api_client.async_get_session_and_rsa_key()

    assert jsessionid == "test_jsessionid"
    assert cookie_rsa == "test_cookie_rsa"
    assert rsa_exponent == "10001"

@pytest.mark.asyncio
async def test_async_login_success(api_client, aiohttp_mock: AioHTTPMock):
    aiohttp_mock.get("https://pp.kepco.co.kr:8030/intro.do", status=200, headers={
        "Set-Cookie": "JSESSIONID=test_jsessionid; Path=/; HttpOnly, cookieRsa=test_cookie_rsa; Path=/; HttpOnly"
    }, payload="<input type=\"hidden\" id=\"RSAExponent\" value=\"10001\">")
    aiohttp_mock.post("https://pp.kepco.co.kr:8030/login", status=200, payload="로그아웃")

    result = await api_client.async_login("test_user", "test_password")
    assert result is True

@pytest.mark.asyncio
async def test_async_login_failure(api_client, aiohttp_mock: AioHTTPMock):
    aiohttp_mock.get("https://pp.kepco.co.kr:8030/intro.do", status=200, headers={
        "Set-Cookie": "JSESSIONID=test_jsessionid; Path=/; HttpOnly, cookieRsa=test_cookie_rsa; Path=/; HttpOnly"
    }, payload="<input type=\"hidden\" id=\"RSAExponent\" value=\"10001\">")
    aiohttp_mock.post("https://pp.kepco.co.kr:8030/login", status=200, payload="로그인 실패")

    result = await api_client.async_login("test_user", "test_password")
    assert result is False

@pytest.mark.asyncio
async def test_async_login_http_error(api_client, aiohttp_mock: AioHTTPMock):
    aiohttp_mock.get("https://pp.kepco.co.kr:8030/intro.do", status=500)

    with pytest.raises(KepcoConnectionError):
        await api_client.async_login("test_user", "test_password")

@pytest.mark.asyncio
async def test_async_get_recent_usage(api_client, aiohttp_mock: AioHTTPMock):
    aiohttp_mock.post("https://pp.kepco.co.kr:8030/low/main/recent_usage.do", status=200, payload={"result": {"F_AP_QT": "123.45", "KWH_BILL": "678"}})

    data = await api_client.async_get_recent_usage()
    assert data["result"]["F_AP_QT"] == "123.45"
    assert data["result"]["KWH_BILL"] == "678"

@pytest.mark.asyncio
async def test_async_get_usage_info(api_client, aiohttp_mock: AioHTTPMock):
    aiohttp_mock.post("https://pp.kepco.co.kr:8030/low/main/usage_info.do", status=200, payload={"result": {"BILL_LAST_MONTH": "10000", "PREDICT_TOTAL_CHARGE_REV": "15000"}})

    data = await api_client.async_get_usage_info()
    assert data["result"]["BILL_LAST_MONTH"] == "10000"
    assert data["result"]["PREDICT_TOTAL_CHARGE_REV"] == "15000"

@pytest.mark.asyncio
async def test_async_get_usage_info_unauthorized(api_client, aiohttp_mock: AioHTTPMock):
    aiohttp_mock.post("https://pp.kepco.co.kr:8030/low/main/usage_info.do", status=401)

    with pytest.raises(KepcoAuthError):
        await api_client.async_get_usage_info()

@pytest.mark.asyncio
async def test_set_credentials(api_client):
    api_client.set_credentials("test_user", "test_password")
    assert api_client._username == "test_user"
    assert api_client._password == "test_password"
