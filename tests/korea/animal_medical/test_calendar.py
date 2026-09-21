"""Calendar range boundaries, breaks, overnight hours and platform routing."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from custom_components.korea_incubator.animal_medical.calendar import (
    MedicalHoursCalendar,
)
from custom_components.korea_incubator.animal_medical.hours import SEOUL
from custom_components.korea_incubator.calendar import async_setup_entry
from custom_components.korea_incubator.const import DOMAIN

from .test_detail_sensor import coordinator
from .test_pharmacy import DATA, RECORD

TODAY = datetime(2026, 9, 21, tzinfo=SEOUL)


def calendar(days, data=None):
    return MedicalHoursCalendar(
        coordinator(
            {**(RECORD if data is None else data), "_kakao": {"schedule": days}},
            "pharmacy",
        ),
        DATA,
    )


@pytest.mark.asyncio
async def test_breaks_split_events_and_range_overlap():
    entity = calendar({"2026-09-21": {"open": [540, 1170], "breaks": [[810, 840]]}})
    events = await entity.async_get_events(None, TODAY, TODAY + timedelta(days=1))
    assert [
        (e.start.hour, e.start.minute, e.end.hour, e.end.minute) for e in events
    ] == [(9, 0, 13, 30), (14, 0, 19, 30)]
    assert all(e.start.tzinfo == SEOUL and not e.all_day for e in events)
    assert events[0].summary == "약국 영업"
    assert events[0].location == RECORD["dutyAddr"]
    assert len({event.uid for event in events}) == 2
    assert entity.name == "영업시간"
    assert entity.device_info["name"] == "약국"
    assert entity.supported_features == 0
    # Calendar range retrieval returns full intersecting events, not clipped ones.
    assert await entity.async_get_events(
        None, TODAY.replace(hour=10), TODAY.replace(hour=11)
    ) == [events[0]]
    assert (
        await entity.async_get_events(
            None, TODAY.replace(hour=13, minute=30), TODAY.replace(hour=14)
        )
        == []
    )
    assert await entity.async_get_events(None, TODAY, TODAY) == []
    assert await entity.async_get_events(None, TODAY + timedelta(days=1), TODAY) == []
    assert (
        await entity.async_get_events(
            None,
            TODAY.astimezone(timezone.utc),
            (TODAY + timedelta(days=1)).astimezone(timezone.utc),
        )
        == events
    )
    assert (
        await entity.async_get_events(
            None, TODAY + timedelta(days=7), TODAY + timedelta(days=8)
        )
        == []
    )


@pytest.mark.parametrize(
    "hour,minute,index", [(8, 0, 0), (9, 0, 0), (13, 30, 1), (14, 0, 1), (19, 30, None)]
)
def test_event_and_state_advance_at_boundaries(hour, minute, index):
    entity = calendar({"2026-09-21": {"open": [540, 1170], "breaks": [[810, 840]]}})
    now = TODAY.replace(hour=hour, minute=minute)
    with (
        patch(
            "custom_components.korea_incubator.animal_medical.calendar.dt_util.utcnow",
            return_value=now,
        ),
        patch("homeassistant.components.calendar.dt_util.now", return_value=now),
    ):
        if index is None:
            assert entity.event is None
        else:
            assert entity.event == entity._events()[index]
        assert entity.state == ("on" if (hour, minute) in ((9, 0), (14, 0)) else "off")


@pytest.mark.asyncio
async def test_overnight_breaks_overlap_and_off_day():
    entity = calendar(
        {
            "2026-09-21": {
                "open": [1320, 1620],
                "breaks": [[1460, 1500], [1440, 1470], [1500, 1510]],
            },
            "2026-09-22": {"open": None, "breaks": []},
            "2026-09-23": None,
        }
    )
    events = await entity.async_get_events(
        None, TODAY + timedelta(days=1), TODAY + timedelta(days=2)
    )
    assert len(events) == 1  # First segment ends exactly at query start.
    assert events[0].start == TODAY + timedelta(days=1, hours=1, minutes=10)
    assert events[0].end == TODAY + timedelta(days=1, hours=3)
    assert entity.extra_state_attributes["known_dates"] == ["2026-09-21", "2026-09-22"]
    assert entity.extra_state_attributes["unknown_dates"] == ["2026-09-23"]
    assert entity.extra_state_attributes["excludes_breaks"]


@pytest.mark.asyncio
async def test_24_hours_year_rollover_and_entire_day_break():
    entity = calendar(
        {
            "2026-12-31": {"open": [0, 1440], "breaks": []},
            "2027-01-01": {"open": [600, 1200], "breaks": [[600, 1200]]},
        }
    )
    events = entity._events()
    assert len(events) == 1
    assert events[0].end == datetime(2027, 1, 1, tzinfo=SEOUL)
    assert events[0].end - events[0].start == timedelta(days=1)


@pytest.mark.parametrize(
    "days", [{}, {"2026-09-21": None}, {"2026-09-21": {"open": [5, 1], "breaks": []}}]
)
def test_unknown_or_corrupt_hours_unavailable(days):
    entity = calendar(days)
    assert not entity.available
    assert entity.event is None
    assert entity._events() == []


def test_known_closed_and_api_failure_and_renamed_business():
    entity = calendar({"2026-09-21": {"open": None, "breaks": []}})
    assert entity.available
    assert entity._events() == []
    entity.coordinator.data["_kakao"]["schedule"]["2026-09-21"] = {
        "open": [540, 1080],
        "breaks": [],
    }
    entity.coordinator.data["dutyName"] = "새 이름 약국"
    assert entity._events()[0].summary == "새 이름 약국 영업"
    entity.coordinator.last_update_success = False
    assert not entity.available
    assert entity._events() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["hospital", "pharmacy"])
async def test_animal_calendar_platform_device_and_address(
    animal_hass, entry_data, record, kind
):
    entry_data["institution_type"] = kind
    record.pop("ROAD_NM_ADDR")
    record["LOTNO_ADDR"] = "지번주소"
    c = coordinator(
        {
            **record,
            "_kakao": {"schedule": {"2026-09-21": {"open": [540, 1080], "breaks": []}}},
        }
    )
    entry = MagicMock(data=entry_data, entry_id="entry")
    animal_hass.data[DOMAIN] = {"entry": {"coordinator": c}}
    add = MagicMock()
    await async_setup_entry(animal_hass, entry, add)
    entity = add.call_args.args[0][0]
    assert entity.device_info["name"] == record["BPLC_NM"]
    assert entity.unique_id.endswith("_opening_calendar")
    assert entity._events()[0].location == "지번주소"


def test_missing_name_uses_configured_business_name():
    entity = calendar({"2026-09-21": {"open": [540, 1080], "breaks": []}}, data={})
    assert entity._events()[0].summary == DATA["business_name"] + " 영업"
