"""Consolidated entities and date-specific closure actions."""

from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.korea_incubator.animal_medical.closed_days import (
    closed_day_status,
    upcoming_closed_days,
)
from custom_components.korea_incubator.animal_medical.compact_sensor import (
    NAMES,
    MedicalInfoSensor,
    remove_retired_entities,
)
from custom_components.korea_incubator.animal_medical.hours import SEOUL
from custom_components.korea_incubator.animal_medical.services import (
    group_title,
    register_medical_action,
    unregister_medical_action,
)
from custom_components.korea_incubator.const import DOMAIN

OFF = {"open": None, "breaks": []}
ON = {"open": [540, 1080], "breaks": []}
DAY = date(2026, 9, 22)


def test_minimum_date():
    assert closed_day_status({}, date.min) is None


@pytest.mark.parametrize(
    "days,expected",
    [
        ({}, None),
        ({"bad": OFF}, None),
        ({"2026-09-22": None}, None),
        ({"2026-09-22": OFF}, True),
        ({"2026-09-22": ON}, False),
        (
            {"2026-09-21": {"open": [1200, 1500], "breaks": []}, "2026-09-22": OFF},
            False,
        ),
        ({"2026-09-21": {"open": [1200, 1440], "breaks": []}, "2026-09-22": OFF}, True),
    ],
)
def test_closed_date(days, expected):
    assert closed_day_status(days, DAY) is expected
    assert upcoming_closed_days(days, DAY) == ([DAY] if expected is True else [])


@pytest.fixture
def primary():
    return MagicMock(
        unique_id="clinic",
        device_info={"model": "동물병원"},
        native_value="open",
        _entry_data={"business_name": "저장된 이름"},
        extra_state_attributes={
            "business_name": "라온동물병원",
            "api_record": {},
            "latitude": 37.5,
            "longitude": 127.0,
            "phone": "02-123",
        },
        coordinator=MagicMock(
            data={
                "_kakao": {
                    "summary": {"name": "지도 이름"},
                    "media": {
                        "rating": 4.5,
                        "photo_count": 2,
                        "main_photo": "https://t1.daumcdn.net/a.jpg",
                    },
                    "schedule": {
                        "2026-09-22": {**OFF, "closure_reason": "임시휴무"},
                        "2026-09-23": None,
                    },
                }
            },
            last_refresh=datetime(2026, 9, 21, tzinfo=SEOUL),
        ),
    )


def test_groups(primary):
    with patch(
        "custom_components.korea_incubator.animal_medical.compact_sensor.dt_util.now",
        return_value=datetime(2026, 9, 21, tzinfo=SEOUL),
    ):
        expected = [
            "라온동물병원",
            "37.5, 127.0",
            "02-123",
            "정보 있음",
            None,
            None,
            None,
            None,
            primary.coordinator.last_refresh,
            DAY,
        ]
        for kind, value in zip(NAMES, expected, strict=True):
            sensor = MedicalInfoSensor(primary, kind)
            assert sensor.native_value == value
            assert sensor.extra_state_attributes
            assert "카카오" not in sensor.name
            assert sensor.entity_picture == (
                "https://t1.daumcdn.net/a.jpg" if kind == "name" else None
            )
        attrs = MedicalInfoSensor(primary, "closed_day").extra_state_attributes
        assert attrs["known_dates"] == ["2026-09-22"]
        assert attrs["unknown_dates"] == ["2026-09-23"]
        assert attrs["closed_day_details"] == [
            {"date": "2026-09-22", "reason": "임시휴무"}
        ]


