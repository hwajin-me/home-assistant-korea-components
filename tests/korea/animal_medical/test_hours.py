"""Date boundaries, breaks, overnight shifts, malformed hours and expiry."""

from datetime import datetime

import pytest

from custom_components.korea_incubator.animal_medical.hours import (
    SEOUL,
    _span,
    current_state,
    schedule,
)

STAMP = datetime(2026, 9, 21, 10, tzinfo=SEOUL)


@pytest.mark.parametrize(
    "reason",
    [
        "임시휴무",
        "비정기 휴무",
        "추석 휴무",
        "추석 연휴 휴진",
        "설날 휴무",
        "설 연휴 휴무",
        "공휴일 휴무",
        "대체공휴일 휴무",
        "정기 휴무",
    ],
)
def test_explicit_special_closure(reason):
    from custom_components.korea_incubator.animal_medical.closed_days import (
        upcoming_closed_days,
    )

    result = schedule(
        hours({"day_of_the_week_desc": "금(9/25)", "off_days_desc": reason}), STAMP
    )
    assert result["2026-09-25"] == {
        "open": None,
        "breaks": [],
        "closure_reason": reason,
    }
    assert [d.isoformat() for d in upcoming_closed_days(result, STAMP.date())] == [
        "2026-09-25"
    ]


@pytest.mark.parametrize(
    "reason",
    [
        "추석",
        "추석 정상영업",
        "추석 휴무 아님",
        "오후 휴무",
        "휴무 예정",
        "휴무 여부 문의",
    ],
)
def test_holiday_text_is_not_proof_of_closure(reason):
    result = schedule(
        hours({"day_of_the_week_desc": "금(9/25)", "off_days_desc": reason}), STAMP
    )
    assert result["2026-09-25"] is None


def test_holiday_opening_and_conflicting_information():
    assert schedule(hours(day("금(9/25)")), STAMP)["2026-09-25"]["open"] == [600, 1140]
    assert (
        schedule(hours({**day("금(9/25)"), "off_days_desc": "추석 휴무"}), STAMP)[
            "2026-09-25"
        ]
        is None
    )


def hours(*days):
    return {"week_from_today": {"week_periods": [{"days": list(days)}]}}


def day(label="월(9/21)", time="10:00 ~ 19:00", breaks=None):
    return {
        "day_of_the_week_desc": label,
        "on_days": {"start_end_time_desc": time, "break_times_desc": breaks or []},
    }


@pytest.mark.parametrize(
    "value",
    [
        "bad",
        None,
        "25:00 ~ 26:00",
        "10:60 ~ 19:00",
        "10:00 ~ 19:60",
        "10:00 ~ 24:01",
        "10:00 ~ 10:00",
    ],
)
def test_invalid_span(value):
    assert _span(value) is None


@pytest.mark.parametrize(
    "hour,minute,state",
    [
        (9, 59, "closed"),
        (10, 0, "open"),
        (12, 29, "open"),
        (12, 30, "break"),
        (13, 30, "open"),
        (18, 59, "open"),
        (19, 0, "closed"),
    ],
)
def test_boundaries(hour, minute, state):
    days = schedule(hours(day(breaks=["12:30 ~ 13:30 휴게시간"])), STAMP)
    assert current_state(days, STAMP.replace(hour=hour, minute=minute)) == state


def test_overnight_and_off_day():
    days = schedule(
        hours(
            day(time="22:00 ~ 03:00", breaks=["00:30 ~ 01:00 휴게시간"]),
            {"day_of_the_week_desc": "화(9/22)", "off_days_desc": "휴무일"},
        ),
        STAMP,
    )
    assert current_state(days, STAMP.replace(day=22, hour=0, minute=30)) == "break"
    assert current_state(days, STAMP.replace(day=22, hour=2)) == "open"
    assert current_state(days, STAMP.replace(day=22, hour=3)) == "closed"
    assert current_state(days, STAMP.replace(day=23)) is None
    assert current_state({}) is None


def test_round_the_clock_year_rollover_and_utc():
    stamp = datetime(2026, 12, 31, tzinfo=SEOUL)
    days = schedule(
        hours(day("목(12/31)", "24시간 영업"), day("금(1/1)", "00:00 ~ 24:00")), stamp
    )
    assert "2027-01-01" in days
    assert (
        current_state(days, datetime.fromisoformat("2026-12-31T16:00:00+00:00"))
        == "open"
    )


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"week_from_today": None},
        {"week_from_today": {"week_periods": None}},
        {"week_from_today": {"week_periods": [None, {}]}},
    ],
)
def test_missing_week(body):
    assert schedule(body, STAMP) == {}


@pytest.mark.parametrize("item", [None, {}, day("매주 월요일"), day("월(1/1)")])
def test_missing_dates(item):
    assert schedule(hours(item), STAMP) == {}


@pytest.mark.parametrize(
    "item",
    [
        {"day_of_the_week_desc": "월(9/21)"},
        day(time="예약 진료"),
        day(breaks=["휴게시간 상이"]),
        {**day(), "off_days_desc": "휴무"},
        {
            "day_of_the_week_desc": "월(9/21)",
            "on_days": {
                "start_end_time_desc": "10:00 ~ 19:00",
                "break_times_desc": None,
            },
        },
    ],
)
def test_ambiguous_hours(item):
    days = schedule(hours(item), STAMP)
    assert days == {"2026-09-21": None}
    assert current_state(days, STAMP) is None


def test_duplicate_dates_and_overnight_break_before_midnight():
    assert schedule(hours(day(), day()), STAMP) == {"2026-09-21": None}
    days = schedule(
        hours(day(time="20:00 ~ 02:00", breaks=["22:00 ~ 23:00 휴게시간"])), STAMP
    )
    assert current_state(days, STAMP.replace(hour=22)) == "break"
    assert current_state(days, STAMP.replace(hour=1)) is None


def test_break_outside_hours_and_unknown_off_description():
    assert schedule(hours(day(breaks=["20:00 ~ 21:00 휴게시간"])), STAMP) == {
        "2026-09-21": None
    }
    assert schedule(
        hours({"day_of_the_week_desc": "월(9/21)", "off_days_desc": "정보없음"}), STAMP
    ) == {"2026-09-21": None}
