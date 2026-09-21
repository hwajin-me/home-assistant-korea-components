"""Restart-relative deadlines, cache validation, forced reloads and storage."""

import json
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.util import dt as dt_util

from custom_components.korea_incubator import (
    _async_animal_options_updated,
    async_setup_entry,
)
from custom_components.korea_incubator.animal_medical.api import AnimalMedicalApiError
from custom_components.korea_incubator.animal_medical.coordinator import (
    AnimalMedicalCoordinator,
)

pytestmark = pytest.mark.asyncio
MODULE = "custom_components.korea_incubator.animal_medical.coordinator"


def make_coordinator(hass, entry_data, interval=60):
    entry = MagicMock(
        entry_id="entry",
        data=entry_data,
        options={"scan_interval_minutes": interval},
        pref_disable_polling=False,
    )
    return AnimalMedicalCoordinator(hass, entry_data, config_entry=entry)


async def test_restart_restores_and_schedules_remaining_time(
    animal_hass, entry_data, record, memory_store
):
    now = dt_util.utcnow()
    first = make_coordinator(animal_hass, entry_data, 30)
    first._find = AsyncMock(return_value=record)
    with patch(f"{MODULE}.dt_util.utcnow", return_value=now):
        assert await first._async_update_data() == record
    saved = memory_store.async_save.call_args.args[0]
    memory_store.async_load.return_value = saved
    second = make_coordinator(animal_hass, entry_data, 30)
    second._find = AsyncMock(return_value=record)
    with patch(f"{MODULE}.dt_util.utcnow", return_value=now + timedelta(minutes=10)):
        await second.async_restore()
        assert await second._async_update_data() == record
        second._find.assert_not_awaited()
        assert second.last_refresh == now
        assert second.next_refresh == now + timedelta(minutes=30)
        with patch.object(animal_hass.loop, "call_at") as timer:
            second._schedule_refresh()
            assert 1199 <= timer.call_args.args[0] - animal_hass.loop.time() <= 1201
        assert second.update_interval == timedelta(minutes=30)
        await second._async_update_data()
        second._find.assert_awaited_once()
        assert second.last_refresh == now + timedelta(minutes=10)


@pytest.mark.parametrize(
    "case",
    [
        "none",
        "fingerprint",
        "missing",
        "invalid_time",
        "naive",
        "future",
        "expired",
        "identity",
        "record",
        "load_error",
        "invalid_time_type",
    ],
)
async def test_invalid_cache_fetches_again(
    animal_hass, entry_data, record, memory_store, case
):
    coordinator = make_coordinator(animal_hass, entry_data)
    now = dt_util.utcnow()
    cache = {
        "fingerprint": coordinator._fingerprint,
        "last_refresh": (now - timedelta(minutes=1)).isoformat(),
        "record": record,
    }
    if case == "none":
        cache = None
    elif case == "fingerprint":
        cache["fingerprint"] = "old settings"
    elif case == "missing":
        del cache["last_refresh"]
    elif case == "invalid_time":
        cache["last_refresh"] = "bad timestamp"
    elif case == "naive":
        cache["last_refresh"] = "2026-01-01T00:00:00"
    elif case == "future":
        cache["last_refresh"] = (now + timedelta(minutes=5)).isoformat()
    elif case == "expired":
        cache["last_refresh"] = (now - timedelta(minutes=60)).isoformat()
    elif case == "identity":
        cache["record"] = {**record, "MNG_NO": "different"}
    elif case == "record":
        cache["record"] = []
    elif case == "load_error":
        memory_store.async_load.side_effect = OSError("unreadable")
    elif case == "invalid_time_type":
        cache["last_refresh"] = 12
    memory_store.async_load.return_value = cache
    coordinator._find = AsyncMock(return_value=record)
    with patch(f"{MODULE}.dt_util.utcnow", return_value=now):
        await coordinator.async_restore()
        assert await coordinator._async_update_data() == record
    coordinator._find.assert_awaited_once()


async def test_no_store_restore_and_failed_save(
    animal_hass, entry_data, record, memory_store, caplog
):
    no_store = AnimalMedicalCoordinator(animal_hass, entry_data)
    await no_store.async_restore()
    assert no_store.next_refresh is None
    coordinator = make_coordinator(animal_hass, entry_data)
    coordinator._find = AsyncMock(return_value=record)
    memory_store.async_save.side_effect = OSError("disk full")
    assert await coordinator._async_update_data() == record
    assert "could not be saved" in caplog.text
    stamp = coordinator.last_refresh
    coordinator._find.side_effect = AnimalMedicalApiError("offline")
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
    assert coordinator.last_refresh == stamp


async def test_options_override_initial_interval(animal_hass, entry_data, memory_store):
    entry_data["scan_interval_minutes"] = 10
    assert AnimalMedicalCoordinator(animal_hass, entry_data).interval_minutes == 10
    assert make_coordinator(animal_hass, entry_data, 25).interval_minutes == 25


async def test_boot_only_restore_and_reload_forces_fetch(animal_hass, entry_data):
    entry = MagicMock(entry_id="entry", data=entry_data)
    coordinator = MagicMock()
    coordinator.async_restore = AsyncMock()
    coordinator.async_config_entry_first_refresh = AsyncMock()
    animal_hass.is_running = False
    with patch(f"{MODULE}.AnimalMedicalCoordinator", return_value=coordinator):
        assert await async_setup_entry(animal_hass, entry)
        assert await async_setup_entry(animal_hass, entry)
        animal_hass.is_running = True
        assert await async_setup_entry(animal_hass, entry)
    coordinator.async_restore.assert_awaited_once()
    assert coordinator.async_config_entry_first_refresh.await_count == 3
    entry.add_update_listener.assert_called_with(_async_animal_options_updated)
    animal_hass.config_entries.async_reload = AsyncMock()
    await _async_animal_options_updated(animal_hass, entry)
    animal_hass.config_entries.async_reload.assert_awaited_once_with("entry")


async def test_real_storage_roundtrip_without_credentials(tmp_path, entry_data, record):
    hass = HomeAssistant(str(tmp_path))
    first = make_coordinator(hass, entry_data)
    first._find = AsyncMock(return_value=record)
    await first._async_update_data()
    await hass.async_block_till_done()
    saved = json.loads(
        (tmp_path / ".storage" / "korea_incubator.animal_medical.entry").read_text()
    )
    assert "api_key" not in json.dumps(saved)
    second = make_coordinator(hass, entry_data)
    second._find = AsyncMock()
    await second.async_restore()
    assert await second._async_update_data() == record
    second._find.assert_not_awaited()
    assert second.last_refresh == first.last_refresh
    await first.async_shutdown()
    await second.async_shutdown()


async def test_remove_entry_removes_storage(animal_hass, entry_data):
    from custom_components.korea_incubator import async_remove_entry

    animal_hass.data["korea_incubator_animal_started"] = {"entry"}
    with patch("homeassistant.helpers.storage.Store") as store:
        store.return_value.async_remove = AsyncMock()
        await async_remove_entry(
            animal_hass, MagicMock(data=entry_data, entry_id="entry")
        )
        store.return_value.async_remove.assert_awaited_once()
        assert not animal_hass.data["korea_incubator_animal_started"]
        await async_remove_entry(animal_hass, MagicMock(data={"service": "other"}))
        store.return_value.async_remove.assert_awaited_once()
