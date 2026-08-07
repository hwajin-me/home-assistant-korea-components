"""Tests for CJ O-NE coordinator retention policies."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytz

from custom_components.korea_incubator.cj_one_delivery.api import DeliveryStatus
from custom_components.korea_incubator.cj_one_delivery.coordinator import (
    _completed_sensor_statuses,
    _normalized_status,
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


def test_cj_status_is_normalized_for_automations() -> None:
    expected_statuses = {
        "01": ("scheduled", "배송대기"),
        "42": ("in_transit", "배송중"),
        "82": ("out_for_delivery", "배송출발"),
        "91": ("delivered", "배송완료"),
        "9927": ("in_transit", "배송중"),
        "9933": ("in_transit", "배송중"),
    }

    for status_code, expected in expected_statuses.items():
        assert (
            _normalized_status(
                DeliveryStatus("tracking", "CJ 원본 상태", status_code=status_code)
            )
            == expected
        )

    assert _normalized_status(DeliveryStatus("tracking", "알 수 없는 상태")) == (
        "unknown",
        "알 수 없는 상태",
    )
