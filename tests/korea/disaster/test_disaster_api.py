"""Tests for disaster API response handling."""

from datetime import datetime
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest

from custom_components.korea_incubator.disaster.api import (
    DisasterApiError,
    DisasterDailyLimitError,
    _daily_limit_blocked_until,
    _parse_payload,
    fetch_disaster_messages,
    validate_disaster_api,
)


@pytest.fixture(autouse=True)
def clear_daily_limit_blocks():
    _daily_limit_blocked_until.clear()
    yield
    _daily_limit_blocked_until.clear()


def test_parse_json_messages():
    payload = """{
        "header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE"},
        "body": [{
            "MSG_CN": "테스트 재난문자",
            "RCPTN_RGN_NM": "서울 용산구",
            "CRT_DT": "2026-08-24 12:00:00",
            "EMRG_STEP_NM": "안전안내",
            "DST_SE_NM": "기타"
        }]
    }"""

    assert _parse_payload(payload) == [
        {
            "message": "테스트 재난문자",
            "area": "서울 용산구",
            "create_date": "2026-08-24 12:00:00",
            "level": "안전안내",
            "disaster_type": "기타",
        }
    ]


def test_parse_expired_key_error():
    payload = """{
        "header": {
            "resultMsg": "DEADLINE HAS EXPIRED ERROR",
            "resultCode": "31",
            "errorMsg": "기한만료된 서비스키"
        },
        "body": null
    }"""

    with pytest.raises(ValueError, match=r"기한만료된 서비스키.*31"):
        _parse_payload(payload)


def test_parse_daily_limit_error_exposes_result_code():
    payload = """{
        "header": {"resultCode": "22", "errorMsg": "서비스 요청제한횟수 초과"},
        "body": null
    }"""

    with pytest.raises(DisasterApiError) as raised:
        _parse_payload(payload)

    assert raised.value.code == "22"


@pytest.mark.asyncio
async def test_api_error_does_not_retry_tls_profiles():
    payload = """{
        "header": {"resultCode": "31", "errorMsg": "기한만료된 서비스키"},
        "body": null
    }"""

    with patch(
        "custom_components.korea_incubator.disaster.api._fetch_with_profile",
        AsyncMock(return_value=payload),
    ) as fetch:
        with pytest.raises(ValueError, match="기한만료된 서비스키"):
            await fetch_disaster_messages("expired-key", count=1)

    fetch.assert_awaited_once()


@pytest.mark.asyncio
async def test_daily_limit_blocks_follow_up_network_calls_until_midnight():
    payload = """{
        "header": {"resultCode": "22", "errorMsg": "서비스 요청제한횟수 초과"},
        "body": null
    }"""
    now = datetime(2026, 8, 28, 14, 30, tzinfo=ZoneInfo("Asia/Seoul"))

    with (
        patch(
            "custom_components.korea_incubator.disaster.api._fetch_with_profile",
            AsyncMock(return_value=payload),
        ) as fetch,
        patch("custom_components.korea_incubator.disaster.api._now", return_value=now),
    ):
        with pytest.raises(DisasterDailyLimitError) as first:
            await fetch_disaster_messages("limited-key", count=1)
        with pytest.raises(DisasterDailyLimitError) as second:
            await fetch_disaster_messages("limited-key", count=1)

    assert first.value.reset_at.isoformat() == "2026-08-29T00:00:00+09:00"
    assert second.value.reset_at == first.value.reset_at
    fetch.assert_awaited_once()


@pytest.mark.asyncio
async def test_daily_limit_block_expires_at_next_midnight():
    key = "limited-key"
    reset_at = datetime(2026, 8, 29, tzinfo=ZoneInfo("Asia/Seoul"))
    after_reset = datetime(2026, 8, 29, 0, 1, tzinfo=ZoneInfo("Asia/Seoul"))
    _daily_limit_blocked_until[key] = reset_at
    payload = '{"header":{"resultCode":"00"},"body":[]}'

    with (
        patch(
            "custom_components.korea_incubator.disaster.api._fetch_with_profile",
            AsyncMock(return_value=payload),
        ) as fetch,
        patch(
            "custom_components.korea_incubator.disaster.api._now",
            return_value=after_reset,
        ),
    ):
        assert await fetch_disaster_messages(key, count=1) == []

    fetch.assert_awaited_once()
    assert key not in _daily_limit_blocked_until


@pytest.mark.asyncio
async def test_validation_accepts_key_that_only_reached_daily_limit():
    reset_at = datetime(2026, 8, 29, tzinfo=ZoneInfo("Asia/Seoul"))

    with patch(
        "custom_components.korea_incubator.disaster.api.fetch_disaster_messages",
        AsyncMock(
            side_effect=DisasterDailyLimitError(
                "서비스 요청제한횟수 초과", reset_at
            )
        ),
    ):
        assert await validate_disaster_api("limited-key") is True
