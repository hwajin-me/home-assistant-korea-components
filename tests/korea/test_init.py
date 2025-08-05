import pytest
from homeassistant.setup import async_setup_component
from homeassistant.const import Platform

from custom_components.korea_incubator.const import DOMAIN


@pytest.fixture(autouse=True)
def platforms_fixture():
    """Fixture to set up platforms for testing."""
    yield


@pytest.mark.asyncio
async def test_setup_entry_kepco_success(hass, aiohttp_mock):
    # Mock KEPCO API calls
    aiohttp_mock.get("https://pp.kepco.co.kr:8030/intro.do", status=200, headers={
        "Set-Cookie": "JSESSIONID=test_jsessionid; Path=/; HttpOnly, cookieRsa=test_cookie_rsa; Path=/; HttpOnly"
    }, payload="<input type=\"hidden\" id=\"RSAExponent\" value=\"10001\">")
    aiohttp_mock.post("https://pp.kepco.co.kr:8030/login", status=200, payload="로그아웃")
    aiohttp_mock.post("https://pp.kepco.co.kr:8030/low/main/recent_usage.do", status=200, payload={"result": {"F_AP_QT": "123.45", "KWH_BILL": "678"}})
    aiohttp_mock.post("https://pp.kepco.co.kr:8030/low/main/usage_info.do", status=200, payload={"result": {"BILL_LAST_MONTH": "10000", "PREDICT_TOTAL_CHARGE_REV": "15000"}})

    # Setup the config entry
    config_entry = {
        "entry_id": "test_kepco_entry",
        "domain": DOMAIN,
        "data": {
            "service": "kepco",
            "username": "test_user",
            "password": "test_password",
        },
        "title": "한국전력 (test_user)",
    }
    hass.config_entries.async_queue_entry(config_entry)

    # Load the integration
    assert await async_setup_component(hass, DOMAIN, {DOMAIN: {}})
    await hass.async_block_till_done()

    # Verify that sensors are created
    assert hass.states.get("sensor.한국전력_최근_사용량") is not None
    assert hass.states.get("sensor.한국전력_당월_예측_사용량") is not None
    assert hass.states.get("sensor.한국전력_전월_요금") is not None
    assert hass.states.get("sensor.한국전력_당월_예상_요금") is not None

    # Verify sensor states
    assert hass.states.get("sensor.한국전력_최근_사용량").state == "123.45"
    assert hass.states.get("sensor.한국전력_당월_예측_사용량").state == "678"
    assert hass.states.get("sensor.한국전력_전월_요금").state == "10000"
    assert hass.states.get("sensor.한국전력_당월_예상_요금").state == "15000"


@pytest.mark.asyncio
async def test_setup_entry_kepco_login_failure(hass, aiohttp_mock):
    # Mock KEPCO API calls for login failure
    aiohttp_mock.get("https://pp.kepco.co.kr:8030/intro.do", status=200, headers={
        "Set-Cookie": "JSESSIONID=test_jsessionid; Path=/; HttpOnly, cookieRsa=test_cookie_rsa; Path=/; HttpOnly"
    }, payload="<input type=\"hidden\" id=\"RSAExponent\" value=\"10001\">")
    aiohttp_mock.post("https://pp.kepco.co.kr:8030/login", status=200, payload="로그인 실패")

    # Setup the config entry
    config_entry = {
        "entry_id": "test_kepco_entry_fail",
        "domain": DOMAIN,
        "data": {
            "service": "kepco",
            "username": "wrong_user",
            "password": "wrong_password",
        },
        "title": "한국전력 (wrong_user)",
    }
    hass.config_entries.async_queue_entry(config_entry)

    # Load the integration (should fail to set up)
    assert not await async_setup_component(hass, DOMAIN, {DOMAIN: {}})
    await hass.async_block_till_done()

    # Verify that no sensors are created
    assert hass.states.get("sensor.한국전력_최근_사용량") is None


@pytest.mark.asyncio
async def test_unload_entry(hass, aiohttp_mock):
    # Mock KEPCO API calls for successful setup
    aiohttp_mock.get("https://pp.kepco.co.kr:8030/intro.do", status=200, headers={
        "Set-Cookie": "JSESSIONID=test_jsessionid; Path=/; HttpOnly, cookieRsa=test_cookie_rsa; Path=/; HttpOnly"
    }, payload="<input type=\"hidden\" id=\"RSAExponent\" value=\"10001\">")
    aiohttp_mock.post("https://pp.kepco.co.kr:8030/login", status=200, payload="로그아웃")
    aiohttp_mock.post("https://pp.kepco.co.kr:8030/low/main/recent_usage.do", status=200, payload={"result": {"F_AP_QT": "123.45", "KWH_BILL": "678"}})
    aiohttp_mock.post("https://pp.kepco.co.kr:8030/low/main/usage_info.do", status=200, payload={"result": {"BILL_LAST_MONTH": "10000", "PREDICT_TOTAL_CHARGE_REV": "15000"}})

    # Setup the config entry
    config_entry = {
        "entry_id": "test_unload_entry",
        "domain": DOMAIN,
        "data": {
            "service": "kepco",
            "username": "test_user",
            "password": "test_password",
        },
        "title": "한국전력 (test_user)",
    }
    hass.config_entries.async_queue_entry(config_entry)

    # Load the integration
    assert await async_setup_component(hass, DOMAIN, {DOMAIN: {}})
    await hass.async_block_till_done()

    # Verify that sensors are created
    assert hass.states.get("sensor.한국전력_최근_사용량") is not None

    # Unload the integration
    assert await hass.config_entries.async_unload(config_entry["entry_id"])
    await hass.async_block_till_done()

    # Verify that sensors are removed
    assert hass.states.get("sensor.한국전력_최근_사용량") is None
