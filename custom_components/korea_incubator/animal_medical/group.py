"""Flat service groups for animal pharmacies and animal hospitals."""

from __future__ import annotations

import inspect
from types import SimpleNamespace
from uuid import uuid4

from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import device_registry as dr, entity_registry as er

from ..const import DOMAIN
from .sensor import institution_identifier
from .services import group_title, register_medical_action


class FacilityEntry:
    """Read-only view used by the existing institution editing forms."""

    def __init__(self, parent, key):
        self.parent, self.key = parent, key

    def __getattr__(self, name):
        member = self.parent.data["facilities"][self.key]
        if name in {"data", "options", "unique_id"}:
            return member.get(name, {})
        return getattr(self.parent, name)


def save_facility(hass, entry, *, data=None, options=None, unique_id=None):
    parent = entry.parent
    members = dict(parent.data["facilities"])
    member = dict(members[entry.key])
    for key, value in (("data", data), ("options", options), ("unique_id", unique_id)):
        if value is not None:
            member[key] = value
    members[entry.key] = member
    changed = hass.config_entries.async_update_entry(
        parent, data={**parent.data, "facilities": members}
    )
    if not changed or not parent.update_listeners:
        hass.config_entries.async_schedule_reload(parent.entry_id)


def add_facility(flow, data, options=None):
    """Return a flow result when appending to an existing matching service."""
    parent = next(
        (
            e
            for e in flow._async_current_entries()
            if e.data.get("medical_group")
            and e.data.get("institution_type") == data["institution_type"]
        ),
        None,
    )
    if parent is None:
        return None
    members = dict(parent.data["facilities"])
    if any(
        member.get("unique_id") == flow.unique_id
        or institution_identifier(member["data"]) == institution_identifier(data)
        for member in members.values()
    ):
        return flow.async_abort(reason="already_configured")
    members[uuid4().hex] = {
        "data": data,
        "options": options or {},
        "unique_id": flow.unique_id,
    }
    flow.hass.config_entries.async_update_entry(
        parent, data={**parent.data, "facilities": members}
    )
    return flow.async_abort(reason="medical_added")


def migrate(hass, current):
    entries = [
        e
        for e in hass.config_entries.async_entries(DOMAIN)
        if e.data.get("service") == "animal_medical"
        and e.data.get("institution_type") == current.data["institution_type"]
    ]
    parent = next(
        (e for e in entries if e.data.get("medical_group") and e.disabled_by is None),
        current,
    )
    members = dict(parent.data.get("facilities", {}))
    if not parent.data.get("medical_group"):
        members.setdefault(
            parent.entry_id,
            {
                "data": dict(parent.data),
                "options": dict(parent.options),
                "unique_id": parent.unique_id,
            },
        )
    registry, devices = er.async_get(hass), dr.async_get(hass)
    for source in entries:
        if (
            source.data.get("medical_group")
            or source.data.get("merged_into")
            or source.disabled_by is not None
        ):
            continue
        if source.state == ConfigEntryState.LOADED:
            continue
        members.setdefault(
            source.entry_id,
            {
                "data": dict(source.data),
                "options": dict(source.options),
                "unique_id": source.unique_id,
            },
        )
        # Persist configuration before ownership changes; source keys make retry idempotent.
        hass.config_entries.async_update_entry(
            parent,
            title=group_title(parent.data),
            data={
                **parent.data,
                "medical_group": True,
                "facilities": dict(members),
            },
        )
        for entity in list(
            er.async_entries_for_config_entry(registry, source.entry_id)
        ):
            registry.async_update_entity(
                entity.entity_id, config_entry_id=parent.entry_id
            )
        if source != parent:
            for device in list(
                dr.async_entries_for_config_entry(devices, source.entry_id)
            ):
                if (
                    "new_config_entry_id"
                    in inspect.signature(devices.async_update_device).parameters
                ):
                    devices.async_update_device(
                        device.id, new_config_entry_id=parent.entry_id
                    )
                else:
                    devices.async_update_device(
                        device.id, add_config_entry_id=parent.entry_id
                    )
                    devices.async_update_device(
                        device.id, remove_config_entry_id=source.entry_id
                    )
            hass.config_entries.async_update_entry(
                source, data={**source.data, "merged_into": parent.entry_id}
            )
    return parent


async def setup(hass, entry, platforms):
    from .coordinator import AnimalMedicalCoordinator
    from .. import _async_animal_options_updated

    parent = migrate(hass, entry)
    task_key = f"{DOMAIN}_medical_merge_cleanup"
    if (task := hass.data.get(task_key)) is None or task.done():
        hass.data[task_key] = hass.async_create_task(cleanup(hass))
    if entry != parent:
        return True
    store = {"facilities": {}}
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = store
    entry.async_on_unload(entry.add_update_listener(_async_animal_options_updated))
    for key, member in entry.data["facilities"].items():
        coordinator = AnimalMedicalCoordinator(
            hass,
            member["data"],
            config_entry=entry,
            options=member["options"],
            storage_id=key,
        )
        started = hass.data.setdefault(f"{DOMAIN}_animal_started", set())
        if not hass.is_running and key not in started:
            await coordinator.async_restore()
        started.add(key)
        await coordinator.async_refresh()
        store["facilities"][key] = coordinator
        register_medical_action(hass, SimpleNamespace(entry_id=key), coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, platforms)
    return True


async def cleanup(hass):
    while entry := next(
        (
            e
            for e in hass.config_entries.async_entries(DOMAIN)
            if e.data.get("service") == "animal_medical" and e.data.get("merged_into")
        ),
        None,
    ):
        await hass.config_entries.async_remove(entry.entry_id)


def setup_platform(hass, entry, add, platform):
    """Create every facility's entities in one reconciliation pass."""
    from .sensor import AnimalMedicalSensor
    from .compact_sensor import setup_compact_sensors
    from .binary_sensor import MedicalBinarySensor
    from .calendar import MedicalHoursCalendar

    for key, member in entry.data["facilities"].items():
        coord = hass.data[DOMAIN][entry.entry_id]["facilities"].get(key)
        if coord is None:
            continue
        primary = AnimalMedicalSensor(coord, member["data"])
        if platform == "sensor":
            setup_compact_sensors(hass, entry, add, primary)
        elif platform == "binary_sensor":
            add([MedicalBinarySensor(primary, kind) for kind in ("open", "error")])
        else:
            add([MedicalHoursCalendar(coord, member["data"])])


def remove_device(hass, entry, device):
    remaining = {
        key: member
        for key, member in entry.data["facilities"].items()
        if (DOMAIN, institution_identifier(member["data"])) not in device.identifiers
    }
    if len(remaining) == len(entry.data["facilities"]):
        return False
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, "facilities": remaining}
    )
    return True
