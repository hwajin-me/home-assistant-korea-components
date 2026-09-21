"""Regressions from lifecycle, persisted-state and configuration-path review."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.util import dt as dt_util

from custom_components.korea_incubator import async_unload_entry
from custom_components.korea_incubator.animal_medical.hours import valid_schedule
from custom_components.korea_incubator.const import DOMAIN
from custom_components.korea_incubator.pharmacy.api import PharmacyApiError
from custom_components.korea_incubator.pharmacy.coordinator import PharmacyCoordinator
from custom_components.korea_incubator.pharmacy.services import (
    KEYS,
    async_register_pharmacy_service,
    async_unregister_pharmacy_service,
)

from .test_pharmacy import DATA, RECORD, P


@pytest.mark.asyncio
async def test_reconfigure_interval_overrides_old_options(flow, kakao_network):
    entry = MagicMock(
        data=DATA,
        options={"scan_interval_minutes": 120},
        unique_id="pharmacy_C1",
        entry_id="entry",
    )
    flow.context = {"source": "reconfigure"}
    flow._get_reconfigure_entry = MagicMock(return_value=entry)
    form = await flow.async_step_reconfigure()
    assert form["data_schema"]({"api_key": "key"})["scan_interval_minutes"] == 120
    flow._kakao_entry = {**DATA, "scan_interval_minutes": 15}
    flow.async_update_reload_and_abort = MagicMock(return_value={})
    await flow._async_kakao_finish("123")
    updates = flow.async_update_reload_and_abort.call_args.kwargs
    assert updates["options"]["scan_interval_minutes"] == 15
    new_entry = MagicMock(options=updates["options"], entry_id="entry")
    coordinator = PharmacyCoordinator(
        flow.hass, updates["data_updates"], config_entry=new_entry
    )
    assert coordinator.interval_minutes == 15


@pytest.mark.asyncio
async def test_incomplete_page_keeps_existing_selection(flow):
    with (
        patch(f"{P}.config_flow.async_get_clientsession", return_value=MagicMock()),
        patch(f"{P}.config_flow.fetch_page", new_callable=AsyncMock) as fetch,
    ):
        fetch.return_value = ([RECORD], 101)
        await flow.async_step_pharmacy(DATA)
        fetch.return_value = ([], 101)
        result = await flow.async_step_pharmacy_select({"selection": "__next__"})
    assert result["errors"]["base"] == "animal_cannot_connect"
    assert flow._pharmacy_page == 1
    assert flow._pharmacy_items == [RECORD]


@pytest.mark.asyncio
async def test_service_selects_active_entry_and_unload_releases_key(animal_hass):
    animal_hass.services = MagicMock()
    async_register_pharmacy_service(animal_hass, "key-a", "a")
    async_register_pharmacy_service(animal_hass, "key-b", "b")
    callback = animal_hass.services.async_register.call_args.args[2]
    with (
        patch(f"{P}.services.async_get_clientsession", return_value=MagicMock()),
        patch(
            f"{P}.services.fetch_pharmacies", new_callable=AsyncMock, return_value=[]
        ) as fetch,
    ):
        await callback(MagicMock(data={"region": "서울", "config_entry_id": "b"}))
        assert fetch.call_args.args[1] == "key-b"
        async_unregister_pharmacy_service(animal_hass, "b")
        animal_hass.services.async_remove.assert_not_called()
        await callback(MagicMock(data={"region": "서울"}))
        assert fetch.call_args.args[1] == "key-a"
        with pytest.raises(ServiceValidationError):
            await callback(MagicMock(data={"region": "서울", "config_entry_id": "b"}))
        fetch.side_effect = PharmacyApiError("quota exhausted")
        with pytest.raises(HomeAssistantError, match="quota exhausted"):
            await callback(MagicMock(data={"region": "서울"}))
    async_unregister_pharmacy_service(animal_hass, "a")
    assert KEYS not in animal_hass.data
    animal_hass.services.async_remove.assert_called_once_with(DOMAIN, "search_pharmacy")
    with pytest.raises(ServiceValidationError):
        await callback(MagicMock(data={"region": "서울"}))


@pytest.mark.asyncio
@pytest.mark.parametrize("success", [True, False])
async def test_failed_unload_preserves_llm_and_service(animal_hass, success):
    animal_hass.services = MagicMock()
    cleanup = MagicMock()
    animal_hass.data[DOMAIN] = {"entry": {"unregister_llm": cleanup}}
    animal_hass.data[KEYS] = {"entry": "key"}
    animal_hass.config_entries.async_unload_platforms.return_value = success
    entry = MagicMock(entry_id="entry", data=DATA)
    assert await async_unload_entry(animal_hass, entry) == success
    assert cleanup.call_count == int(success)
    assert (KEYS in animal_hass.data) != success


@pytest.mark.parametrize(
    "days",
    [
        None,
        [],
        {"bad-date": None},
        {"2026-09-21": []},
        {"2026-09-21": {"open": None, "breaks": "bad"}},
        {"2026-09-21": {"open": None, "breaks": [[600, 700]]}},
        {"2026-09-21": {"open": [True, 1440], "breaks": []}},
        {"2026-09-21": {"open": [-10, 600], "breaks": []}},
        {"2026-09-21": {"open": [1500, 1600], "breaks": []}},
        {"2026-09-21": {"open": [0, 1500], "breaks": []}},
        {"2026-09-21": {"open": [600, 1200], "breaks": [[500, 700]]}},
    ],
)
def test_corrupt_schedule_is_rejected(days):
    assert not valid_schedule(days)


def test_unknown_closed_overnight_cache_is_valid():
    assert valid_schedule(
        {
            "2026-09-20": None,
            "2026-09-21": {"open": None, "breaks": []},
            "2026-09-22": {"open": [1320, 1560], "breaks": [[1440, 1450]]},
        }
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "place",
    [
        None,
        [],
        {"summary": {}, "open_hours": {}, "schedule": None, "place_id": "123"},
        {"summary": {}, "open_hours": {}, "schedule": {}, "place_id": "other"},
    ],
)
async def test_corrupt_cached_hours_force_refresh(animal_hass, memory_store, place):
    coordinator = PharmacyCoordinator(
        animal_hass, DATA, config_entry=MagicMock(options={}, entry_id="entry")
    )
    memory_store.async_load.return_value = {
        "fingerprint": coordinator._fingerprint,
        "last_refresh": dt_util.utcnow().isoformat(),
        "record": {**RECORD, "_kakao": place},
    }
    await coordinator.async_restore()
    assert coordinator._restored_data is None
