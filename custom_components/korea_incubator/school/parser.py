"""Parsers for NEIS API data."""
import re
from datetime import datetime, date
from zoneinfo import ZoneInfo
from typing import Any

from . import ALLERGY_MAP

# 한국 표준시 (KST)
KST = ZoneInfo("Asia/Seoul")

ALLERGY_REGEX = re.compile(r"\(([\d.,\s]+)\)")

def parse_timetable(api_data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Parse NEIS timetable API data.

    Args:
        api_data: List of timetable rows from NEIS API

    Returns:
        List of daily schedules:
        [
            {
                "date": "2025-12-25",
                "day_of_week": 3,  # 0=Monday, 6=Sunday
                "lessons": [
                    {"period": 1, "subject": "국어"},
                    {"period": 2, "subject": "수학"},
                    ...
                ]
            },
            ...
        ]
    """
    # Group by date
    schedule_by_date = {}

    for row in api_data:
        # Parse date (ALL_TI_YMD format: YYYYMMDD)
        date_str = row.get("ALL_TI_YMD", "")
        if not date_str or len(date_str) != 8:
            continue

        try:
            dt = datetime.strptime(date_str, "%Y%m%d").replace(tzinfo=KST)
            iso_date = dt.date().isoformat()
            day_of_week = dt.weekday()
        except ValueError:
            continue

        # Get period and subject
        try:
            period = int(row.get("PERIO", 0))
            subject = row.get("ITRT_CNTNT", "").strip()

            if not subject:
                continue

        except (ValueError, AttributeError):
            continue

        # Initialize date entry if needed
        if iso_date not in schedule_by_date:
            schedule_by_date[iso_date] = {
                "date": iso_date,
                "day_of_week": day_of_week,
                "lessons": [],
            }

        # Add lesson
        schedule_by_date[iso_date]["lessons"].append({
            "period": period,
            "subject": subject,
        })

    # Sort lessons by period within each day
    for schedule in schedule_by_date.values():
        schedule["lessons"].sort(key=lambda x: x["period"])

    # Return sorted by date
    return sorted(schedule_by_date.values(), key=lambda x: x["date"])


def parse_school_calendar(api_data: list[dict[str, Any]], user_grade: int | None = None) -> list[dict[str, Any]]:
    """
    Parse NEIS school schedule API data.

    Args:
        api_data: List of schedule rows from NEIS API
        user_grade: User's grade number (1-6) to add grade indicators to event summaries

    Returns:
        List of calendar events with grade indicators in summary
    """
    # Map grade number to API field name
    GRADE_FIELDS = {
        1: "ONE_GRADE_EVENT_YN",
        2: "TW_GRADE_EVENT_YN",
        3: "THREE_GRADE_EVENT_YN",
        4: "FR_GRADE_EVENT_YN",      # Elementary only
        5: "FIV_GRADE_EVENT_YN",     # Elementary only
        6: "SIX_GRADE_EVENT_YN",     # Elementary only
    }

    events = []

    for row in api_data:
        # Parse date (AA_YMD format: YYYYMMDD)
        date_str = row.get("AA_YMD", "")
        if not date_str or len(date_str) != 8:
            continue

        try:
            dt = datetime.strptime(date_str, "%Y%m%d").replace(tzinfo=KST)
        except ValueError:
            continue

        # Get event name
        summary = row.get("EVENT_NM", "").strip()
        if not summary:
            continue

        # Determine which grades this event applies to
        applies_to_grades = []
        for grade, field_name in GRADE_FIELDS.items():
            if row.get(field_name, "N").strip().upper() == "Y":
                applies_to_grades.append(grade)

        # Add grade indicator if event is for specific grades that don't include the user
        if applies_to_grades and user_grade is not None:
            if user_grade not in applies_to_grades:
                # Event applies to other specific grades - add label
                grade_str = ",".join(str(g) for g in sorted(applies_to_grades))
                summary = f"[{grade_str}] {summary}"

        events.append({
            "summary": summary,
            "start": dt,
            "end": dt.replace(hour=23, minute=59),
            "all_day": True,
        })

    return events


def parse_lunch_menu(api_data: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """
    Parse NEIS meal service API data.

    Args:
        api_data: List of meal rows from NEIS API

    Returns:
        Dict keyed by date:
        {
            "2025-12-25": {
                "date": "2025-12-25",
                "menu": ["밥", "국", "반찬"],
                "calorie": "650.5 Kcal",
                "allergy": {1: "allergy.egg", ...},
                "allergy_codes": [1, 2, 5],
                "raw_text": "...",
                "source": "NEIS Open API",
            },
            ...
        }
    """
    lunch_by_date = {}

    for row in api_data:
        # Parse date (MLSV_YMD format: YYYYMMDD)
        date_str = row.get("MLSV_YMD", "")
        if not date_str or len(date_str) != 8:
            continue

        try:
            dt = datetime.strptime(date_str, "%Y%m%d")
            iso_date = dt.date().isoformat()
        except ValueError:
            continue

        # Get meal dish name (DDISH_NM) - contains menu with allergy codes
        dish_name = row.get("DDISH_NM", "")
        if not dish_name:
            continue

        # Parse menu items and allergy codes
        # Menu items are separated by <br/> in the API response
        menu_items = []
        raw_text_items = []
        allergy_codes = set()

        for line in dish_name.split("<br/>"):
            line = line.strip()
            if not line:
                continue

            raw_text_items.append(line)

            # Extract allergy codes (format: "메뉴명 (1.2.5)")
            match = ALLERGY_REGEX.search(line)
            if match:
                # Parse allergy codes
                codes_str = match.group(1)
                for code in codes_str.replace(" ", "").split("."):
                    if code.isdigit():
                        allergy_codes.add(int(code))

            # Remove allergy codes from menu item
            clean_item = ALLERGY_REGEX.sub("", line).strip()
            if clean_item:
                menu_items.append(clean_item)

        # Get calorie info (CAL_INFO)
        calorie = row.get("CAL_INFO", "").strip()

        lunch_by_date[iso_date] = {
            "date": iso_date,
            "menu": menu_items,
            "calorie": calorie,
            "allergy": {
                code: ALLERGY_MAP.get(code, "allergy.unknown")
                for code in sorted(allergy_codes)
            },
            "allergy_codes": sorted(allergy_codes),
            "raw_text": " ".join(raw_text_items),
            "source": "NEIS Open API",
        }

    return lunch_by_date


def parse_school_info(api_data: dict[str, Any]) -> dict[str, str]:
    """
    Parse NEIS school info API data.

    Args:
        api_data: School info row from NEIS API

    Returns:
        {
            "school_name": str,
            "address": str,
            "phone": str,
            "fax": str,
            "region_code": str,
            "school_code": str,
        }
    """
    return {
        "school_name": api_data.get("SCHUL_NM", "Unknown School").strip(),
        "address": api_data.get("ORG_RDNMA", "").strip(),  # Road address
        "phone": api_data.get("ORG_TELNO", "").strip(),
        "fax": api_data.get("ORG_FAXNO", "").strip(),
        "region_code": api_data.get("ATPT_OFCDC_SC_CODE", "").strip(),
        "school_code": api_data.get("SD_SCHUL_CODE", "").strip(),
    }


def parse_class_info(api_data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Parse NEIS class info API data (for high school).

    Args:
        api_data: List of class info rows from NEIS API

    Returns:
        List of class information:
        [
            {
                "grade": int,
                "class_num": int,
                "class_name": str,
            },
            ...
        ]
    """
    classes = []

    for row in api_data:
        try:
            grade = int(row.get("GRADE", 1))
            class_num = int(row.get("CLASS_NM", 1))
            class_name = row.get("DDDEP_NM", "").strip()  # Department name

            classes.append({
                "grade": grade,
                "class_num": class_num,
                "class_name": class_name,
            })
        except (ValueError, AttributeError):
            continue

    return classes
