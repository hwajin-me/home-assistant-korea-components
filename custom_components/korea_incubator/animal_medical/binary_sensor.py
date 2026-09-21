"""Boolean medical status for automations, without guessing unknown hours."""

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .icons import operating_icon

LABELS = {
    "open": "현재 영업 중",
    "break": "현재 휴게 중",
    "hours": "운영시간 확인 가능",
    "location": "위치정보 있음",
    "error": "운영시간 조회 문제",
}


class MedicalBinarySensor(CoordinatorEntity, BinarySensorEntity):
    _attr_has_entity_name = True

    def __init__(self, primary, kind):
        super().__init__(primary.coordinator)
        self.primary, self.kind = primary, kind
        self._attr_name = LABELS[kind]
        self._attr_unique_id = f"{primary.unique_id}_binary_{kind}"
        self._attr_device_info = primary.device_info
        if kind in ("hours", "location", "error"):
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        if kind == "error":
            self._attr_device_class = BinarySensorDeviceClass.PROBLEM

    @property
    def icon(self):
        if self.kind in ("open", "break"):
            return operating_icon(self.primary.native_value)
        active, inactive = {
            "hours": ("mdi:clock-check-outline", "mdi:clock-alert-outline"),
            "location": ("mdi:map-marker-check", "mdi:map-marker-question-outline"),
            "error": ("mdi:alert-circle-outline", "mdi:check-circle-outline"),
        }[self.kind]
        return active if self.is_on else inactive

    @property
    def is_on(self):
        if self.kind in ("open", "break"):
            state = self.primary.native_value
            return None if state is None else state == self.kind
        attrs = self.primary.extra_state_attributes
        return bool(
            attrs[
                {
                    "hours": "opening_hours_available",
                    "location": "location_available",
                    "error": "opening_hours_error",
                }[self.kind]
            ]
        )

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        if self.kind in ("open", "break", "hours"):
            self.async_on_remove(
                async_track_time_change(self.hass, self._clock_tick, second=0)
            )

    @callback
    def _clock_tick(self, _now):
        self.async_write_ha_state()
