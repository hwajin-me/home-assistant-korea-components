"""Remove deselected static entities after a platform has set up successfully."""

from collections.abc import Mapping
from functools import wraps

from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import DOMAIN

# Dynamic shipment entities and account-based sensors have their own lifecycle.
STATIC_SERVICES = {
    "weather_warning",
    "transit",
    "fuel",
    "school",
    "airkorea",
    "kma_weather",
    "safety_alert",
    "animal_medical",
    "pharmacy",
    "disaster",
}


def reconcile_entities(platform):
    """Keep configured (including disabled) entities and prune only this entry's stale IDs."""

    def decorate(setup):
        @wraps(setup)
        async def wrapped(hass, entry, async_add_entities):
            if entry.data.get("service") not in STATIC_SERVICES:
                return await setup(hass, entry, async_add_entities)
            expected = set()
            expected_devices = set()

            def add(entities, *args, **kwargs):
                entities = list(entities)
                expected.update(
                    entity.unique_id for entity in entities if entity.unique_id
                )
                for entity in entities:
                    info = getattr(entity, "device_info", None)
                    if isinstance(info, Mapping):
                        expected_devices.update(info.get("identifiers", set()))
                async_add_entities(entities, *args, **kwargs)

            result = await setup(hass, entry, add)
            # Only reconcile successful setup: API/setup failures leave old IDs intact.
            if result is False:
                return result
            try:
                registry = er.async_get(hass)
            except KeyError:
                return result
            affected_devices = set()
            for entity in list(
                er.async_entries_for_config_entry(registry, entry.entry_id)
            ):
                if (
                    entity.platform == DOMAIN
                    and entity.domain == platform
                    and entity.unique_id not in expected
                ):
                    if entity.device_id:
                        affected_devices.add(entity.device_id)
                    registry.async_remove(entity.entity_id)
            if affected_devices:
                devices = dr.async_get(hass)
                for device_id in affected_devices:
                    # Other platforms or entries may still use a shared device.
                    if (device := devices.async_get(device_id)) is not None and not any(
                        entity.config_entry_id == entry.entry_id
                        for entity in er.async_entries_for_device(
                            registry, device_id, include_disabled_entities=True
                        )
                    ):
                        if expected_devices.intersection(
                            getattr(device, "identifiers", set())
                        ):
                            continue
                        if entry.entry_id in device.config_entries:
                            devices.async_update_device(
                                device_id, remove_config_entry_id=entry.entry_id
                            )
            return result

        return wrapped

    return decorate
