"""Medical grouping preserves registrations and per-facility configuration."""

from types import MappingProxyType
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntries, ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components.korea_incubator.const import DOMAIN
from custom_components.korea_incubator.animal_medical.group import (
    migrate,
    FacilityEntry,
    remove_device,
)
from custom_components.korea_incubator.animal_medical.sensor import (
    institution_identifier,
)
from custom_components.korea_incubator.config_flow import (
    KoreaConfigFlow,
    KoreaOptionsFlow,
)


@pytest.fixture
async def group_hass(tmp_path):
    hass = HomeAssistant(str(tmp_path))
    hass.config_entries = ConfigEntries(hass, {})
    await dr.async_get(hass).async_load()
    await er.async_get(hass).async_load()
    with (
        patch.object(hass.config_entries, "_async_schedule_save"),
        patch.object(dr.async_get(hass), "async_schedule_save"),
        patch.object(er.async_get(hass), "async_schedule_save"),
    ):
        yield hass
    await hass.async_stop()


def add(hass, name, kind="pharmacy"):
    data = {
        "service": "animal_medical",
        "institution_type": kind,
        "municipality_code": "3000000",
        "management_number": name,
        "business_name": name,
        "api_key": name + "-key",
        "kakao_place_id": "123",
    }
    entry = ConfigEntry(
        domain=DOMAIN,
        data=data,
        options={"scan_interval_minutes": len(name) + 10},
        title="동물약국",
        unique_id=institution_identifier(data),
        source="user",
        version=1,
        minor_version=1,
        discovery_keys=MappingProxyType({}),
        subentries_data=None,
    )
    hass.config_entries._entries[entry.entry_id] = entry
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, institution_identifier(data))},
        name=name,
    )
    entity = er.async_get(hass).async_get_or_create(
        "sensor",
        DOMAIN,
        f"{DOMAIN}_{institution_identifier(data)}",
        config_entry=entry,
        device_id=device.id,
        suggested_object_id=name,
    )
    return entry, device, entity


async def test_two_pharmacies_merge_flat_but_hospital_stays_separate(group_hass):
    hass = group_hass
    first, d1, e1 = add(hass, "healing")
    second, d2, e2 = add(hass, "kookmin")
    hospital, _, _ = add(hass, "hospital", "hospital")
    parent = migrate(hass, second)
    assert parent == second
    assert set(parent.data["facilities"]) == {first.entry_id, second.entry_id}
    assert not parent.subentries
    assert not hospital.data.get("medical_group")
    for source, device, entity in ((first, d1, e1), (second, d2, e2)):
        registered = er.async_get(hass).async_get(entity.entity_id)
        assert registered.device_id == device.id
        assert registered.unique_id == entity.unique_id
        assert registered.config_entry_id == parent.entry_id
        assert registered.config_subentry_id is None
        assert (
            parent.data["facilities"][source.entry_id]["options"][
                "scan_interval_minutes"
            ]
            == 17
        )
    migrate(hass, first)
    assert len(parent.data["facilities"]) == 2
    dr.async_get(hass).async_clear_config_entry(first.entry_id)
    er.async_get(hass).async_clear_config_entry(first.entry_id)
    assert er.async_get(hass).async_get(e1.entity_id) is not None


async def test_interrupted_transfer_resumes(group_hass):
    hass = group_hass
    first, _, _ = add(hass, "one")
    second, _, entity = add(hass, "two")
    registry = er.async_get(hass)
    original = registry.async_update_entity

    def fail(entity_id, **kwargs):
        if entity_id == entity.entity_id:
            raise RuntimeError("interrupted")
        return original(entity_id, **kwargs)

    with patch.object(registry, "async_update_entity", side_effect=fail):
        with pytest.raises(RuntimeError):
            migrate(hass, first)
    parent = migrate(hass, second)
    assert parent == first
    assert len(parent.data["facilities"]) == 2
    assert registry.async_get(entity.entity_id).config_entry_id == parent.entry_id


async def test_edit_options_and_add_do_not_create_extra_group(group_hass):
    hass = group_hass
    first, _, _ = add(hass, "one")
    second, _, _ = add(hass, "two")
    second_id = second.entry_id
    parent = migrate(hass, first)
    original = parent.data["facilities"][first.entry_id]
    flow = KoreaOptionsFlow(parent)
    flow.hass = hass
    result = await flow.async_step_init()
    assert result["step_id"] == "medical_facility_options"
    result = await flow.async_step_medical_facility_options({"facility": second_id})
    assert result["step_id"] == "animal_medical_options"
    with patch.object(hass.config_entries, "async_schedule_reload"):
        flow.async_create_entry(title="", data={"scan_interval_minutes": 99})
    assert parent.data["facilities"][second_id]["options"] == {
        "scan_interval_minutes": 99
    }
    assert parent.data["facilities"][first.entry_id] == original
    config = KoreaConfigFlow()
    config.hass, config.handler, config.context = (
        hass,
        DOMAIN,
        {"source": "user", "unique_id": "new"},
    )
    data = {**original["data"], "management_number": "new", "business_name": "new"}
    result = config._finish_service_entry(title="동물약국", data=data)
    assert result["reason"] == "medical_added"
    assert len(parent.data["facilities"]) == 3
    assert not parent.subentries


