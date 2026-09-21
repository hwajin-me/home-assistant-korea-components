"""Korean dates must not drift with HA timezone or pytz historical LMT offsets."""

from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from homeassistant.util import dt as dt_util

from custom_components.korea_incubator.utils import parse_date_value


@pytest.mark.parametrize(
    "value",
    [
        "2025-01-15",
        "20250115",
        "2025/01/15",
        "2025.01.15",
        "2025년 1월 15일",
        "01/15/2025",
        "1.15.2025",
    ],
)
@pytest.mark.parametrize("host_zone", ["UTC", "America/Los_Angeles", "Asia/Seoul"])
def test_all_date_formats_same_korean_date(value, host_zone):
    with patch.object(dt_util, "DEFAULT_TIME_ZONE", ZoneInfo(host_zone)):
        result = parse_date_value(value)
    assert result == datetime(2025, 1, 15, tzinfo=ZoneInfo("Asia/Seoul"))
    assert result.utcoffset() == timedelta(hours=9)
    assert result.astimezone(ZoneInfo("UTC")).isoformat() == "2025-01-14T15:00:00+00:00"


@pytest.mark.parametrize("value", ["2025-01", "2025.01", "202501", "2025년 1월"])
def test_month_only_does_not_shift_to_previous_year(value):
    assert parse_date_value(value).date().isoformat() == "2025-01-01"


@pytest.mark.parametrize(
    "value,expected",
    [
        ("2025-01-15 14:30:00", "2025-01-15T14:30:00+09:00"),
        ("2025/1/15 14:30:00", "2025-01-15T14:30:00+09:00"),
        ("2025-01-15T05:30:00Z", "2025-01-15T14:30:00+09:00"),
        ("2025-01-15T05:30:00.123456+00:00", "2025-01-15T14:30:00.123456+09:00"),
        ("2025-1-15 14:30:00.123", "2025-01-15T14:30:00.123000+09:00"),
        ("2024-02-29", "2024-02-29T00:00:00+09:00"),
    ],
)
def test_timestamp_formats_and_fraction(value, expected):
    assert parse_date_value(value).isoformat() == expected


@pytest.mark.parametrize(
    "value",
    [
        "2025-02-29",
        "20251301",
        "2025년 13월",
        "2025/1/32",
        "2025-01-15 25:00:00",
        "not a date",
        "",
        None,
        20250101,
    ],
)
def test_invalid_dates_are_unknown(value):
    assert parse_date_value(value) is None


def test_short_timestamp_uses_korean_current_year():
    with patch(
        "custom_components.korea_incubator.utils.datetime", wraps=datetime
    ) as clock:
        clock.now.return_value = datetime(2026, 1, 1, tzinfo=ZoneInfo("Asia/Seoul"))
        assert parse_date_value("01/01 00").isoformat() == "2026-01-01T00:00:00+09:00"
        clock.now.assert_called_once_with(ZoneInfo("Asia/Seoul"))
    assert parse_date_value("01/01 00", current_year=2025).year == 2025
