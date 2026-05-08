from __future__ import annotations

from datetime import datetime, time, date, timedelta
from zoneinfo import ZoneInfo

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ..const import DOMAIN
from .coordinator import SchoolCoordinator
from .device import school_device

# 한국 표준시 (KST)
KST = ZoneInfo("Asia/Seoul")


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up calendar entities."""
    coordinator = hass.data[DOMAIN][entry.entry_id]

    entities = [
        SchoolCalendar(coordinator, entry),
        SchoolClassCalendar(coordinator, entry),
    ]

    async_add_entities(entities)


class SchoolCalendar(CoordinatorEntity, CalendarEntity):
    """학교 학사일정 캘린더"""
    _attr_has_entity_name = True
    _attr_translation_key = "school_academic"

    def __init__(
        self,
        coordinator: SchoolCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self.entry = entry
        self._attr_unique_id = f"{DOMAIN}_school_{entry.data['region_code']}_{entry.data['school_code']}_{entry.data['grade']}_calendar"

    @property
    def device_info(self) -> DeviceInfo:
        return school_device(self.entry)

    @property
    def event(self) -> CalendarEvent | None:
        """Return the next upcoming event."""
        if not self.coordinator.data:
            return None

        events = self.coordinator.data.get("calendar", [])
        if not events:
            return None

        now = datetime.now(KST)

        for event_data in events:
            try:
                if event_data["start"] >= now:
                    return CalendarEvent(
                        summary=event_data["summary"],
                        start=event_data["start"],
                        end=event_data["end"],
                    )
            except Exception:
                continue
        return None

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        """Return calendar events within a datetime range."""
        events: list[CalendarEvent] = []

        # Check if coordinator has data
        if not self.coordinator.data:
            return events

        calendar_events = self.coordinator.data.get("calendar", [])
        if not calendar_events:
            return events

        for event_data in calendar_events:
            try:
                event_start = event_data["start"]
                event_end = event_data["end"]

                # Filter events within the requested range
                if event_end >= start_date and event_start <= end_date:
                    events.append(
                        CalendarEvent(
                            summary=event_data["summary"],
                            start=event_start,
                            end=event_end,
                        )
                    )
            except Exception:
                # Skip malformed event data
                continue

        return events


class SchoolClassCalendar(CoordinatorEntity, CalendarEntity):
    """학급 시간표 캘린더"""
    _attr_has_entity_name = True
    _attr_translation_key = "school_class"

    def __init__(
        self,
        coordinator: SchoolCoordinator,
        entry: ConfigEntry,
        grade_class: str = "",
    ) -> None:
        super().__init__(coordinator)
        self.entry = entry
        self._gc = grade_class or "1-1"
        parts = self._gc.split("-")
        self._grade = parts[0] if parts else "1"
        self._cls = parts[1] if len(parts) > 1 else "1"
        self._attr_unique_id = f"{DOMAIN}_class_{entry.data['region_code']}_{entry.data['school_code']}_{self._gc}_schedule"
        self._attr_name = f"{self._grade}학년 {self._cls}반 시간표"

    @property
    def device_info(self) -> DeviceInfo:
        return school_device(self.entry)

    @property
    def event(self) -> CalendarEvent | None:
        """Return the next upcoming event."""
        if not self.coordinator.data:
            return None

        timetable = self.coordinator.data.get("timetable", {}).get(self._gc, [])
        if not timetable:
            return None

        period_times = self._get_period_times()
        now = datetime.now(KST)

        # Convert all timetable data to events and find the next one
        upcoming_events = []

        for day_schedule in timetable:
            try:
                day_date = date.fromisoformat(day_schedule["date"])

                for lesson in day_schedule["lessons"]:
                    period = lesson["period"]
                    subject = lesson["subject"]

                    if period not in period_times:
                        continue

                    start_t, end_t = period_times[period]
                    event_start = datetime.combine(day_date, start_t, tzinfo=KST)
                    event_end = datetime.combine(day_date, end_t, tzinfo=KST)

                    if event_start >= now:
                        upcoming_events.append((event_start, CalendarEvent(
                            summary=subject,
                            start=event_start,
                            end=event_end,
                        )))
            except Exception:
                continue

        if upcoming_events:
            upcoming_events.sort(key=lambda x: x[0])
            return upcoming_events[0][1]

        return None

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        events: list[CalendarEvent] = []

        # Check if coordinator has data
        if not self.coordinator.data:
            return events

        timetable = self.coordinator.data.get("timetable", {}).get(self._gc, [])
        if not timetable:
            return events

        period_times = self._get_period_times()

        # Get translated lunch text (defaults to Korean if translation unavailable)
        try:
            lunch_text = hass.localize("component.kr_public_data.calendar.school.lunch") or "점심시간"
        except Exception:
            lunch_text = "점심시간"

        lunch_start = self._parse_time(self.entry.data.get("lunch_start"))
        lunch_end = self._parse_time(self.entry.data.get("lunch_end"))

        for day_schedule in timetable:
            try:
                day_date = date.fromisoformat(day_schedule["date"])

                # Filter: only include dates within the requested range
                day_dt = datetime.combine(day_date, time.min, tzinfo=KST)
                if day_dt < start_date or day_dt > end_date:
                    continue

                # Add class periods
                for lesson in day_schedule["lessons"]:
                    period = lesson["period"]
                    subject = lesson["subject"]

                    if period not in period_times:
                        continue

                    start_t, end_t = period_times[period]

                    events.append(
                        CalendarEvent(
                            summary=subject,
                            start=datetime.combine(day_date, start_t, tzinfo=KST),
                            end=datetime.combine(day_date, end_t, tzinfo=KST),
                        )
                    )

                # Add lunch break for school days with lessons
                if lunch_start and lunch_end and day_schedule["lessons"]:
                    # Get lunch menu for this day
                    lunch_data = self.coordinator.data.get("lunch", {})
                    day_lunch = lunch_data.get(day_schedule["date"])

                    # Build lunch description with menu if available
                    lunch_description = None
                    if day_lunch and day_lunch.get("menu"):
                        menu_items = day_lunch["menu"]
                        lunch_description = "\n".join(menu_items)
                        if day_lunch.get("calorie"):
                            lunch_description += f"\n\n{day_lunch['calorie']}"

                    events.append(
                        CalendarEvent(
                            summary=lunch_text,
                            description=lunch_description,
                            start=datetime.combine(day_date, lunch_start, tzinfo=KST),
                            end=datetime.combine(day_date, lunch_end, tzinfo=KST),
                        )
                    )
            except Exception as e:
                # Skip malformed schedule data
                continue

        return events

    def _get_period_times(self) -> dict[int, tuple[time, time]]:
        result: dict[int, tuple[time, time]] = {}

        # 최대 10교시까지 지원
        for i in range(1, 11):
            key = f"period_{i}"
            value = self.entry.data.get(key)
            if not value:
                continue

            try:
                start_str, end_str = value.split("-")
                result[i] = (
                    self._parse_time(start_str),
                    self._parse_time(end_str),
                )
            except ValueError:
                continue

        return result

    @staticmethod
    def _parse_time(value: str | None) -> time | None:
        if not value:
            return None
        return datetime.strptime(value, "%H:%M").time()
