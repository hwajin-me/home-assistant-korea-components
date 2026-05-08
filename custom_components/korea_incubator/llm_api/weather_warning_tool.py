"""Weather warning (기상특보) LLM tool."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm

from ..const import ENTRY_WEATHER
from ..weather import (
    AREA_CODES,
    EVENT_TYPE_KO,
    EVENT_TYPE_NONE,
    WARNING_TYPES,
)
from .base_tool import BaseKRTool
from .render import svg_card, svg_table

_WARN_ACCENT_ACTIVE = "#dc2626"   # red
_WARN_ACCENT_INACTIVE = "#64748b"  # slate


class GetWeatherWarningsTool(BaseKRTool):
    service = ENTRY_WEATHER
    name = "get_weather_warnings"
    description = (
        "Return KMA severe weather warnings (호우, 폭염, 한파, 강풍, 태풍, "
        "황사, 대설 등) currently active in the configured area(s)."
    )
    parameters = vol.Schema({})

    async def async_call(
        self,
        hass: HomeAssistant,
        tool_input: llm.ToolInput,
        llm_context: llm.LLMContext,
    ) -> dict[str, Any]:
        store = self.store
        coord = store.get("coordinator")
        area_codes = store.get("area_codes", [])
        if coord is None or coord.data is None:
            return self.error("기상특보 데이터가 아직 준비되지 않았습니다.")

        active: list[dict[str, Any]] = []
        for ac in area_codes:
            area_data = coord.data.get(ac, {})
            for wt, payload in area_data.items():
                etype = payload.get("event_type")
                if not etype or etype == EVENT_TYPE_NONE:
                    continue
                key, ko_name, _ = WARNING_TYPES.get(wt, ("", "", ""))
                active.append({
                    "area_code": ac,
                    "area_name": AREA_CODES.get(ac, ac),
                    "warning_type": key,
                    "warning_name_ko": ko_name,
                    "event_type": etype,
                    "event_type_ko": EVENT_TYPE_KO.get(etype, etype),
                    "start_time": payload.get("start_time"),
                    "end_time": payload.get("end_time"),
                })

        if not active:
            featured = svg_card(
                "기상특보",
                [],
                subtitle="활성 특보 없음",
                accent=_WARN_ACCENT_INACTIVE,
                big_value="안전",
                big_value_caption="현재 발효 중인 특보가 없습니다.",
            )
            return self.envelope(
                active_count=0,
                warnings=[],
                featured_image=featured,
                instruction=(
                    "Tell the user there are no active KMA weather warnings "
                    "for the configured area(s)."
                ),
            )

        rows = [
            [
                w["warning_name_ko"],
                w["event_type_ko"],
                w["area_name"],
                (w.get("start_time") or "")[:16].replace("T", " "),
            ]
            for w in active
        ]
        featured = svg_table(
            "활성 기상특보",
            ["종류", "단계", "지역", "발효 시각"],
            rows,
            subtitle=f"활성 {len(active)}건",
            accent=_WARN_ACCENT_ACTIVE,
        )
        return self.envelope(
            active_count=len(active),
            warnings=active,
            featured_image=featured,
            instruction=(
                "Summarise the active Korean weather warnings briefly — a "
                "table is shown. Translate event_type_ko (주의보=advisory, "
                "경보=warning) into the user's language. Mention the "
                "affected area names."
            ),
        )
