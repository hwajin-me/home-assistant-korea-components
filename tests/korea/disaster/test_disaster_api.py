"""Tests for disaster API response handling."""

from unittest.mock import AsyncMock, patch

import pytest

from custom_components.korea_incubator.disaster.api import (
    _parse_payload,
    fetch_disaster_messages,
)


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
