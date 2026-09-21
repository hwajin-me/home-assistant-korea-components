"""Upcoming opening/resumption and closing/break timestamps from calendar intervals."""

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import callback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .calendar import MedicalHoursCalendar


class MedicalTransitionSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:clock-outline"

    def __init__(self, primary, kind):
        super().__init__(primary.coordinator)
        self.kind = kind
        self._calendar = MedicalHoursCalendar(primary.coordinator, primary._entry_data)
        self._attr_unique_id = f"{primary.unique_id}_next_{kind}"
        self._attr_device_info = primary.device_info
        self._attr_name = (
            "다음 운영 시작 시각" if kind == "start" else "다음 운영 종료 시각"
        )

    @property
    def native_value(self):
        now = dt_util.utcnow()
        return min(
            (
                stamp
                for event in self._calendar._events()
                if (stamp := getattr(event, self.kind)) > now
            ),
            default=None,
        )

    @property
    def extra_state_attributes(self):
        return {"source": "kakao", "includes_break_boundaries": True}

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self.async_on_remove(
            async_track_time_change(self.hass, self._clock_tick, second=0)
        )

    @callback
    def _clock_tick(self, _now):
        self.async_write_ha_state()
