"""Pharmacy sensor - counts open pharmacies."""
from __future__ import annotations
from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from ..const import DOMAIN

class PharmacySensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    _attr_icon = "mdi:pharmacy"
    _attr_state_class = SensorStateClass.MEASUREMENT
    def __init__(self, coordinator, q0, q1):
        super().__init__(coordinator)
        # Service name: just district if provided, else sido
        label = q1 if q1 else q0
        self._attr_unique_id = f"{DOMAIN}_pharmacy_{q0}_{q1}"
        self._attr_name = "운영 약국 수"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"pharmacy_{q0}_{q1}")},
            name=f"약국 - {label}", manufacturer="건강보험심사평가원",
            model="약국 운영정보", entry_type=DeviceEntryType.SERVICE)
    @property
    def native_value(self):
        return len(self.coordinator.data or [])
