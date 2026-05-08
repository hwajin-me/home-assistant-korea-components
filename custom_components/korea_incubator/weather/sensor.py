"""Weather warning binary sensor - ON when any warning is active."""
from __future__ import annotations
from typing import Any
from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from ..const import DOMAIN
from . import EVENT_TYPE_ADVISORY, EVENT_TYPE_WARNING, EVENT_TYPE_PRE_ADVISORY, EVENT_TYPE_PRE_WARNING, AREA_CODES, WARNING_TYPES
from .coordinator import WeatherWarningCoordinator
from .device import weather_device


class WeatherWarningBinarySensor(CoordinatorEntity[WeatherWarningCoordinator], BinarySensorEntity):
    """ON when any weather warning is active for this area."""
    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.SAFETY
    _attr_icon = "mdi:weather-hurricane"

    def __init__(self, coordinator, area_code):
        super().__init__(coordinator)
        self._area_code = area_code
        area_name = AREA_CODES.get(area_code, area_code)
        self._attr_unique_id = f"{DOMAIN}_weather_alert_{area_code}"
        self._attr_name = "기상특보 발령"
        self._attr_device_info = weather_device(area_code)

    @property
    def is_on(self) -> bool:
        """Return True if any warning is active."""
        if not self.coordinator.data:
            return False
        area_data = self.coordinator.data.get(self._area_code, {})
        active_types = {EVENT_TYPE_ADVISORY, EVENT_TYPE_WARNING,
                        EVENT_TYPE_PRE_ADVISORY, EVENT_TYPE_PRE_WARNING}
        for wt, info in area_data.items():
            if info.get("event_type") in active_types:
                return True
        return False

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if not self.coordinator.data:
            return {}
        area_data = self.coordinator.data.get(self._area_code, {})
        active = []
        active_types = {EVENT_TYPE_ADVISORY, EVENT_TYPE_WARNING,
                        EVENT_TYPE_PRE_ADVISORY, EVENT_TYPE_PRE_WARNING}
        for wt, info in area_data.items():
            et = info.get("event_type", "none")
            if et in active_types:
                wt_info = WARNING_TYPES.get(wt)
                name = wt_info[1] if wt_info else str(wt)
                active.append({
                    "type": name,
                    "level": et,
                    "start_time": info.get("start_time"),
                })
        return {
            "active_warnings": active,
            "active_count": len(active),
        }