async def test_reconfigure_chooses_facility_and_updates_only_it(group_hass):
    hass = group_hass
    first, _, _ = add(hass, "one")
    second, _, _ = add(hass, "two")
    parent = migrate(hass, first)
    flow = KoreaConfigFlow()
    flow.hass, flow.handler = hass, DOMAIN
    flow.context = {"source": "reconfigure", "entry_id": parent.entry_id}
    assert (await flow.async_step_reconfigure())["step_id"] == "medical_facility"
    with patch.object(flow, "async_step_animal_medical", new_callable=AsyncMock):
        await flow.async_step_medical_facility({"facility": second.entry_id})
    assert isinstance(flow._get_reconfigure_entry(), FacilityEntry)
    data = {**flow._reconfigure_entry.data, "business_name": "renamed"}
    with patch.object(hass.config_entries, "async_schedule_reload"):
        result = flow._finish_service_entry(title="동물약국", data=data)
    assert result["reason"] == "reconfigure_successful"
    assert (
        parent.data["facilities"][second.entry_id]["data"]["business_name"] == "renamed"
    )
    assert parent.data["facilities"][first.entry_id]["data"]["business_name"] == "one"


async def test_all_platforms_preserve_both_facilities_and_independent_options(
    group_hass,
):
    from custom_components.korea_incubator.animal_medical.group import setup
    from custom_components.korea_incubator.animal_medical.coordinator import (
        AnimalMedicalCoordinator,
    )
    from custom_components.korea_incubator import sensor, binary_sensor, calendar
    from custom_components.korea_incubator.animal_medical.services import STORE

    hass = group_hass
    first, device, _ = add(hass, "one")
    second, _, _ = add(hass, "second")
    captured = []

    async def forward(entry, platforms):
        for platform in (sensor, binary_sensor, calendar):
            await platform.async_setup_entry(
                hass, entry, lambda entities: captured.extend(entities)
            )

    with (
        patch.object(AnimalMedicalCoordinator, "async_restore", new_callable=AsyncMock),
        patch.object(
            AnimalMedicalCoordinator,
            "_async_update_data",
            new_callable=AsyncMock,
            return_value={},
        ),
        patch.object(
            hass.config_entries, "async_forward_entry_setups", side_effect=forward
        ),
        patch(
            "custom_components.korea_incubator.animal_medical.group.cleanup",
            new_callable=AsyncMock,
        ),
    ):
        assert await setup(hass, first, [])
    assert len(captured) == 32
    assert len({entity.unique_id for entity in captured}) == 32
    assert not first.subentries
    coords = hass.data[DOMAIN][first.entry_id]["facilities"]
    assert coords[first.entry_id].interval_minutes == 13
    assert coords[second.entry_id].interval_minutes == 16
    assert coords[first.entry_id]._store.key.endswith(first.entry_id)
    assert coords[second.entry_id]._store.key.endswith(second.entry_id)
    assert hass.data[STORE][second.entry_id] == coords[second.entry_id]
    with patch.object(hass.config_entries, "async_reload", new_callable=AsyncMock):
        assert remove_device(hass, first, device)
        await hass.async_block_till_done()
    assert set(first.data["facilities"]) == {second.entry_id}
    for coordinator in coords.values():
        await coordinator.async_shutdown()


async def test_reauth_updates_only_selected_facility(group_hass):
    hass = group_hass
    first, _, _ = add(hass, "one")
    second, _, _ = add(hass, "two")
    parent = migrate(hass, first)
    flow = KoreaConfigFlow()
    flow.hass, flow.handler = hass, DOMAIN
    flow.context = {"source": "reauth", "entry_id": parent.entry_id}
    assert (await flow.async_step_reauth(parent.data))["step_id"] == "medical_facility"
    await flow.async_step_medical_facility({"facility": second.entry_id})
    with patch.object(hass.config_entries, "async_schedule_reload"):
        result = flow.async_update_reload_and_abort(
            flow._get_reauth_entry(), data_updates={"api_key": "new-key"}
        )
    assert result["reason"] == "reauth_successful"
    assert parent.data["facilities"][first.entry_id]["data"]["api_key"] == "one-key"
    assert parent.data["facilities"][second.entry_id]["data"]["api_key"] == "new-key"
