"""Service-level configuration and migration of regional alert entries."""

from __future__ import annotations

from datetime import timedelta
from functools import partial
import inspect
from types import MappingProxyType, SimpleNamespace
from collections.abc import Mapping
from typing import Any

from homeassistant.config_entries import ConfigEntry, ConfigSubentry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from ..const import DOMAIN, LOGGER
from .device import SafetyAlertDevice
from .migration import migrate_region_unique_ids

SERVICE_DATA = {"service": "safety_alert", "grouped": True}


def region_id(data: Mapping[str, Any]) -> str:
    """Use the same identity for numeric and manually entered regions."""
    return "safety_alert_" + "_".join(
        str(value)
        for value in (
            data.get("area_code"),
            data.get("area_code2") or data.get("area_name2"),
            data.get("area_code3") or data.get("area_name3"),
        )
        if value
    )


def make_device(
    hass: HomeAssistant, entry_id: str, data: Mapping[str, Any]
) -> SafetyAlertDevice:
    """Construct a region device using HA's shared session."""
    return SafetyAlertDevice(
        hass,
        entry_id,
        data["area_code"],
        data["area_name"],
        data.get("area_code2"),
        data.get("area_code3"),
        async_get_clientsession(hass),
        data.get("area_name2"),
        data.get("area_name3"),
    )


def migrate_entries(hass: HomeAssistant, current: ConfigEntry) -> ConfigEntry:
    """Move unloaded entries synchronously before any platform can start.

    Persist each region before moving registry ownership. Source entries are
    deleted asynchronously, after their setup locks have been released. The
    source-ID marker makes an interrupted migration safe to resume.
    """
    entries = [
        e
        for e in hass.config_entries.async_entries(DOMAIN)
        if e.data.get("service") == "safety_alert"
    ]
    parent = next(
        (
            e
            for e in entries
            if e.disabled_by is None
            and (
                e.data.get("grouped")
                or any(s.subentry_type == "region" for s in e.subentries.values())
            )
        ),
        current,
    )
    registry = er.async_get(hass)
    devices = dr.async_get(hass)
    for source in entries:
        if source.data.get("grouped") or source.disabled_by is not None:
            continue
        if source.state == ConfigEntryState.LOADED:
            # A reload must not move live entities. They migrate on restart.
            continue
        sub = next(
            (
                s
                for s in parent.subentries.values()
                if s.data.get("legacy_entry_id") == source.entry_id
            ),
            None,
        )
        if sub is None:
            sub = ConfigSubentry(
                data=MappingProxyType(
                    {**source.data, "legacy_entry_id": source.entry_id}
                ),
                subentry_type="region",
                title=source.data["area_name"],
                unique_id=source.unique_id or source.entry_id,
            )
            hass.config_entries.async_add_subentry(parent, sub)
        device = make_device(hass, source.entry_id, source.data)
        migrate_region_unique_ids(hass, source, device, unassigned_only=True)
        # Move entity ownership first: removing a device's old entry otherwise
        # triggers HA's registry cleanup for entities still owned by it.
        for entity in list(
            er.async_entries_for_config_entry(registry, source.entry_id)
        ):
            if entity.config_subentry_id is None:
                registry.async_update_entity(
                    entity.entity_id,
                    config_entry_id=parent.entry_id,
                    config_subentry_id=sub.subentry_id,
                )
        for registered in list(
            dr.async_entries_for_config_entry(devices, source.entry_id)
        ):
            if (DOMAIN, "safety_alert_service") in registered.identifiers:
                continue
            if registered.identifiers != device.device_info["identifiers"]:
                continue
            if (
                "new_config_entry_id"
                in inspect.signature(devices.async_update_device).parameters
            ):
                devices.async_update_device(
                    registered.id,
                    new_config_entry_id=parent.entry_id,
                    new_config_subentry_id=sub.subentry_id,
                    via_device_id=None,
                )
            else:
                devices.async_update_device(
                    registered.id,
                    add_config_entry_id=parent.entry_id,
                    add_config_subentry_id=sub.subentry_id,
                    via_device_id=None,
                )
                devices.async_update_device(
                    registered.id,
                    remove_config_entry_id=source.entry_id,
                    **({"remove_config_subentry_id": None} if source == parent else {}),
                )
        if source != parent:
            hass.config_entries.async_update_entry(
                source, data={**source.data, "merged_into": parent.entry_id}
            )
    hass.config_entries.async_update_entry(parent, data=SERVICE_DATA, title="안전알림")
    # Remove only the empty devices introduced by the previous grouping bug.
    for registered in list(dr.async_entries_for_config_entry(devices, parent.entry_id)):
        if (
            DOMAIN,
            "safety_alert_service",
        ) in registered.identifiers and not er.async_entries_for_device(
            registry, registered.id
        ):
            devices.async_remove_device(registered.id)
    return parent


async def remove_merged(hass: HomeAssistant) -> None:
    """Delete drained sources only after their setup locks are released."""
    while entry := next(
        (
            e
            for e in hass.config_entries.async_entries(DOMAIN)
            if e.data.get("service") == "safety_alert" and e.data.get("merged_into")
        ),
        None,
    ):
        await hass.config_entries.async_remove(entry.entry_id)


async def setup_group(hass, entry, platforms):
    """Set up independent regional coordinators below one service entry."""
    parent = migrate_entries(hass, entry)
    task_key = f"{DOMAIN}_safety_merge_cleanup"
    if (task := hass.data.get(task_key)) is None or task.done():
        hass.data[task_key] = hass.async_create_task(remove_merged(hass))
    if entry.entry_id != parent.entry_id:
        return True
    store = {"regions": [], "coordinators": {}, "region_stores": {}}
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = store
    entry.async_on_unload(entry.add_update_listener(reload_group))
    for sub in entry.subentries.values():
        device = make_device(hass, entry.entry_id, sub.data)

        async def update(device=device):
            await device.async_update()
            return device.data

        coordinator = DataUpdateCoordinator(
            hass,
            LOGGER,
            name=device.unique_id,
            config_entry=entry,
            update_method=update,
            update_interval=timedelta(minutes=5),
        )
        # A temporarily unavailable region must not hide the other regions.
        await coordinator.async_refresh()
        store["region_stores"][sub.subentry_id] = {
            "device": device,
            "coordinator": coordinator,
        }
        store["coordinators"][sub.subentry_id] = coordinator
        store["regions"].append({"code": sub.subentry_id, "name": sub.title})
    await hass.config_entries.async_forward_entry_setups(entry, platforms)
    from ..llm_api import async_setup_llm_api

    store["unregister_llm"] = await async_setup_llm_api(hass, entry, "safety_alert")
    return True


async def reload_group(hass, entry):
    """Apply region additions and deletions through HA's unload lifecycle."""
    await hass.config_entries.async_reload(entry.entry_id)


async def setup_platform(hass, entry, add_entities, setup):
    """Reuse regional entity definitions with explicit subentry ownership."""
    for sub in entry.subentries.values():
        store = hass.data[DOMAIN][entry.entry_id]["region_stores"].get(sub.subentry_id)
        if store is None:
            # A region added during the initial refresh is picked up by the
            # reload scheduled by the update listener.
            continue
        proxy = SimpleNamespace(entry_id=sub.subentry_id, data=sub.data)
        hass.data[DOMAIN][sub.subentry_id] = store
        try:
            await setup(
                hass, proxy, partial(add_entities, config_subentry_id=sub.subentry_id)
            )
        finally:
            hass.data[DOMAIN].pop(sub.subentry_id, None)
