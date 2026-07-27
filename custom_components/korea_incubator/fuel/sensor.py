"""Fuel price sensors."""
from __future__ import annotations
from typing import Any
from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from ..const import DOMAIN
from . import FUEL_TYPES, SIDO_CODES
from .coordinator import FuelCoordinator
from .device import fuel_device


class FuelAvgSensor(CoordinatorEntity[FuelCoordinator], SensorEntity):
    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "원/L"
    _attr_icon = "mdi:gas-station"

    def __init__(self, coordinator, sido, fuel_code):
        super().__init__(coordinator)
        self._fuel_code = fuel_code
        self._attr_unique_id = f"{DOMAIN}_fuel_avg_{sido}_{fuel_code}"
        self._attr_name = "전국 평균가"
        self._attr_device_info = fuel_device(sido, fuel_code)

    @property
    def native_value(self):
        for item in (self.coordinator.data or {}).get("average", []):
            if item.get("product_code") == self._fuel_code:
                try:
                    return float(item["price"])
                except (ValueError, KeyError):
                    pass
        return None

    @property
    def extra_state_attributes(self):
        for item in (self.coordinator.data or {}).get("average", []):
            if item.get("product_code") == self._fuel_code:
                return {"diff": item.get("diff", "")}
        return {}


class FuelLowSensor(CoordinatorEntity[FuelCoordinator], SensorEntity):
    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "원/L"
    _attr_icon = "mdi:gas-station-outline"

    def __init__(self, coordinator, sido, fuel_code):
        super().__init__(coordinator)
        self._key = f"low_{sido}_{fuel_code}"
        self._attr_unique_id = f"{DOMAIN}_fuel_low_{sido}_{fuel_code}"
        self._attr_name = "최저가"
        self._attr_device_info = fuel_device(sido, fuel_code)

    @property
    def native_value(self):
        items = (self.coordinator.data or {}).get(self._key, [])
        if items:
            try:
                return float(items[0]["price"])
            except (ValueError, KeyError):
                pass
        return None

    @property
    def extra_state_attributes(self):
        items = (self.coordinator.data or {}).get(self._key, [])
        if not items:
            return {}
        top = items[0]
        attrs: dict[str, Any] = {
            "station_name": top.get("station_name", ""),
            "address": top.get("address", ""),
        }
        if len(items) > 1:
            attrs["ranking"] = [
                {"name": i.get("station_name"), "price": i.get("price"),
                 "address": i.get("address")} for i in items[:5]
            ]
        return attrs
