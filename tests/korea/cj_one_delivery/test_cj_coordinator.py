"""Tests for CJ O-NE coordinator retention policies."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytz

from custom_components.korea_incubator.cj_one_delivery.api import DeliveryStatus
from custom_components.korea_incubator.cj_one_delivery.coordinator import (
    _completed_sensor_statuses,
    _scan_interval,
)


def test_completed_parcel_sensors_are_retained_for_two_days() -> None:
    timezone = pytz.timezone("Asia/Seoul")
    now = timezone.localize(datetime(2026, 8, 8, 12))
    statuses = [
        DeliveryStatus(
            "recent",
            "배송완료",
            last_event_time="2026-08-06 12:00:00",
            display_group="배송완료",
        ),
        DeliveryStatus(
            "expired",
            "배송완료",
            last_event_time="2026-08-06 11:59:59",
            display_group="배송완료",
        ),
        DeliveryStatus(
            "active",
            "배송출발",
            last_event_time="2026-08-08 11:00:00",
            display_group="진행중",
        ),
    ]

    result = _completed_sensor_statuses(statuses, now=now)

    assert [status.tracking_number for status in result] == ["recent"]


def test_scan_interval_is_clamped_to_supported_range() -> None:
    entry = MagicMock()

    entry.options = {"scan_interval_minutes": 2}
    assert _scan_interval(entry) == timedelta(minutes=3)

    entry.options = {"scan_interval_minutes": 31}
    assert _scan_interval(entry) == timedelta(minutes=30)
