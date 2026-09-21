"""Safety Alert HTML endpoint tests with the actual curl_cffi transport mocked."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.korea_incubator.safety_alert.api import SafetyAlertApiClient
from custom_components.korea_incubator.safety_alert.exceptions import (
    SafetyAlertConnectionError,
    SafetyAlertDataError,
)

HTML = """<div class="board-count"><span>1,002</span></div>
<div class="board-listarea"><table><tbody>
<tr><td>호우</td><td><a>안전한 장소로 이동하세요</a><p>발송일시 : 2026/09/21 12:30:00 ㆍ 긴급단계 : 관심 ㆍ 송출지역 : 서울특별시</p></td></tr>
<tr><td>폭염</td><td><a>물을 마시세요</a><p>발송일시 : 2026/09/21 13:00:00 ㆍ 긴급단계 : 안전안내 ㆍ 송출지역 : 경기도</p></td></tr>
</tbody></table></div>"""
EMPTY_HTML = '<div class="board-count"><span>0</span></div><div class="board-listarea"><table><tbody><tr><td colspan="2">등록된 자료가 없습니다</td></tr></tbody></table></div>'


@pytest.fixture
def transport():
    session = MagicMock()
    session.get = AsyncMock(return_value=MagicMock(status_code=200, text=HTML))
    with patch(
        "custom_components.korea_incubator.safety_alert.api.curl_cffi.AsyncSession"
    ) as factory:
        factory.return_value.__aenter__ = AsyncMock(return_value=session)
        factory.return_value.__aexit__ = AsyncMock(return_value=False)
        yield session
        factory.return_value.__aexit__.assert_awaited_once()


async def test_get_safety_alerts_success(transport):
    result = await SafetyAlertApiClient().async_get_safety_alerts()
    assert len(result["disasterSmsList"]) == 2
    assert result["rtnResult"]["totCnt"] == 1002
    assert result["disasterSmsList"][0] == {
        "DSSTR_SE_NM": "호우",
        "EMRGNCY_STEP_NM": "관심",
        "MSG_CN": "안전한 장소로 이동하세요",
        "RCV_AREA_NM": "서울특별시",
        "REGIST_DT": "2026/09/21 12:30:00",
    }


@pytest.mark.parametrize(
    "codes",
    [
        ("1100000000", None, None),
        ("1100000000", "1111000000", None),
        ("1100000000", "1111000000", "1111010100"),
        ("", None, None),
    ],
)
async def test_area_parameters(transport, codes):
    await SafetyAlertApiClient().async_get_safety_alerts(*codes)
    params = transport.get.call_args.kwargs["params"]
    assert [params[key] for key in ("sbLawArea1", "sbLawArea2", "sbLawArea3")] == [
        code or "" for code in codes
    ]
    assert params["startDate"] <= params["endDate"]


@pytest.mark.parametrize("status", [403, 500])
async def test_http_failure(transport, status):
    transport.get.return_value.status_code = status
    with pytest.raises(SafetyAlertConnectionError, match=str(status)):
        await SafetyAlertApiClient().async_get_safety_alerts()


async def test_connection_failure(transport):
    transport.get.side_effect = TimeoutError("timeout")
    with pytest.raises(SafetyAlertConnectionError):
        await SafetyAlertApiClient().async_get_safety_alerts()


async def test_empty_response(transport):
    transport.get.return_value.text = EMPTY_HTML
    assert await SafetyAlertApiClient().async_get_safety_alerts() == {
        "disasterSmsList": [],
        "rtnResult": {"totCnt": 0},
    }


@pytest.mark.parametrize(
    "html",
    [
        "",
        "<html>Maintenance</html>",
        '<div class="board-count"><span>invalid</span></div>',
    ],
)
async def test_invalid_html_is_data_error(transport, html):
    transport.get.return_value.text = html
    with pytest.raises(SafetyAlertDataError):
        await SafetyAlertApiClient().async_get_safety_alerts()


@pytest.mark.integration
async def test_real_api_connection():
    result = await SafetyAlertApiClient().async_get_safety_alerts()
    assert isinstance(result["disasterSmsList"], list)


@pytest.mark.integration
@pytest.mark.parametrize("area", ["2600000000", "4100000000"])
async def test_real_regions(area):
    result = await SafetyAlertApiClient().async_get_safety_alerts(area)
    assert "rtnResult" in result
