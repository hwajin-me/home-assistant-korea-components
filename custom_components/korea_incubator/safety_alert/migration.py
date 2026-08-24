"""Entity registry migrations for the legacy Safety Alert platform."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from ..const import DOMAIN
from .device import SafetyAlertDevice


def migrate_region_unique_ids(
    hass: HomeAssistant, entry: ConfigEntry, device: SafetyAlertDevice
) -> None:
    """Add subregion identifiers to legacy IDs owned by this config entry."""
    legacy_device_id = f"safety_alert_{device.area_code}"
    if device.unique_id == legacy_device_id:
        return

    legacy_prefix = f"korea_{legacy_device_id}_"
    new_prefix = f"korea_{device.unique_id}_"
    entity_registry = er.async_get(hass)
    migrated_entity = False

    for entity_entry in er.async_entries_for_config_entry(
        entity_registry, entry.entry_id
    ):
        if (
            entity_entry.platform == DOMAIN
            and entity_entry.domain in {"sensor", "binary_sensor"}
            and entity_entry.unique_id.startswith(legacy_prefix)
        ):
            entity_registry.async_update_entity(
                entity_entry.entity_id,
                new_unique_id=new_prefix + entity_entry.unique_id[len(legacy_prefix) :],
            )
            migrated_entity = True

    # The old identifier may be shared by entries affected by the collision.
    # Move it only when this entry actually owned the registered legacy entities.
    if migrated_entity:
        device_registry = dr.async_get(hass)
        legacy_device = device_registry.async_get_device(
            identifiers={(DOMAIN, legacy_device_id)}
        )
        if legacy_device is not None:
            device_registry.async_update_device(
                legacy_device.id,
                new_identifiers={(DOMAIN, device.unique_id)},
            )
