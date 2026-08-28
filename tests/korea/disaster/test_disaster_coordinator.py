"""Tests for disaster coordinator filtering."""

from datetime import datetime
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest

from custom_components.korea_incubator.disaster.api import DisasterDailyLimitError
from custom_components.korea_incubator.disaster.coordinator import (
    DisasterCoordinator,
    _matches_region,
)


def test_subregion_matches_official_api_name():
    assert _matches_region("서울특별시 용산구", "서울 용산구")


def test_province_aliases_match():
    assert _matches_region("전북특별자치도 전주시", "전북 전주시")
    assert _matches_region("제주특별자치도 제주시", "제주 제주시")


def test_different_district_does_not_match():
    assert not _matches_region("서울특별시 강남구", "서울 용산구")


@pytest.mark.asyncio
async def test_daily_limit_returns_no_data_instead_of_setup_failure():
    reset_at = datetime(2026, 8, 29, tzinfo=ZoneInfo("Asia/Seoul"))
    coordinator = object.__new__(DisasterCoordinator)
    coordinator._api_key = "limited-key"
    coordinator._region_filter = "서울 용산구"
    coordinator._consecutive_failures = 0
    coordinator._daily_limit_logged_until = None

    with patch(
        "custom_components.korea_incubator.disaster.coordinator.fetch_disaster_messages",
        AsyncMock(
            side_effect=DisasterDailyLimitError(
                "서비스 요청제한횟수 초과", reset_at
            )
        ),
    ):
        result = await coordinator._async_update_data()

    assert result is None
    assert coordinator._daily_limit_logged_until == reset_at
