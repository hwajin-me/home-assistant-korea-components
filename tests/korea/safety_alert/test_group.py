"""Exercise migration against real HA config, device and entity registries."""

from types import MappingProxyType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry, ConfigEntries
from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components.korea_incubator.const import DOMAIN
from custom_components.korea_incubator.safety_alert.group import (
    migrate_entries,
    region_id,
)
from custom_components.korea_incubator.config_flow import (
    KoreaConfigFlow,
    SafetyAlertRegionFlow,
)


@pytest.fixture
async def registry_hass(tmp_path):
    hass = HomeAssistant(str(tmp_path))
    hass.config_entries = ConfigEntries(hass, {})
    await dr.async_get(hass).async_load()
    await er.async_get(hass).async_load()
    with (
        patch.object(hass.config_entries, "_async_schedule_save"),
        patch.object(dr.async_get(hass), "async_schedule_save"),
        patch.object(er.async_get(hass), "async_schedule_save"),
        patch(
            "custom_components.korea_incubator.safety_alert.group.async_get_clientsession",
            return_value=MagicMock(),
        ),
    ):
        yield hass
    await hass.async_stop()


def add_region(hass, code):
    data = {
        "service": "safety_alert",
        "area_code": "11",
        "area_code2": code,
        "area_name": f"서울 {code}",
    }
    entry = ConfigEntry(
        domain=DOMAIN,
        title=data["area_name"],
        data=data,
        source="user",
        version=1,
        minor_version=1,
        options={},
        unique_id=region_id(data),
        discovery_keys=MappingProxyType({}),
        subentries_data=None,
    )
    hass.config_entries._entries[entry.entry_id] = entry
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, region_id(data))},
        name=data["area_name"],
    )
    entity = er.async_get(hass).async_get_or_create(
        "sensor",
        DOMAIN,
        f"korea_{region_id(data)}_metadata_count",
        config_entry=entry,
        device_id=device.id,
        suggested_object_id=f"region_{code}",
    )
    return entry, device, entity


async def test_three_regions_merge_and_retry_preserves_registry_ids(registry_hass):
    hass = registry_hass
    originals = [add_region(hass, code) for code in ("1", "2", "3")]
    # Starting with the middle entry catches migrations that delete previously
    # moved entities when reconciling the parent's own region.
    parent = migrate_entries(hass, originals[1][0])
    assert parent.title == "안전알림"
    assert len(parent.subentries) == 3
    for source, device, entity in originals:
        migrated = er.async_get(hass).async_get(entity.entity_id)
        assert migrated is not None
        assert migrated.unique_id == entity.unique_id
        assert migrated.device_id == device.id
        assert migrated.config_entry_id == parent.entry_id
        assert migrated.config_subentry_id in parent.subentries
        registered = dr.async_get(hass).async_get(device.id)
        assert registered.config_entries_subentries == {
            parent.entry_id: {migrated.config_subentry_id}
        }
    migrate_entries(hass, originals[2][0])
    assert len(parent.subentries) == 3
    assert len(er.async_get(hass).entities) == 3
    for source, _, _ in originals:
        if source != parent:
            # This is the registry cleanup performed when HA deletes a donor.
            dr.async_get(hass).async_clear_config_entry(source.entry_id)
            er.async_get(hass).async_clear_config_entry(source.entry_id)
    assert len(er.async_get(hass).entities) == 3


async def test_interrupted_migration_resumes_from_another_source(registry_hass):
    hass = registry_hass
    originals = [add_region(hass, code) for code in ("1", "2", "3")]
    registry = er.async_get(hass)
    update = registry.async_update_entity

    def interrupt(entity_id, **kwargs):
        if entity_id == originals[1][2].entity_id:
            raise RuntimeError("interrupted")
        return update(entity_id, **kwargs)

    with patch.object(registry, "async_update_entity", side_effect=interrupt):
        with pytest.raises(RuntimeError, match="interrupted"):
            migrate_entries(hass, originals[0][0])
    parent = migrate_entries(hass, originals[2][0])
    assert parent == originals[0][0]
    assert len(parent.subentries) == 3
    for _, _, entity in originals:
        assert registry.async_get(entity.entity_id).config_entry_id == parent.entry_id


async def test_group_platforms_and_failed_region_are_independent(registry_hass):
    from custom_components.korea_incubator.safety_alert.group import setup_group
    from custom_components.korea_incubator.safety_alert.device import SafetyAlertDevice
    from custom_components.korea_incubator import sensor, binary_sensor
    from homeassistant.helpers.update_coordinator import UpdateFailed

    hass = registry_hass
    parent, _, _ = add_region(hass, "1")
    add_region(hass, "2")
    added = []

    async def update(device):
        if device.area_code2 == "1":
            raise UpdateFailed("temporary outage")
        device.data = {
            "metadata": {"count": 1},
            "parsed_data": {
                "data": [
                    {
                        "RCV_AREA_NM": "서울 2",
                        "MSG_CN": "test",
                        "DSSTR_SE_NM": "호우",
                        "EMRGNCY_STEP_NM": "안전안내",
                        "REGIST_DT": "2026-09-21 10:00:00",
                    }
                ]
            },
        }

    async def forward(entry, platforms):
        for module in (sensor, binary_sensor):
            await module.async_setup_entry(
                hass, entry, lambda entities, **kw: added.append((entities, kw))
            )

    with (
        patch.object(SafetyAlertDevice, "async_update", update),
        patch.object(
            hass.config_entries, "async_forward_entry_setups", side_effect=forward
        ),
        patch(
            "custom_components.korea_incubator.safety_alert.group.remove_merged",
            new_callable=AsyncMock,
        ),
    ):
        assert await setup_group(hass, parent, [])
    assert sum(len(entities) for entities, _ in added) == 14
    assert {kw["config_subentry_id"] for _, kw in added} == set(parent.subentries)
    coords = hass.data[DOMAIN][parent.entry_id]["coordinators"]
    assert sorted(c.last_update_success for c in coords.values()) == [False, True]
    area = next(
        entity
        for entities, _ in added
        for entity in entities
        if entity.name == "최신 알림 대상지" and entity._device.area_code2 == "2"
    )
    assert area.native_value == "서울 2"
    from custom_components.korea_incubator.llm_api.safety_alert_tool import (
        GetSafetyAlertsTool,
    )

    result = await GetSafetyAlertsTool(hass, parent.entry_id).async_call(
        hass, MagicMock(tool_args={}), MagicMock()
    )
    assert result["regions"][0]["alerts"][0]["category"] == "호우"
    assert result["regions"][0]["alerts"][0]["level"] == "안전안내"
    for coordinator in coords.values():
        await coordinator.async_shutdown()


