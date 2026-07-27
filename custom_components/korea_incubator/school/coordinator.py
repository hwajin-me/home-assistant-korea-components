"""School data coordinator - supports multiple grade+class combos."""
from __future__ import annotations
import logging
from datetime import timedelta, datetime, date
from zoneinfo import ZoneInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from ..const import DOMAIN
from .api import NeisApiClient
from .parser import parse_lunch_menu, parse_school_calendar, parse_timetable

_LOGGER = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")

def _school_year_mondays(ref=None):
    ref = ref or datetime.now(KST).date()
    start = date(ref.year - 1, 3, 1) if ref.month <= 2 else date(ref.year, 3, 1)
    end = date(start.year + 1, 2, 28)
    cur = start
    while cur.weekday() != 0:
        cur += timedelta(days=1)
    mondays = []
    while cur <= end:
        mondays.append(cur)
        cur += timedelta(days=7)
    return mondays


class SchoolCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry):
        self.entry = entry
        self.client = NeisApiClient(async_get_clientsession(hass), entry.data["api_key"])
        self.rc = entry.data["region_code"]
        self.sc = entry.data["school_code"]
        self.level = entry.data["school_level"]
        # Parse grade_classes: ["1-3", "3-1"] format
        self.grade_classes = entry.data.get("grade_classes", [])
        if not self.grade_classes:
            g = entry.data.get("grade", 1)
            cls_list = entry.data.get("classes", [str(entry.data.get("class", "1"))])
            self.grade_classes = [f"{g}-{c}" for c in cls_list]
        # All unique grades for calendar
        self.grades = list(set(gc.split("-")[0] for gc in self.grade_classes))
        super().__init__(hass, _LOGGER, name=f"{DOMAIN}_school_{entry.entry_id}",
                         update_interval=timedelta(hours=6))

    async def _async_update_data(self):
        try:
            mondays = _school_year_mondays()
            sy_start = mondays[0]
            sy_end = mondays[-1] + timedelta(days=6)

            lunch = await self.client.get_meal(self.rc, self.sc, sy_start, sy_end)

            cal = []
            cur = sy_start
            while cur <= sy_end:
                try:
                    cal.extend(await self.client.get_schedule_month(
                        self.rc, self.sc, cur.year, cur.month))
                except Exception:
                    pass
                cur = date(cur.year + (1 if cur.month == 12 else 0),
                           1 if cur.month == 12 else cur.month + 1, 1)

            # Timetable per grade-class combo
            timetables = {}
            for gc in self.grade_classes:
                g, cl = gc.split("-")
                tt = []
                for mon in mondays:
                    try:
                        tt.extend(await self.client.get_timetable(
                            self.rc, self.sc, self.level, int(g), cl,
                            mon, mon + timedelta(days=6)))
                    except Exception:
                        pass
                timetables[gc] = parse_timetable(tt)

            # Use first grade for calendar filtering
            first_grade = int(self.grades[0]) if self.grades else 1
            return {
                "lunch": parse_lunch_menu(lunch),
                "timetable": timetables,
                "calendar": parse_school_calendar(cal, user_grade=first_grade),
            }
        except Exception as e:
            raise UpdateFailed(f"학교 데이터 갱신 실패: {e}") from e
