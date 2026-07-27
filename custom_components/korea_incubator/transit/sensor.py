"""Transit sensors - pure TIMESTAMP, no string values."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Any
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from ..const import DOMAIN

KST = timezone(timedelta(hours=9))

class SubwayArrivalSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:subway-variant"

    def __init__(self, coordinator, station, direction, line_id, index, device_info):
        super().__init__(coordinator)
        self._key = f"{direction}_{line_id or ''}"
        self._idx = index
        suffix = "now" if index == 0 else "next"
        self._attr_unique_id = f"{DOMAIN}_subway_{station}_{direction}_{line_id}_{suffix}"
        self._attr_name = "다음 열차" if index == 0 else "다다음 열차"
        self._attr_device_info = device_info

    @property
    def native_value(self) -> datetime | None:
        items = (self.coordinator.data or {}).get(self._key, [])
        if self._idx >= len(items):
            return None
        return items[self._idx].get("arrival_time")

    @property
    def extra_state_attributes(self):
        items = (self.coordinator.data or {}).get(self._key, [])
        if self._idx >= len(items):
            return {}
        item = items[self._idx]
        attrs = {k: v for k, v in item.items() if k != "arrival_time" and v}
        dt = item.get("arrival_time")
        if dt:
            remaining = (dt - datetime.now(KST)).total_seconds()
            if remaining <= 60:
                attrs["status"] = "곧 도착"
            elif remaining > 0:
                attrs["status"] = f"{int(remaining // 60)}분 후"
        return attrs


class BusArrivalSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:bus-clock"

    def __init__(self, coordinator, bus_name, index, device_info):
        super().__init__(coordinator)
        self._bus_name = bus_name
        self._idx = index
        suffix = "now" if index == 0 else "next"
        self._attr_unique_id = f"{DOMAIN}_bus_{coordinator.stop_id}_{bus_name}_{suffix}"
        self._attr_name = f"{bus_name} 다음" if index == 0 else f"{bus_name} 다다음"
        self._attr_device_info = device_info

    @property
    def native_value(self) -> datetime | None:
        if not self.coordinator.data:
            return None
        line = self.coordinator.data.get(self._bus_name)
        if not line or line.get("realtimeState") == "NOVEHICLE":
            return None
        arrival = line.get("arrival", {})
        key = "arrivalTime" if self._idx == 0 else "arrivalTime2"
        t = arrival.get(key, 0)
        if not t or t <= 0:
            return None
        return datetime.now(KST) + timedelta(seconds=t)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if not self.coordinator.data:
            return {}
        line = self.coordinator.data.get(self._bus_name, {})
        arrival = line.get("arrival", {})
        key = "arrivalTime" if self._idx == 0 else "arrivalTime2"
        t = arrival.get(key, 0)
        attrs: dict[str, Any] = {"direction": arrival.get("direction")}
        if t and t > 0:
            attrs["remaining_seconds"] = t
            attrs["status"] = "곧 도착" if t <= 60 else f"{int(t // 60)}분 후"
        elif line.get("realtimeState") == "NOVEHICLE":
            attrs["status"] = "운행 종료"
        return attrs
