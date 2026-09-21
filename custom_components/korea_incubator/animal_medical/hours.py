"""Conservative evaluation of date-specific Korean opening hours in Seoul time."""

import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

SEOUL = ZoneInfo("Asia/Seoul")


def valid_schedule(days):
    """Validate persisted schedules before they reach minute-level state callbacks."""
    if not isinstance(days, dict):
        return False
    try:
        for key, day in days.items():
            date.fromisoformat(key)
            if day is None:
                continue
            opening, breaks = day["open"], day["breaks"]
            if not isinstance(breaks, list):
                return False
            if opening is None:
                if breaks:
                    return False
                continue
            for span in [opening, *breaks]:
                if (
                    not isinstance(span, list)
                    or len(span) != 2
                    or any(type(n) is not int for n in span)
                ):
                    return False
                if not 0 <= span[0] < span[1] <= 2880:
                    return False
            if opening[0] >= 1440 or opening[1] - opening[0] > 1440:
                return False
            if any(
                not opening[0] <= start < end <= opening[1] for start, end in breaks
            ):
                return False
        return True
    except (KeyError, TypeError, ValueError):
        return False


def _span(text, suffix=""):
    match = re.fullmatch(
        r"\s*(\d{1,2}):(\d{2})\s*~\s*(\d{1,2}):(\d{2})\s*" + suffix, str(text)
    )
    if not match:
        return None
    h1, m1, h2, m2 = map(int, match.groups())
    if h1 > 23 or h2 > 24 or m1 > 59 or m2 > 59 or (h2 == 24 and m2):
        return None
    start, end = h1 * 60 + m1, h2 * 60 + m2
    if start == end:
        return None
    return [start, end + 1440 if end < start else end]


def schedule(hours, fetched_at):
    """Resolve month/day labels to actual dates, never assume weekly recurrence."""
    today = fetched_at.astimezone(SEOUL).date()
    result = {}
    week = hours.get("week_from_today", {})
    if not isinstance(week, dict) or not isinstance(week.get("week_periods"), list):
        return result
    for period in week["week_periods"]:
        if not isinstance(period, dict) or not isinstance(period.get("days"), list):
            continue
        for day in period["days"]:
            if not isinstance(day, dict):
                continue
            match = re.fullmatch(
                r"[월화수목금토일]\((\d{1,2})/(\d{1,2})\)",
                str(day.get("day_of_the_week_desc", "")),
            )
            if not match:
                continue
            date = next(
                (
                    today + timedelta(days=n)
                    for n in range(7)
                    if (
                        (today + timedelta(days=n)).month,
                        (today + timedelta(days=n)).day,
                    )
                    == tuple(map(int, match.groups()))
                ),
                None,
            )
            if date is None:
                continue
            key = date.isoformat()
            # An ambiguous duplicate date must not silently overwrite earlier data.
            if key in result:
                result[key] = None
                continue
            on = day.get("on_days")
            if not on and re.fullmatch(
                r"(?:정기\s*)?(?:휴무일|휴무|휴진|휴일)",
                str(day.get("off_days_desc", "")),
            ):
                result[key] = {"open": None, "breaks": []}
                continue
            if not isinstance(on, dict):
                result[key] = None
                continue
            opening = _span(on.get("start_end_time_desc"))
            if on.get("start_end_time_desc") in ("24시간", "24시간 영업"):
                opening = [0, 1440]
            breaks = on.get("break_times_desc", [])
            if not isinstance(breaks, list):
                result[key] = None
                continue
            parsed = [_span(value, r"(?:휴게시간|브레이크타임)\s*") for value in breaks]
            if (
                opening is None
                or any(value is None for value in parsed)
                or day.get("off_days_desc")
            ):
                result[key] = None
            else:
                # Breaks after midnight belong to the second half of an overnight shift.
                for value in parsed:
                    if opening[1] > 1440 and value[0] < opening[0]:
                        value[0] += 1440
                        value[1] += 1440
                result[key] = (
                    {"open": opening, "breaks": parsed}
                    if all(
                        opening[0] <= start < end <= opening[1] for start, end in parsed
                    )
                    else None
                )
    return result


def current_state(days, now=None):
    """Return open/closed/break or unknown; date coverage expires naturally."""
    now = (now or datetime.now(SEOUL)).astimezone(SEOUL)
    minute = now.hour * 60 + now.minute
    today = days.get(now.date().isoformat())
    yesterday = days.get((now.date() - timedelta(days=1)).isoformat())
    if yesterday and yesterday["open"] and yesterday["open"][1] > minute + 1440:
        if any(start <= minute + 1440 < end for start, end in yesterday["breaks"]):
            return "break"
        return "open"
    if today is None:
        return None
    if (
        yesterday is None
        and today["open"]
        and today["open"][1] > 1440
        and minute < today["open"][0]
    ):
        return None  # First-ever early-morning fetch cannot infer yesterday's shift.
    if not today["open"] or not today["open"][0] <= minute < today["open"][1]:
        return "closed"
    if any(start <= minute < end for start, end in today["breaks"]):
        return "break"
    return "open"
