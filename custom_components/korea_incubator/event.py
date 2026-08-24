"""Event platform dispatcher."""
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .const import (
    CONF_ENTRY_TYPE,
    DOMAIN,
    ENTRY_AIRKOREA,
    ENTRY_DISASTER,
    ENTRY_EARTHQUAKE,
    ENTRY_SAFETY_ALERT,
    ENTRY_WEATHER,
)


def _migrate_earthquake_unique_id(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Migrate the one legacy earthquake entity owned by this config entry."""
    registry = er.async_get(hass)
    legacy_unique_id = f"{DOMAIN}_earthquake_event"
    new_unique_id = f"{DOMAIN}_{entry.entry_id}_earthquake_event"
    for entity_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if (
            entity_entry.domain == "event"
            and entity_entry.platform == DOMAIN
            and entity_entry.unique_id == legacy_unique_id
        ):
            registry.async_update_entity(
                entity_entry.entity_id, new_unique_id=new_unique_id
            )
            break

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    etype = entry.data.get(CONF_ENTRY_TYPE)
    store = hass.data[DOMAIN][entry.entry_id]
    entities = []

    if etype == ENTRY_WEATHER:
        from .weather import WARNING_TYPES
        from .weather.event import KMAWeatherEvent
        c = store["coordinator"]
        for ac in store["area_codes"]:
            for wc, (wid, wn, icon) in WARNING_TYPES.items():
                entities.append(KMAWeatherEvent(c, ac, wc, wid, wn, icon))

    elif etype == ENTRY_DISASTER:
        from .disaster.sensor import DisasterEvent
        entities = [DisasterEvent(store["coordinator"], store.get("region", ""))]

    elif etype == ENTRY_SAFETY_ALERT:
        from .safety_alert.sensor import SafetyAlertEvent
        for region in store.get("regions", []):
            coord = store["coordinators"].get(region["code"])
            if coord:
                entities.append(SafetyAlertEvent(coord, region["code"], region["name"]))

    elif etype == ENTRY_AIRKOREA:
        from .airkorea.sensor import AirAlertEvent
        c = store["coordinator"]
        sido = entry.data.get("sido", "")
        for st in store.get("stations", []):
            entities.append(AirAlertEvent(c, st["stationName"], sido))

    elif etype == ENTRY_EARTHQUAKE:
        from .earthquake.sensor import EarthquakeEvent
        _migrate_earthquake_unique_id(hass, entry)
        c = store["coordinator"]
        lat = entry.data.get("home_latitude", 37.5665)
        lon = entry.data.get("home_longitude", 126.978)
        radius = entry.data.get("radius_km", 200)
        min_mag = entry.data.get("min_magnitude", 3.0)
        entities = [
            EarthquakeEvent(c, entry.entry_id, lat, lon, radius, min_mag)
        ]

    if entities:
        async_add_entities(entities)
