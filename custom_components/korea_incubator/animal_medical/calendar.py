"""Read-only calendar of confirmed opening intervals, excluding breaks."""

from datetime import datetime, time, timedelta

from homeassistant.components.calendar import (
    CalendarEntity,
    CalendarEntityFeature,
    CalendarEvent,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .hours import SEOUL, effective_schedule
from .sensor import AnimalMedicalSensor


class MedicalHoursCalendar(CoordinatorEntity, CalendarEntity):
    """Use cached date-specific hours; never invent recurring future events."""

    _attr_has_entity_name = True
    _attr_name = "영업시간"
    _attr_icon = "mdi:calendar-clock"
    _attr_supported_features = CalendarEntityFeature(0)

    def __init__(self, coordinator, entry_data):
        super().__init__(coordinator)
        if entry_data["service"] == "pharmacy":
            from ..pharmacy.sensor import PharmacySensor

            self._primary = PharmacySensor(coordinator, entry_data)
        else:
            self._primary = AnimalMedicalSensor(coordinator, entry_data)
        self._attr_unique_id = f"{self._primary.unique_id}_opening_calendar"
        self._attr_device_info = self._primary.device_info
        self._business_name = entry_data["business_name"]

    def _schedule(self):
        return effective_schedule(self.coordinator.data)

    @property
    def available(self):
        return super().available and any(
            day is not None for day in self._schedule().values()
        )

    def _events(self):
        if not self.available:
            return []
        attrs = self._primary.extra_state_attributes
        name = attrs.get("business_name") or self._business_name
        events = []
        for date, day in sorted(self._schedule().items()):
            if day is None or day["open"] is None:
                continue
            start, end = day["open"]
            intervals = []
            # Merge overlapping breaks implicitly by moving the cursor forward.
            for left, right in sorted(day["breaks"]):
                if start < left:
                    intervals.append((start, left))
                start = max(start, right)
            if start < end:
                intervals.append((start, end))
            midnight = datetime.combine(
                datetime.fromisoformat(date).date(), time(), SEOUL
            )
            for left, right in intervals:
                events.append(
                    CalendarEvent(
                        start=midnight + timedelta(minutes=left),
                        end=midnight + timedelta(minutes=right),
                        summary=f"{name} 영업",
                        location=attrs.get("road_address")
                        or attrs.get("lot_number_address"),
                        description="연결된 지도의 날짜별 운영시간 기준입니다. 휴게시간은 제외되며 실제 운영 여부는 기관에 확인하세요.",
                        uid=f"{self.unique_id}_{date}_{left}_{right}",
                    )
                )
        return sorted(events, key=lambda event: event.start)

    @property
    def event(self):
        now = dt_util.utcnow()
        return next((event for event in self._events() if event.end > now), None)

    async def async_get_events(self, hass, start_date, end_date):
        if start_date >= end_date:
            return []
        return [
            event
            for event in self._events()
            if event.start < end_date and event.end > start_date
        ]

    @property
    def extra_state_attributes(self):
        days = self._schedule()
        return {
            "opening_hours_source": "kakao",
            "known_dates": sorted(
                date for date, day in days.items() if day is not None
            ),
            "unknown_dates": sorted(date for date, day in days.items() if day is None),
            "excludes_breaks": True,
        }
