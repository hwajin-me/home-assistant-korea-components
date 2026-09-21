"""Explicit full-day closures; no inference outside the supplied date coverage."""

from datetime import date, timedelta

from .hours import valid_schedule


def closed_day_status(days, requested):
    """None is unknown; an overnight opening from yesterday rules out full closure."""
    if not valid_schedule(days):
        return None
    yesterday = (
        days.get((requested - timedelta(days=1)).isoformat())
        if requested > date.min
        else None
    )
    if yesterday and yesterday["open"] and yesterday["open"][1] > 1440:
        return False
    today = days.get(requested.isoformat())
    if today is None:
        return None
    return today["open"] is None


def upcoming_closed_days(days, today):
    if not valid_schedule(days):
        return []
    return sorted(
        date.fromisoformat(key)
        for key in days
        if date.fromisoformat(key) >= today
        and closed_day_status(days, date.fromisoformat(key)) is True
    )