def test_missing_and_long_values(primary):
    primary.extra_state_attributes = {"api_record": {}}
    assert MedicalInfoSensor(primary, "name").native_value == "지도 이름"
    primary.coordinator.data = {}
    assert MedicalInfoSensor(primary, "name").native_value == "저장된 이름"
    assert (
        MedicalInfoSensor(primary, "name").extra_state_attributes["business_name"]
        == "저장된 이름"
    )
    for kind in ("location", "contact", "opening", "closing", "breaks", "closed_day"):
        assert MedicalInfoSensor(primary, kind).native_value is None
    assert MedicalInfoSensor(primary, "name").entity_picture is None
    primary.extra_state_attributes["business_name"] = "가" * 300
    assert len(MedicalInfoSensor(primary, "name").native_value) == 255
    assert (
        len(MedicalInfoSensor(primary, "name").extra_state_attributes["business_name"])
        == 300
    )
    primary.coordinator.data = {"_kakao": {"schedule": {"invalid": OFF}}}
    assert (
        MedicalInfoSensor(primary, "closed_day").extra_state_attributes["known_dates"]
        == []
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", list(NAMES))
async def test_clocks(primary, kind):
    entity = MedicalInfoSensor(primary, kind)
    entity.hass = MagicMock()
    with (
        patch(
            "homeassistant.helpers.update_coordinator.CoordinatorEntity.async_added_to_hass",
            new_callable=AsyncMock,
        ),
        patch(
            "custom_components.korea_incubator.animal_medical.compact_sensor.async_track_time_change"
        ) as track,
        patch.object(entity, "async_on_remove") as remove,
        patch.object(entity, "async_write_ha_state") as write,
    ):
        await entity.async_added_to_hass()
        assert track.call_count == int(
            kind in ("hours", "opening", "closing", "breaks", "closed_day")
        )
        if track.called:
            track.call_args.args[1](None)
            write.assert_called_once()
            remove.assert_called_once_with(track.return_value)


def test_retired_registry(primary, compact_registry):
    entries = [
        MagicMock(platform=platform, unique_id=uid, entity_id=uid)
        for platform, uid in [
            (DOMAIN, "clinic_detail_phone"),
            (DOMAIN, "clinic_binary_break"),
            (DOMAIN, "clinic"),
            (DOMAIN, "another_detail_phone"),
            ("other", "clinic_detail_phone"),
        ]
    ]
    compact_registry.entities.get_entries_for_config_entry_id.return_value = entries
    remove_retired_entities(MagicMock(), MagicMock(entry_id="entry"), primary)
    assert [c.args[0] for c in compact_registry.async_remove.call_args_list] == [
        "clinic_detail_phone",
        "clinic_binary_break",
    ]


@pytest.mark.asyncio
async def test_action(animal_hass, primary):
    entry = MagicMock(entry_id="entry")
    coord = primary.coordinator
    register_medical_action(animal_hass, entry, coord)
    args = animal_hass.services.async_register.call_args
    handler, schema = args.args[2], args.kwargs["schema"]
    for requested, expected in [("2026-09-22", "closed"), ("2026-09-23", "unknown")]:
        response = await handler(
            MagicMock(data=schema({"config_entry_id": "entry", "date": requested}))
        )
        assert response["status"] == expected
        assert response["closure_reason"] == (
            "임시휴무" if expected == "closed" else None
        )
    coord.data["_kakao"]["schedule"] = {"2026-09-22": ON}
    assert (await handler(MagicMock(data={"config_entry_id": "entry", "date": DAY})))[
        "status"
    ] == "open"
    coord.last_update_success = False
    assert (await handler(MagicMock(data={"config_entry_id": "entry", "date": DAY})))[
        "is_closed"
    ] is None
    coord.data = {"_kakao": {"schedule": {"bad": OFF}}}
    assert (await handler(MagicMock(data={"config_entry_id": "entry", "date": DAY})))[
        "known_dates"
    ] == []
    with pytest.raises(ServiceValidationError):
        await handler(MagicMock(data={"config_entry_id": "missing", "date": DAY}))
    register_medical_action(animal_hass, MagicMock(entry_id="second"), coord)
    unregister_medical_action(animal_hass, "entry")
    animal_hass.services.async_remove.assert_not_called()
    unregister_medical_action(animal_hass, "second")
    animal_hass.services.async_remove.assert_called_once()


@pytest.mark.parametrize(
    "data,title",
    [
        ({"service": "pharmacy"}, "약국"),
        ({"service": "animal_medical", "institution_type": "hospital"}, "동물병원"),
        ({"service": "animal_medical", "institution_type": "pharmacy"}, "동물약국"),
    ],
)
def test_group_title(data, title):
    assert group_title(data) == title
