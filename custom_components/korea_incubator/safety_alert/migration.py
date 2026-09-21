"""Entity registry migrations for the legacy Safety Alert platform."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from ..const import DOMAIN
from .device import SafetyAlertDevice


def _expected_entity_unique_ids(device: SafetyAlertDevice) -> set[str]:
    """Return the complete, stable entity set for a Safety Alert entry."""
    prefix = f"korea_{device.unique_id}_"
    return {
        f"{prefix}safety_alert",
        f"{prefix}metadata_count",
        f"{prefix}parsed_data_data[0]_EMRGNCY_STEP_NM",
        f"{prefix}parsed_data_data[0]_DSSTR_SE_NM",
        f"{prefix}parsed_data_data[0]_MSG_CN",
        f"{prefix}parsed_data_data[0]_RCV_AREA_NM",
        f"{prefix}parsed_data_data[0]_REGIST_DT",
    }


def migrate_region_unique_ids(
    hass: HomeAssistant, entry: ConfigEntry, device: SafetyAlertDevice
) -> None:
    """Reconcile obsolete Safety Alert entities on every setup.

    This runs before platforms are forwarded, so Home Assistant sees only the
    current entity set on an integration reload and on startup.
    """
    legacy_device_id = f"safety_alert_{device.area_code}"
    legacy_prefix = f"korea_{legacy_device_id}_"
    new_prefix = f"korea_{device.unique_id}_"
    expected_unique_ids = _expected_entity_unique_ids(device)
    entity_registry = er.async_get(hass)
    migrated_entity = False
    # A previous startup can have completed only part of this migration.  In
    # that case the registry contains both the old and the new unique ID for
    # the same entity.  Trying to rename the old entry again raises a
    # duplicate-unique-ID error, leaving it behind for the platform to expose
    # as another entity on every reload.
    entries = list(er.async_entries_for_config_entry(entity_registry, entry.entry_id))
    existing_unique_ids = {entity_entry.unique_id for entity_entry in entries}

    for entity_entry in entries:
        if not (
            entity_entry.platform == DOMAIN
            and entity_entry.domain in {"sensor", "binary_sensor"}
            and entity_entry.unique_id.startswith("korea_safety_alert_")
        ):
            continue

        unique_id = entity_entry.unique_id
        if unique_id in expected_unique_ids:
            continue

        if unique_id.startswith(legacy_prefix) and new_prefix != legacy_prefix:
            new_unique_id = new_prefix + unique_id[len(legacy_prefix) :]
            if new_unique_id in expected_unique_ids and new_unique_id not in existing_unique_ids:
                entity_registry.async_update_entity(
                    entity_entry.entity_id,
                    new_unique_id=new_unique_id,
                )
                existing_unique_ids.add(new_unique_id)
            else:
                # The current unique ID is already registered for this config
                # entry, or the legacy ID no longer maps to an entity this
                # platform creates. Discard the stale duplicate.
                entity_registry.async_remove(entity_entry.entity_id)
        else:
            # Entity definitions or unique IDs from older releases are not
            # part of the current platform and would otherwise stay orphaned.
            entity_registry.async_remove(entity_entry.entity_id)
        migrated_entity = True

    # The old identifier may be shared by entries affected by the collision.
    # Move it only when this entry actually owned the registered legacy entities.
    if migrated_entity and device.unique_id != legacy_device_id:
        device_registry = dr.async_get(hass)
        legacy_device = device_registry.async_get_device_by_identifier(
            (DOMAIN, legacy_device_id), entry.entry_id
        )
        if legacy_device is not None:
            device_registry.async_update_device(
                legacy_device.id,
                new_identifiers={(DOMAIN, device.unique_id)},
            )
