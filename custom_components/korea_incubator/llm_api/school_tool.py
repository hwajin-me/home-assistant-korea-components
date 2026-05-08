"""School lunch + timetable LLM tools (NEIS Open API)."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm

from ..const import ENTRY_SCHOOL
from ..school import ALLERGY_MAP
from .base_tool import BaseKRTool
from .render import svg_card, svg_table

_SCHOOL_ACCENT = "#0ea5e9"   # sky
_MEAL_ACCENT = "#84cc16"     # lime


def _resolve_iso_date(when: str) -> str | None:
    today = date.today()
    if when == "today":
        return today.isoformat()
    if when == "tomorrow":
        return (today + timedelta(days=1)).isoformat()
    try:
        return datetime.strptime(when, "%Y-%m-%d").date().isoformat()
    except ValueError:
        return None


class GetSchoolMealTool(BaseKRTool):
    service = ENTRY_SCHOOL
    name = "get_school_meal"
    description = (
        "Return the school lunch menu (NEIS) for a date. Pass 'today', "
        "'tomorrow', or an ISO date (YYYY-MM-DD)."
    )
    parameters = vol.Schema(
        {
            vol.Required(
                "when",
                description="'today', 'tomorrow', or 'YYYY-MM-DD'.",
            ): str,
        }
    )

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> dict[str, Any]:
        store = self.store
        coord = store.get("coordinator")
        if coord is None or coord.data is None:
            return self.error("학교 데이터가 아직 준비되지 않았습니다.")

        iso = _resolve_iso_date(tool_input.tool_args["when"])
        if iso is None:
            return self.error("when 형식이 올바르지 않습니다.")

        lunch = (coord.data.get("lunch") or {}).get(iso)
        if not lunch:
            return self.envelope(
                date=iso,
                message="해당 날짜의 급식 정보가 없습니다.",
            )

        menu = lunch.get("menu") or []
        codes = lunch.get("allergy_codes") or []
        allergy_names = [ALLERGY_MAP[c] for c in codes if c in ALLERGY_MAP]
        # Use the first 6 menu items as the visible card lines
        lines: list[tuple[str, str]] = [
            (f"{i + 1}", item) for i, item in enumerate(menu[:6])
        ]
        if allergy_names:
            lines.append(("알레르기", ", ".join(allergy_names)))
        featured = svg_card(
            "급식",
            lines,
            subtitle=iso,
            accent=_MEAL_ACCENT,
            big_value=lunch.get("calorie") or "-",
            big_value_caption="총 칼로리",
        )

        return self.envelope(
            date=iso,
            menu=menu,
            calorie=lunch.get("calorie"),
            allergy_codes=codes,
            allergens=allergy_names,
            featured_image=featured,
            instruction=(
                "Read out the school lunch menu naturally. Mention the "
                "calorie total if present, and warn about the allergens "
                "(Korean names in the 'allergens' field) if any. A card "
                "is shown — keep it brief."
            ),
        )


class GetSchoolTimetableTool(BaseKRTool):
    service = ENTRY_SCHOOL
    name = "get_school_timetable"
    description = (
        "Return the class timetable for a configured grade-class on a "
        "given date."
    )
    parameters = vol.Schema(
        {
            vol.Required(
                "when",
                description="'today', 'tomorrow', or 'YYYY-MM-DD'.",
            ): str,
            vol.Optional(
                "grade_class",
                description=(
                    "Configured grade-class string (e.g. '1-3'). Omit to "
                    "use the first configured class."
                ),
            ): str,
        }
    )

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> dict[str, Any]:
        store = self.store
        coord = store.get("coordinator")
        if coord is None or coord.data is None:
            return self.error("학교 데이터가 아직 준비되지 않았습니다.")

        iso = _resolve_iso_date(tool_input.tool_args["when"])
        if iso is None:
            return self.error("when 형식이 올바르지 않습니다.")

        timetables: dict[str, list[dict]] = coord.data.get("timetable") or {}
        if not timetables:
            return self.error("등록된 학년-반이 없습니다.")

        wanted = tool_input.tool_args.get("grade_class")
        if wanted is None:
            gc = next(iter(timetables.keys()))
        elif wanted in timetables:
            gc = wanted
        else:
            return self.error(f"'{wanted}' 학년-반이 등록되어 있지 않습니다.")

        day = next(
            (d for d in timetables[gc] if d.get("date") == iso),
            None,
        )
        if not day:
            return self.envelope(
                date=iso,
                grade_class=gc,
                message="해당 날짜의 시간표가 없습니다.",
            )

        lessons = day.get("lessons") or []
        rows = [[str(l.get("period") or ""), l.get("subject") or ""] for l in lessons]
        featured = svg_table(
            "시간표",
            ["교시", "과목"],
            rows,
            subtitle=f"{iso} · {gc}",
            accent=_SCHOOL_ACCENT,
            empty_message="해당 날짜의 시간표가 없습니다.",
        )

        return self.envelope(
            date=iso,
            grade_class=gc,
            lessons=lessons,
            featured_image=featured,
            instruction=(
                "List the lessons in order. Mention the period number "
                "and subject for each. A table is shown — keep it brief."
            ),
        )
