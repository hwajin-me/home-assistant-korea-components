"""Hours refresh, clock-driven state, GPS fallback and listener cleanup."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.korea_incubator.animal_medical.coordinates import point_wgs84
from custom_components.korea_incubator.animal_medical.coordinator import (
    AnimalMedicalCoordinator,
)
from custom_components.korea_incubator.animal_medical.hours import SEOUL, current_state
from custom_components.korea_incubator.animal_medical.kakao import KakaoError
from custom_components.korea_incubator.animal_medical.sensor import AnimalMedicalSensor

from .test_hours import STAMP, day, hours
from .test_persistence import make_coordinator


@pytest.mark.asyncio
async def test_refresh_hours_failure_drops_stale_state(
    animal_hass, entry_data, record, kakao_network
):
    entry_data["kakao_place_id"] = "123"
    coordinator = AnimalMedicalCoordinator(animal_hass, entry_data)
    refresh = kakao_network[2]
    refresh.return_value = {
        "summary": {"point": {"lat": 37.5, "lon": 127}},
        "open_hours": hours(day()),
    }
    with (
        patch(
            "custom_components.korea_incubator.animal_medical.coordinator.async_get_clientsession",
            return_value=MagicMock(),
        ),
        patch.object(coordinator, "_find", new_callable=AsyncMock, return_value=record),
        patch(
            "custom_components.korea_incubator.animal_medical.coordinator.dt_util.utcnow",
            return_value=STAMP,
        ),
    ):
        coordinator.data = await coordinator._async_update_data()
        assert "2026-09-21" in coordinator.data["_kakao"]["schedule"]
        sensor = AnimalMedicalSensor(coordinator, entry_data)
        with patch(
            "custom_components.korea_incubator.animal_medical.sensor.current_state",
            side_effect=lambda d: current_state(d, STAMP),
        ):
            assert sensor.native_value == "open"
            attrs = sensor.extra_state_attributes
            assert attrs["open_now"] is True
            assert attrs["latitude"] == 37.5
            assert attrs["api_record"] == record
        # Refreshing after midnight must retain the prior date's overnight shift.
        coordinator.data["_kakao"]["schedule"]["2026-09-20"] = {
            "open": [1200, 1560],
            "breaks": [],
        }
        coordinator.data = await coordinator._async_update_data()
        assert "2026-09-20" in coordinator.data["_kakao"]["schedule"]
        refresh.side_effect = KakaoError("HTTP 503")
        coordinator.data = await coordinator._async_update_data()
        assert sensor.native_value is None
        assert sensor.extra_state_attributes["opening_hours_error"] == "HTTP 503"
        assert "_kakao" not in coordinator.data
        assert (
            sensor.extra_state_attributes["operating_status"] == record["SALS_STTS_NM"]
        )
    await coordinator.async_shutdown()


@pytest.mark.asyncio
async def test_sensor_clock_and_cleanup(entry_data):
    sensor = AnimalMedicalSensor(MagicMock(data={}), entry_data)
    sensor.hass = MagicMock()
    unsubscribe = MagicMock()
    with (
        patch(
            "homeassistant.helpers.update_coordinator.CoordinatorEntity.async_added_to_hass",
            new_callable=AsyncMock,
        ),
        patch(
            "custom_components.korea_incubator.animal_medical.sensor.async_track_time_change",
            return_value=unsubscribe,
        ) as track,
        patch.object(sensor, "async_write_ha_state") as write,
        patch.object(sensor, "async_on_remove") as remove,
    ):
        await sensor.async_added_to_hass()
        assert track.call_args.kwargs == {"second": 0}
        track.call_args.args[1](datetime.now(SEOUL))
        write.assert_called_once()
        remove.assert_called_once_with(unsubscribe)


@pytest.mark.parametrize(
    "point",
    [
        None,
        {},
        {"lat": True, "lon": 127},
        {"lat": 37, "lon": False},
        {"lat": "bad", "lon": 127},
        {"lat": None, "lon": 127},
        {"lat": 90, "lon": 127},
        {"lat": float("nan"), "lon": 127},
    ],
)
def test_invalid_kakao_gps(point):
    assert point_wgs84(point) == {}


def test_wgs_point():
    assert point_wgs84({"lat": "37.5", "lon": "127.2"}) == {
        "latitude": 37.5,
        "longitude": 127.2,
    }


@pytest.mark.asyncio
async def test_cached_hours_after_restart_change_with_clock_without_fetch(
    animal_hass, entry_data, record, memory_store, kakao_network
):
    from datetime import timedelta

    from custom_components.korea_incubator.animal_medical.hours import schedule

    entry_data["kakao_place_id"] = "123"
    coordinator = make_coordinator(animal_hass, entry_data, 1440)
    saved = STAMP.replace(hour=18)
    record = {
        **record,
        "_kakao": {
            "place_id": "123",
            "schedule": schedule(hours(day()), saved),
            "open_hours": hours(day()),
            "summary": {},
            "fetched_at": saved.isoformat(),
        },
    }
    memory_store.async_load.return_value = {
        "fingerprint": coordinator._fingerprint,
        "last_refresh": saved.isoformat(),
        "record": record,
    }
    coordinator._find = AsyncMock()
    with patch(
        "custom_components.korea_incubator.animal_medical.coordinator.dt_util.utcnow",
        return_value=saved + timedelta(minutes=10),
    ):
        await coordinator.async_restore()
        coordinator.data = await coordinator._async_update_data()
    sensor = AnimalMedicalSensor(coordinator, entry_data)
    for hour, expected in ((18, "open"), (19, "closed")):
        with patch(
            "custom_components.korea_incubator.animal_medical.sensor.current_state",
            side_effect=lambda d, hour=hour: current_state(d, STAMP.replace(hour=hour)),
        ):
            assert sensor.native_value == expected
            assert sensor.extra_state_attributes["open_now"] == (expected == "open")
    coordinator._find.assert_not_awaited()
    kakao_network[2].assert_not_awaited()
    assert coordinator.next_refresh == saved + timedelta(days=1)
    await coordinator.async_shutdown()
