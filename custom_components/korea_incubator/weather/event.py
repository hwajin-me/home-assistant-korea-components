"""Weather warning event entities."""
from __future__ import annotations
from typing import Any
from homeassistant.components.event import EventEntity
from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from ..const import DOMAIN
from . import EVENT_TYPE_NONE, EVENT_TYPES, WARNING_TYPES, AREA_CODES
from .coordinator import WeatherWarningCoordinator
from .device import weather_device

class KMAWeatherEvent(CoordinatorEntity[WeatherWarningCoordinator], EventEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "weather_warning"
    _attr_event_types = EVENT_TYPES

    def __init__(self, coordinator, area_code, warning_code, warning_id, warning_name, icon):
        super().__init__(coordinator)
        self._area_code = area_code
        self._warning_code = warning_code
        self._warning_name = warning_name
        self._attr_unique_id = f"{DOMAIN}_{area_code}_{warning_id}"
        self._attr_name = f"{warning_name} 특보"
        self._attr_icon = icon
        self._attr_device_info = weather_device(area_code)
        self._last: str | None = None

    @callback
    def _handle_coordinator_update(self):
        if not self.coordinator.data:
            return
        area = self.coordinator.data.get(self._area_code, {})
        data = area.get(self._warning_code, {})
        new = data.get("event_type", EVENT_TYPE_NONE)
        if self._last is not None and new != self._last:
            ed: dict[str, Any] = {"warning_type": self._warning_name,
                                  "area": AREA_CODES.get(self._area_code, "")}
            if data.get("start_time"):
                ed["start_time"] = data["start_time"]
            if data.get("end_time"):
                ed["end_time"] = data["end_time"]
            self._trigger_event(new, ed)
        self._last = new
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self):
        if not self.coordinator.data:
            return {}
        d = self.coordinator.data.get(self._area_code, {}).get(self._warning_code, {})
        a: dict[str, Any] = {"warning_type": self._warning_name, "area_code": self._area_code}
        if d.get("start_time"):
            a["start_time"] = d["start_time"]
        if d.get("end_time"):
            a["end_time"] = d["end_time"]
        return a
