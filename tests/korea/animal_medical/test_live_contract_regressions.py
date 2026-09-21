"""Contracts observed against real public/Kakao endpoints on 2026-09-21.

Only public business fields are reproduced; never store live credentials.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.korea_incubator.animal_medical.api import (
    AnimalMedicalApiError,
    async_fetch_institutions,
)
from custom_components.korea_incubator.animal_medical.hours import (
    current_state,
    schedule,
)
from custom_components.korea_incubator.pharmacy.api import (
    PharmacyApiError,
    fetch_complete_detail,
)

from .test_api import session_for
from .test_hours import STAMP, day, hours

MODULE = "custom_components.korea_incubator.pharmacy.api"
DETAIL = {
    "hpid": "C1102967",
    "dutyName": "건강약국",
    "dutyAddr": "서울특별시 종로구 혜화로 2, 1층 (혜화동)",
    "dutyTime1s": "0900",
    "dutyTime1c": "1930",
}
LIST_RECORD = {**DETAIL, "dutyEtc": "휴게시간 13:00~14:00", "rnum": "2"}


def test_live_breaktime_label_and_source_disagreement():
    parsed = schedule(
        hours(day(time="09:00 ~ 19:30", breaks=["13:30 ~ 14:00 브레이크타임"])), STAMP
    )
    assert current_state(parsed, STAMP.replace(hour=13, minute=15)) == "open"
    assert current_state(parsed, STAMP.replace(hour=13, minute=30)) == "break"
    assert current_state(parsed, STAMP.replace(hour=14, minute=0)) == "open"


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [200, 503])
async def test_live_json_gateway_timeout_preserves_code_message(status):
    body = {
        "OpenAPI_ServiceResponse": {
            "cmmMsgHeader": {
                "errMsg": "SERVICETIMEOUT_ERROR",
                "returnAuthMsg": "서비스 연결실패 에러 secret",
                "returnReasonCode": "05",
            }
        }
    }
    session, _ = session_for(json.dumps(body), status=status)
    with pytest.raises(AnimalMedicalApiError) as error:
        await async_fetch_institutions(session, "secret", "hospital")
    assert "05" in str(error.value)
    assert "서비스 연결실패" in str(error.value)
    assert "secret" not in str(error.value)
    if status == 503:
        assert "HTTP 503" in str(error.value)


@pytest.mark.asyncio
async def test_merge_fields_omitted_by_real_detail_endpoint():
    with (
        patch(f"{MODULE}.fetch_detail", new_callable=AsyncMock, return_value=DETAIL),
        patch(
            f"{MODULE}.fetch_page",
            new_callable=AsyncMock,
            return_value=([LIST_RECORD], 1),
        ) as fetch,
    ):
        result = await fetch_complete_detail(None, "test-key", "C1102967")
    assert result["dutyEtc"] == "휴게시간 13:00~14:00"
    assert result["dutyTime1c"] == "1930"
    assert fetch.call_args.args[2] == "서울특별시"
    assert fetch.call_args.kwargs["name"] == "건강약국"


@pytest.mark.asyncio
async def test_supplemental_list_paging_and_detail_precedence():
    with (
        patch(
            f"{MODULE}.fetch_detail",
            new_callable=AsyncMock,
            return_value={**DETAIL, "dutyAddr": ""},
        ),
        patch(
            f"{MODULE}.fetch_page",
            new_callable=AsyncMock,
            side_effect=[
                ([{"hpid": "other"}], 101),
                ([{**LIST_RECORD, "dutyTime1c": "1800"}], 101),
            ],
        ) as fetch,
    ):
        result = await fetch_complete_detail(None, "test-key", "C1102967")
    assert result["dutyTime1c"] == "1930"
    assert fetch.call_args.kwargs["page"] == 2
    assert fetch.call_args.args[2] == ""


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "pages",
    [
        [([], 1)],
        [([LIST_RECORD, LIST_RECORD], 2)],
        [([{"hpid": "other"}], 1)],
        [([{"hpid": "other"}], 101), ([{"hpid": "other"}], 101)],
    ],
)
async def test_supplemental_list_never_silently_drops_details(pages):
    with (
        patch(f"{MODULE}.fetch_detail", new_callable=AsyncMock, return_value=DETAIL),
        patch(f"{MODULE}.fetch_page", new_callable=AsyncMock, side_effect=pages),
        pytest.raises(PharmacyApiError),
    ):
        await fetch_complete_detail(None, "test-key", "C1102967")


@pytest.mark.asyncio
async def test_missing_detail_name_does_not_scan_entire_country():
    with (
        patch(
            f"{MODULE}.fetch_detail",
            new_callable=AsyncMock,
            return_value={"hpid": "C1102967"},
        ),
        patch(f"{MODULE}.fetch_page", new_callable=AsyncMock) as fetch,
        pytest.raises(PharmacyApiError),
    ):
        await fetch_complete_detail(None, "test-key", "C1102967")
    fetch.assert_not_awaited()
