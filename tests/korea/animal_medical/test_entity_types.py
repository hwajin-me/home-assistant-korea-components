"""Typed dates, timestamps, booleans and upcoming opening boundaries."""

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.helpers.entity import EntityCategory

from custom_components.korea_incubator.animal_medical.binary_sensor import (
    MedicalBinarySensor,
)
from custom_components.korea_incubator.animal_medical.detail_sensor import (
    MedicalDetailSensor,
)
from custom_components.korea_incubator.animal_medical.hours import SEOUL
from custom_components.korea_incubator.animal_medical.schedule_sensor import (
    MedicalTransitionSensor,
)
from custom_components.korea_incubator.animal_medical.sensor import AnimalMedicalSensor
from custom_components.korea_incubator.binary_sensor import async_setup_entry
from custom_components.korea_incubator.const import DOMAIN

from .test_detail_sensor import coordinator
from .test_pharmacy import DATA, RECORD


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("2026-09-21", date(2026, 9, 21)),
        ("20260921", date(2026, 9, 21)),
        ("2026-02-30", None),
        ("", None),
    ],
)
def test_date_fields(entry_data, record, raw, expected):
    primary = AnimalMedicalSensor(coordinator({**record, "LCPMT_YMD": raw}), entry_data)
    sensor = MedicalDetailSensor(primary, ("public", "LCPMT_YMD"), "인허가일")
    assert sensor.device_class == SensorDeviceClass.DATE
    assert sensor.native_value == expected
    assert sensor.extra_state_attributes["value"] == raw


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("2026-09-21 09:00:00", datetime(2026, 9, 21, 9, tzinfo=SEOUL)),
        ("2026-09-21T00:00:00Z", datetime(2026, 9, 21, tzinfo=timezone.utc)),
        (
            datetime(2026, 9, 21, tzinfo=timezone.utc),
            datetime(2026, 9, 21, tzinfo=timezone.utc),
        ),
        ("bad", None),
        ("2026-02-30T12:00:00", None),
    ],
)
def test_timestamp_fields(entry_data, record, raw, expected):
    primary = AnimalMedicalSensor(
        coordinator({**record, "DAT_UPDT_PNT": raw}), entry_data
    )
    sensor = MedicalDetailSensor(primary, ("public", "DAT_UPDT_PNT"), "갱신")
    assert sensor.device_class == SensorDeviceClass.TIMESTAMP
    assert sensor.native_value == expected


def test_duration_and_diagnostics(entry_data, record):
    primary = AnimalMedicalSensor(coordinator(record), entry_data)
    sensor = MedicalDetailSensor(
        primary, ("detail", "scan_interval_minutes"), "갱신 간격"
    )
    assert sensor.device_class == SensorDeviceClass.DURATION
    assert sensor.native_unit_of_measurement == "min"
    assert sensor.entity_category == EntityCategory.DIAGNOSTIC


@pytest.mark.parametrize("state", [None, "open", "closed", "break"])
def test_binary_unknown_does_not_mean_closed(state):
    primary = MagicMock(native_value=state, unique_id="stable", device_info={})
    for kind in ("open", "break"):
        entity = MedicalBinarySensor(primary, kind)
        assert entity.is_on == (None if state is None else state == kind)


@pytest.mark.parametrize("value", [True, False])
def test_binary_diagnostics(value):
    primary = MagicMock(
        unique_id="stable",
        device_info={},
        extra_state_attributes={
            "opening_hours_available": value,
            "location_available": value,
            "opening_hours_error": "problem" if value else None,
        },
    )
    for kind in ("hours", "location", "error"):
        entity = MedicalBinarySensor(primary, kind)
        assert entity.is_on == value
        assert entity.entity_category == EntityCategory.DIAGNOSTIC
    assert (
        MedicalBinarySensor(primary, "error").device_class
        == BinarySensorDeviceClass.PROBLEM
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("service", ["pharmacy", "animal_medical"])
async def test_binary_platform(animal_hass, entry_data, record, service):
    entry = MagicMock(
        entry_id="entry", data=DATA if service == "pharmacy" else entry_data
    )
    animal_hass.data[DOMAIN] = {
        "entry": {
            "coordinator": coordinator(
                RECORD if service == "pharmacy" else record, service
            )
        }
    }
    add = MagicMock()
    await async_setup_entry(animal_hass, entry, add)
    entities = add.call_args.args[0]
    assert len(entities) == 2
    assert len({e.unique_id for e in entities}) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind,clock",
    [
        ("open", True),
        ("break", True),
        ("hours", True),
        ("location", False),
        ("error", False),
        ("start", True),
        ("end", True),
    ],
)
async def test_clock_updates_cleanup(entry_data, record, kind, clock):
    primary = AnimalMedicalSensor(coordinator(record), entry_data)
    schedule = kind in ("start", "end")
    cls = MedicalTransitionSensor if schedule else MedicalBinarySensor
    module = "schedule_sensor" if schedule else "binary_sensor"
    entity = cls(primary, kind)
    entity.hass = MagicMock()
    with (
        patch(
            "homeassistant.helpers.update_coordinator.CoordinatorEntity.async_added_to_hass",
            new_callable=AsyncMock,
        ),
        patch(
            f"custom_components.korea_incubator.animal_medical.{module}.async_track_time_change"
        ) as track,
        patch.object(entity, "async_on_remove") as remove,
        patch.object(entity, "async_write_ha_state") as write,
    ):
        await entity.async_added_to_hass()
        assert track.call_count == int(clock)
        if clock:
            track.call_args.args[1](None)
            write.assert_called_once()
            remove.assert_called_once_with(track.return_value)


@pytest.mark.parametrize(
    "hour,minute,start,end",
    [(8, 0, 9, 13.5), (9, 0, 14, 13.5), (13, 30, 14, 19.5), (19, 30, None, None)],
)
def test_next_transitions_from_confirmed_intervals(
    entry_data, record, hour, minute, start, end
):
    primary = AnimalMedicalSensor(
        coordinator(
            {
                **record,
                "_kakao": {
                    "schedule": {
                        "2026-09-21": {"open": [540, 1170], "breaks": [[810, 840]]}
                    }
                },
            }
        ),
        entry_data,
    )
    now = datetime(2026, 9, 21, hour, minute, tzinfo=SEOUL)
    with patch(
        "custom_components.korea_incubator.animal_medical.schedule_sensor.dt_util.utcnow",
        return_value=now,
    ):
        for kind, expected in (("start", start), ("end", end)):
            sensor = MedicalTransitionSensor(primary, kind)
            assert sensor.device_class == SensorDeviceClass.TIMESTAMP
            if expected is None:
                assert sensor.native_value is None
            else:
                assert (
                    sensor.native_value.hour + sensor.native_value.minute / 60
                    == expected
                )
            assert sensor.extra_state_attributes["includes_break_boundaries"]


def test_missing_hours_no_guessed_next_opening(entry_data, record):
    primary = AnimalMedicalSensor(coordinator(record), entry_data)
    assert MedicalTransitionSensor(primary, "start").native_value is None
