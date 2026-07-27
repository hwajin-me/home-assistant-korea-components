"""Weather platform dispatcher."""
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from .const import DOMAIN, CONF_ENTRY_TYPE, ENTRY_KMA_WEATHER

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    etype = entry.data.get(CONF_ENTRY_TYPE)
    store = hass.data[DOMAIN][entry.entry_id]

    if etype == ENTRY_KMA_WEATHER:
        from .kma_weather.weather import KMAWeather
        c = store["coordinator"]
        entities = []
        for reg in store.get("regions", []):
            entities.append(KMAWeather(c, reg["name"], reg["nx"], reg["ny"]))
        async_add_entities(entities)
