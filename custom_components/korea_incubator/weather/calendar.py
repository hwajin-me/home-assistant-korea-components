"""Weather warning calendar entity - one per area."""
from __future__ import annotations
from datetime import datetime, timedelta
from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util
from ..const import DOMAIN
from . import EVENT_TYPE_CANCELLED, EVENT_TYPE_KO, EVENT_TYPE_NONE, WARNING_TYPES, AREA_CODES
from .coordinator import WeatherWarningCoordinator
from .device import weather_device

class KMAWeatherCalendar(CoordinatorEntity[WeatherWarningCoordinator], CalendarEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, area_code):
        super().__init__(coordinator)
        self._ac = area_code
        self._attr_unique_id = f"{DOMAIN}_{area_code}_calendar"
        self._attr_name = "기상특보"
        self._attr_icon = "mdi:weather-lightning-rainy"
        self._attr_device_info = weather_device(area_code)

    def _build(self):
        if not self.coordinator.data:
            return []
        area = self.coordinator.data.get(self._ac, {})
        evts = []
        for wc, (_, wn, _) in WARNING_TYPES.items():
            d = area.get(wc, {})
            et = d.get("event_type", EVENT_TYPE_NONE)
            if et in (EVENT_TYPE_CANCELLED, EVENT_TYPE_NONE):
                continue
            sdt = d.get("start_time_dt")
            if not sdt:
                continue
            edt = d.get("end_time_dt") or sdt + timedelta(hours=24)
            label = EVENT_TYPE_KO.get(et, "특보")
            evts.append(CalendarEvent(
                summary=f"{wn} {label}",
                start=dt_util.as_local(sdt), end=dt_util.as_local(edt),
                description=f"지역: {AREA_CODES.get(self._ac,'')}\n특보: {wn}\n등급: {label}",
            ))
        evts.sort(key=lambda e: e.start)
        return evts

    @property
    def event(self):
        evts = self._build()
        if not evts:
            return None
        now = dt_util.now()
        for e in evts:
            if e.start <= now <= e.end:
                return e
        for e in evts:
            if e.start > now:
                return e
        return evts[-1] if evts else None

    async def async_get_events(self, hass, start_date, end_date):
        return [e for e in self._build() if e.start <= end_date and e.end >= start_date]
