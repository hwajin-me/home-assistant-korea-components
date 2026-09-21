"""Remove only this entry's retired regional count entity after selection."""

from homeassistant.helpers import entity_registry as er

from ..const import DOMAIN


def remove_legacy_count(hass, entry):
    registry = er.async_get(hass)
    old_id = f"{DOMAIN}_pharmacy_{entry.data['q0']}_{entry.data.get('q1', '')}"
    old_id = entry.data.get("legacy_count_unique_id", old_id)
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if entity.platform == DOMAIN and entity.unique_id == old_id:
            registry.async_remove(entity.entity_id)
