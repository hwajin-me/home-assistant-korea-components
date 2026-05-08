"""Disaster sensors + event entity."""
from __future__ import annotations
from typing import Any
from homeassistant.components.sensor import SensorEntity
from homeassistant.components.event import EventEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.core import callback
from ..const import DOMAIN
from .device import disaster_device
from .coordinator import DisasterCoordinator

class DisasterMessageSensor(CoordinatorEntity[DisasterCoordinator], SensorEntity):
    _attr_has_entity_name = True
    _attr_icon = "mdi:alert-octagram"
    def __init__(self, coordinator, region=""):
        super().__init__(coordinator)
        suffix = f"_{region}" if region else ""
        self._attr_unique_id = f"{DOMAIN}_disaster_latest{suffix}"
        self._attr_name = "최신 재난문자"
        self._attr_device_info = disaster_device(region)
    @property
    def native_value(self):
        if not self.coordinator.data:
            return "없음"
        return self.coordinator.data[0].get("message", "")[:255]
    @property
    def extra_state_attributes(self):
        if not self.coordinator.data:
            return {}
        d = self.coordinator.data[0]
        return {k: d.get(k, "") for k in ("level","area","disaster_type") if d.get(k)}

class DisasterCountSensor(CoordinatorEntity[DisasterCoordinator], SensorEntity):
    _attr_has_entity_name = True
    _attr_icon = "mdi:counter"
    def __init__(self, coordinator, region=""):
        super().__init__(coordinator)
        suffix = f"_{region}" if region else ""
        self._attr_unique_id = f"{DOMAIN}_disaster_count{suffix}"
        self._attr_name = "재난문자 수"
        self._attr_device_info = disaster_device(region)
    @property
    def native_value(self):
        return len(self.coordinator.data or [])

class DisasterEvent(CoordinatorEntity[DisasterCoordinator], EventEntity):
    _attr_has_entity_name = True
    _attr_event_types = ["emergency", "urgent", "safety", "disaster_info"]
    _attr_icon = "mdi:alert-circle"
    def __init__(self, coordinator, region=""):
        super().__init__(coordinator)
        suffix = f"_{region}" if region else ""
        self._attr_unique_id = f"{DOMAIN}_disaster_event{suffix}"
        self._attr_name = "재난문자 이벤트"
        self._attr_device_info = disaster_device(region)
        self._last_id = None

    @callback
    def _handle_coordinator_update(self):
        data = self.coordinator.data or []
        if not data:
            return
        latest = data[0]
        msg_id = latest.get("create_date", "")
        if self._last_id is not None and msg_id and msg_id != self._last_id:
            # Map level/type to event_type
            level = (latest.get("level") or "").strip()
            event_type = "disaster_info"
            if "긴급" in level:
                event_type = "emergency"
            elif "긴급" not in level and level:
                event_type = "urgent"
            elif "안전" in (latest.get("disaster_type") or ""):
                event_type = "safety"
            self._trigger_event(event_type, {
                "message": latest.get("message", ""),
                "area": latest.get("area", ""),
                "level": level,
                "disaster_type": latest.get("disaster_type", ""),
                "date": str(latest.get("create_date", "")),
            })
        self._last_id = msg_id
        self.async_write_ha_state()
