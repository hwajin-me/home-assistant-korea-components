"""All public fields become Korean-named entities without changing device identity."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.korea_incubator.animal_medical.detail_sensor import (
    MedicalDetailSensor,
    fields,
    setup_medical_sensors,
)
from custom_components.korea_incubator.animal_medical.sensor import AnimalMedicalSensor
from custom_components.korea_incubator.const import DOMAIN
from custom_components.korea_incubator.pharmacy.sensor import PharmacySensor
from custom_components.korea_incubator.sensor import async_setup_entry

from .test_pharmacy import DATA, RECORD


def coordinator(data, kind="animal_medical"):
    return MagicMock(
        data=data,
        service_name=kind,
        last_update_success=True,
        last_refresh=None,
        next_refresh=None,
        interval_minutes=60,
    )


@pytest.mark.parametrize(
    "kind,label", [("hospital", "동물병원"), ("pharmacy", "동물약국")]
)
def test_animal_device_name_and_all_fields(entry_data, record, kind, label):
    entry_data["institution_type"] = kind
    record["NEW_FIELD"] = "new public information"
    primary = AnimalMedicalSensor(coordinator(record), entry_data)
    assert primary.device_info["name"] == record["BPLC_NM"]
    assert primary.name == "현재 운영 상태"
    available = fields(primary)
    assert set(record) <= {key for source, key in available if source == "public"}
    assert (
        "public",
        "CLSBIZ_YMD",
    ) in available  # Known missing fields still have entities.
    assert ("public", "hpid") not in available
    assert all("api_key" not in path for path in available)
    for field, (name, value) in available.items():
        sensor = MedicalDetailSensor(primary, field, name)
        assert sensor.device_info == primary.device_info
        assert sensor.name == name
        assert sensor.extra_state_attributes["value"] == value
    assert (
        MedicalDetailSensor(primary, ("public", "CLSBIZ_YMD"), "폐업일").native_value
        is None
    )


def test_pharmacy_fields_hours_and_names():
    primary = PharmacySensor(coordinator(RECORD, "pharmacy"), DATA)
    assert primary.device_info["name"] == "약국"
    available = fields(primary)
    assert available[("public", "dutyTime1s")] == ("월요일 개점 시각", "0900")
    assert available[("public", "dutyTime8c")][0] == "공휴일 마감 시각"
    assert ("public", "MNG_NO") not in available
    assert set(RECORD) <= {key for source, key in available if source == "public"}
    sensor = MedicalDetailSensor(
        primary, ("detail", "scan_interval_minutes"), "갱신 간격"
    )
    assert sensor.native_value == 60
    assert sensor.native_unit_of_measurement == "min"
    assert (
        MedicalDetailSensor(
            primary, ("detail", "opening_hours_source"), "운영시간 출처"
        ).native_value
        == "카카오맵"
    )


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, None),
        ("", None),
        (True, "예"),
        (False, "아니요"),
        ({}, None),
        ([], None),
        ({"text": "detail"}, "정보 있음"),
        ([1], "정보 있음"),
        ("가" * 300, "가" * 254 + "…"),
        (3.5, 3.5),
        ("text", "text"),
    ],
)
def test_state_limits_full_value_and_identity(entry_data, record, value, expected):
    primary = AnimalMedicalSensor(coordinator({**record, "EXTRA": value}), entry_data)
    sensor = MedicalDetailSensor(primary, ("public", "EXTRA"), "추가 정보")
    assert sensor.native_value == expected
    assert sensor.extra_state_attributes["value"] == value
    assert (
        sensor.unique_id
        == MedicalDetailSensor(primary, ("public", "EXTRA"), "다른 표시명").unique_id
    )
    assert (
        sensor.unique_id
        != MedicalDetailSensor(primary, ("kakao", "EXTRA"), "추가 정보").unique_id
    )
    primary.coordinator.last_update_success = False
    assert not sensor.available


def test_discover_new_fields_on_refresh_and_keep_removed_fields(entry_data, record):
    c = coordinator(record)
    primary = AnimalMedicalSensor(c, entry_data)
    entry, add = MagicMock(), MagicMock()
    setup_medical_sensors(entry, add, primary)
    initial = add.call_args.args[0]
    assert initial[0] is primary
    identifiers = {entity.unique_id for entity in initial}
    assert len(identifiers) == len(initial)
    refresh = c.async_add_listener.call_args.args[0]
    add.reset_mock()
    refresh()
    add.assert_not_called()
    c.data = {
        **record,
        "NEW": "new",
        "_kakao": {"summary": {"name": "기관", "extra": {"data": "complete"}}},
    }
    refresh()
    added = add.call_args.args[0]
    assert len(added) == 3
    assert not identifiers & {entity.unique_id for entity in added}
    assert next(s for s in added if s.field == ("kakao", "name")).native_value == "기관"
    assert next(
        s for s in added if s.field == ("kakao", "extra")
    ).extra_state_attributes["value"] == {"data": "complete"}
    c.data = record
    refresh()
    assert add.call_count == 1
    assert all(entity.native_value is None for entity in added)
    entry.async_on_unload.assert_called_once_with(c.async_add_listener.return_value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,clock",
    [
        (("detail", "open_now"), True),
        (("detail", "opening_hours_available"), True),
        (("public", "TELNO"), False),
    ],
)
async def test_only_clock_dependent_fields_get_minute_updates(
    entry_data, record, field, clock
):
    primary = AnimalMedicalSensor(coordinator(record), entry_data)
    sensor = MedicalDetailSensor(primary, field, "테스트")
    sensor.hass = MagicMock()
    with (
        patch(
            "homeassistant.helpers.update_coordinator.CoordinatorEntity.async_added_to_hass",
            new_callable=AsyncMock,
        ),
        patch(
            "custom_components.korea_incubator.animal_medical.detail_sensor.async_track_time_change"
        ) as track,
        patch.object(sensor, "async_on_remove") as remove,
        patch.object(sensor, "async_write_ha_state") as write,
    ):
        await sensor.async_added_to_hass()
        assert track.call_count == int(clock)
        if clock:
            assert track.call_args.kwargs["second"] == 0
            track.call_args.args[1](None)
            write.assert_called_once()
            remove.assert_called_once_with(track.return_value)


@pytest.mark.asyncio
async def test_pharmacy_platform_routes_all_entities(animal_hass):
    entry = MagicMock(data=DATA, entry_id="pharmacy")
    animal_hass.data[DOMAIN] = {
        "pharmacy": {"coordinator": coordinator(RECORD, "pharmacy")}
    }
    add = MagicMock()
    await async_setup_entry(animal_hass, entry, add)
    entities = add.call_args.args[0]
    assert isinstance(entities[0], PharmacySensor)
    assert len(entities) == 13
    assert len({tuple(e.device_info["identifiers"]) for e in entities}) == 1
    assert {"이름", "연락처", "위치", "상세정보"} <= {
        e.name for e in entities
    }
