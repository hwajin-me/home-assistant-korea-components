"""Tests for disaster sensor states."""

from unittest.mock import MagicMock

from custom_components.korea_incubator.disaster.sensor import (
    DisasterCountSensor,
    DisasterMessageSensor,
)


def test_sensors_are_unknown_while_coordinator_data_is_none():
    coordinator = MagicMock()
    coordinator.data = None

    message = DisasterMessageSensor(coordinator, "서울 용산구")
    count = DisasterCountSensor(coordinator, "서울 용산구")

    assert message.native_value is None
    assert count.native_value is None


def test_empty_successful_response_is_not_unknown():
    coordinator = MagicMock()
    coordinator.data = []

    message = DisasterMessageSensor(coordinator, "서울 용산구")
    count = DisasterCountSensor(coordinator, "서울 용산구")

    assert message.native_value == "없음"
    assert count.native_value == 0
