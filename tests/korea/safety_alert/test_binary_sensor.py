"""Tests for safe default safety-alert states."""

from unittest.mock import MagicMock

from homeassistant.components.binary_sensor import BinarySensorDeviceClass

from custom_components.korea_incubator.binary_sensor import SafetyAlertSensor


def test_safety_alert_is_off_when_no_data_has_arrived():
    coordinator = MagicMock()
    coordinator.data = None
    device = MagicMock()

    sensor = SafetyAlertSensor(
        coordinator,
        device,
        "안전 알림",
        "safety_alert",
        BinarySensorDeviceClass.SAFETY,
    )

    assert sensor.is_on is False
