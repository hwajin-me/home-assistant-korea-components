import pytest
import aiohttp
from aiohttp_mock import AioHTTPMock
from custom_components.korea_incubator.safety_alert.api import SafetyAlertApiClient
from custom_components.korea_incubator.safety_alert.exceptions import SafetyAlertConnectionError, SafetyAlertDataError


@pytest.fixture
async def api_client():
    async with aiohttp.ClientSession() as session:
        yield SafetyAlertApiClient(session)


@pytest.mark.asyncio
async def test_async_get_safety_alerts_success(api_client, aiohttp_mock: AioHTTPMock):
    expected_response = {
        "disasterSmsList": [
            {
                "DSSTR_SE_NM": "기상특보",
                "MSG_CN": "강풍주의보 발효",
                "CREAT_DT": "2025-01-15 10:00:00",
                "RCV_AREA_NM": "서울특별시",
                "EMRGNCY_STEP_NM": "주의보"
            },
            {
                "DSSTR_SE_NM": "교통통제",
                "MSG_CN": "도로 결빙으로 인한 통행 제한",
                "CREAT_DT": "2025-01-15 09:30:00",
                "RCV_AREA_NM": "서울특별시 강남구",
                "EMRGNCY_STEP_NM": "주의"
            }
        ]
    }

    aiohttp_mock.post("https://www.safekorea.go.kr/idsiSFK/sfk/cs/sua/web/DisasterSmsList.do",
                     status=200, payload=expected_response)

    alerts = await api_client.async_get_safety_alerts("1100000000")

    assert len(alerts) == 2
    assert alerts[0]["DSSTR_SE_NM"] == "기상특보"
    assert alerts[0]["MSG_CN"] == "강풍주의보 발효"
    assert alerts[1]["DSSTR_SE_NM"] == "교통통제"


@pytest.mark.asyncio
async def test_async_get_safety_alerts_empty_response(api_client, aiohttp_mock: AioHTTPMock):
    aiohttp_mock.post("https://www.safekorea.go.kr/idsiSFK/sfk/cs/sua/web/DisasterSmsList.do",
                     status=200, payload={"disasterSmsList": []})

    alerts = await api_client.async_get_safety_alerts("1100000000")

    assert len(alerts) == 0


@pytest.mark.asyncio
async def test_async_get_safety_alerts_http_error(api_client, aiohttp_mock: AioHTTPMock):
    aiohttp_mock.post("https://www.safekorea.go.kr/idsiSFK/sfk/cs/sua/web/DisasterSmsList.do",
                     status=500)

    with pytest.raises(SafetyAlertConnectionError):
        await api_client.async_get_safety_alerts("1100000000")

@pytest.mark.asyncio
async def test_async_get_safety_alerts_with_multiple_area_codes(api_client, aiohttp_mock: AioHTTPMock):
    expected_response = {
        "disasterSmsList": [
            {
                "DSSTR_SE_NM": "기상특보",
                "MSG_CN": "강풍주의보 발효",
                "CREAT_DT": "2025-01-15 10:00:00",
                "RCV_AREA_NM": "서울특별시 강남구",
                "EMRGNCY_STEP_NM": "주의보"
            }
        ]
    }

    aiohttp_mock.post("https://www.safekorea.go.kr/idsiSFK/sfk/cs/sua/web/DisasterSmsList.do",
                     status=200, payload=expected_response)

    alerts = await api_client.async_get_safety_alerts("1100000000", "1168000000", "1168010100")

    assert len(alerts) == 1
    assert alerts[0]["RCV_AREA_NM"] == "서울특별시 강남구"
