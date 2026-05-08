"""Earthquake sensors + geolocation + event."""
from __future__ import annotations
from typing import Any
from homeassistant.components.geo_location import GeolocationEvent
from homeassistant.components.event import EventEntity
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.core import callback
from ..const import DOMAIN
from .api import haversine_km

def eq_device():
    return DeviceInfo(identifiers={(DOMAIN, "earthquake")},
                      name="지진 정보", manufacturer="기상청",
                      model="지진정보", entry_type=DeviceEntryType.SERVICE)

class EarthquakeEvent(CoordinatorEntity, EventEntity):
    _attr_has_entity_name = True
    _attr_event_types = ["earthquake_alert"]
    _attr_icon = "mdi:earth-arrow-down"
    def __init__(self, coordinator, home_lat, home_lon, radius_km, min_mag):
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_earthquake_event"
        self._attr_name = "지진 경보"
        self._attr_device_info = eq_device()
        self._home_lat = home_lat
        self._home_lon = home_lon
        self._radius = radius_km
        self._min_mag = min_mag
        self._last_dt = None

    @callback
    def _handle_coordinator_update(self):
        data = self.coordinator.data or []
        for eq in data:
            lat = eq.get("latitude")
            lon = eq.get("longitude")
            mag = eq.get("magnitude") or 0
            dt = eq.get("datetime", "")
            if not lat or not lon or not dt:
                continue
            dist = haversine_km(self._home_lat, self._home_lon, lat, lon)
            if dist <= self._radius and mag >= self._min_mag:
                if self._last_dt is not None and dt != self._last_dt:
                    self._trigger_event("earthquake_alert", {
                        "magnitude": mag, "location": eq.get("location",""),
                        "distance_km": round(dist, 1), "datetime": dt,
                        "depth": eq.get("depth",""),
                    })
                self._last_dt = dt
                break
        self.async_write_ha_state()