async def test_removing_region_leaves_other_regions(registry_hass):
    hass = registry_hass
    first, _, first_entity = add_region(hass, "1")
    _, _, other_entity = add_region(hass, "2")
    parent = migrate_entries(hass, first)
    sub_id = er.async_get(hass).async_get(first_entity.entity_id).config_subentry_id
    hass.config_entries.async_remove_subentry(parent, sub_id)
    assert er.async_get(hass).async_get(first_entity.entity_id) is None
    assert er.async_get(hass).async_get(other_entity.entity_id) is not None


async def test_modern_device_move_api_and_empty_parent_cleanup(registry_hass):
    hass = registry_hass
    first, _, first_entity = add_region(hass, "1")
    second, second_device, second_entity = add_region(hass, "2")
    devices = dr.async_get(hass)
    empty_parent = devices.async_get_or_create(
        config_entry_id=first.entry_id, identifiers={(DOMAIN, "safety_alert_service")}
    )
    old_update = devices.async_update_device
    moves = []

    def modern_update(
        device_id, *, new_config_entry_id, new_config_subentry_id, via_device_id
    ):
        moves.append((device_id, new_config_entry_id, new_config_subentry_id))
        old_owner = next(iter(devices.async_get(device_id).config_entries))
        old_update(
            device_id,
            add_config_entry_id=new_config_entry_id,
            add_config_subentry_id=new_config_subentry_id,
            via_device_id=via_device_id,
        )
        old_update(
            device_id,
            remove_config_entry_id=old_owner,
            **(
                {"remove_config_subentry_id": None}
                if old_owner == new_config_entry_id
                else {}
            ),
        )

    with patch.object(devices, "async_update_device", modern_update):
        parent = migrate_entries(hass, first)
    assert len(moves) == 2
    assert devices.async_get(empty_parent.id) is None
    assert (
        er.async_get(hass).async_get(second_entity.entity_id).device_id
        == second_device.id
    )
    assert (
        er.async_get(hass).async_get(first_entity.entity_id).config_entry_id
        == parent.entry_id
    )


async def test_new_region_added_to_existing_service_and_duplicate_rejected(
    registry_hass,
):
    hass = registry_hass
    first, _, _ = add_region(hass, "1")
    parent = migrate_entries(hass, first)
    flow = KoreaConfigFlow()
    flow.hass = hass
    flow.handler = DOMAIN
    data = {
        "service": "safety_alert",
        "area_code": "11",
        "area_name2": "수동구",
        "area_name3": "수동동",
        "area_name": "서울 수동구 수동동",
    }
    result = await flow._finish_safety_alert(data)
    assert result["reason"] == "region_added"
    assert len(parent.subentries) == 2
    result = await flow._finish_safety_alert(data)
    assert result["reason"] == "already_configured"
    assert len(parent.subentries) == 2
    subflow = SafetyAlertRegionFlow()
    with patch.object(subflow, "_get_entry", return_value=parent):
        assert (await subflow._finish_safety_alert(data))[
            "reason"
        ] == "already_configured"


async def test_first_region_creates_service_with_subentry(registry_hass):
    flow = KoreaConfigFlow()
    flow.hass = registry_hass
    flow.handler = DOMAIN
    flow.context = {"source": "user"}
    data = {"service": "safety_alert", "area_code": "11", "area_name": "서울"}
    result = await flow._finish_safety_alert(data)
    assert result["title"] == "안전알림"
    assert result["data"] == {"service": "safety_alert", "grouped": True}
    assert result["subentries"][0]["data"] == data
    assert result["subentries"][0]["unique_id"] == "safety_alert_11"


async def test_legacy_province_only_ids_keep_entity_id(registry_hass):
    hass = registry_hass
    entry, device, entity = add_region(hass, "1")
    registry = er.async_get(hass)
    registry.async_update_entity(
        entity.entity_id, new_unique_id="korea_safety_alert_11_metadata_count"
    )
    dr.async_get(hass).async_update_device(
        device.id, new_identifiers={(DOMAIN, "safety_alert_11")}
    )
    parent = migrate_entries(hass, entry)
    migrated = registry.async_get(entity.entity_id)
    assert migrated.unique_id == entity.unique_id
    assert migrated.config_subentry_id in parent.subentries
    assert migrated.device_id == device.id
