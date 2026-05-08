"""AirKorea air quality LLM tool."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm

from ..airkorea import STAG_GRADES, UV_GRADES
from ..const import ENTRY_AIRKOREA
from .base_tool import BaseKRTool
from .render import svg_table

_AIR_ACCENT = "#22c55e"  # green; will tint via grade in caller
_PM_GRADE_KO = {"1": "좋음", "2": "보통", "3": "나쁨", "4": "매우나쁨"}


def _grade(value: Any, table: list[tuple[int, str]]) -> str | None:
    if value is None:
        return None
    try:
        v = float(value)
    except (ValueError, TypeError):
        return None
    for threshold, label in table:
        if v <= threshold:
            return label
    return table[-1][1]


class GetAirQualityTool(BaseKRTool):
    service = ENTRY_AIRKOREA
    name = "get_air_quality"
    description = (
        "Return realtime air quality (PM10, PM2.5, ozone, NO2, CO, SO2) "
        "for the configured AirKorea stations, plus today's forecast grade, "
        "UV index and atmospheric stagnation index."
    )
    parameters = vol.Schema(
        {
            vol.Optional(
                "station_name",
                description=(
                    "Configured station name (e.g. '강남구'). Omit to "
                    "return all configured stations."
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
            return self.error("대기질 데이터가 아직 준비되지 않았습니다.")

        wanted = tool_input.tool_args.get("station_name")
        stations_data: dict[str, Any] = coord.data.get("stations", {})

        if wanted:
            if wanted not in stations_data:
                return self.error(f"'{wanted}' 측정소가 등록되어 있지 않습니다.")
            station_iter = [(wanted, stations_data[wanted])]
        else:
            station_iter = list(stations_data.items())

        stations_out: list[dict[str, Any]] = []
        for name, data in station_iter:
            if not data:
                continue
            stations_out.append({
                "station": name,
                "datetime": data.get("dataTime"),
                "pm10": data.get("pm10Value"),
                "pm10_grade": data.get("pm10Grade1h") or data.get("pm10Grade"),
                "pm25": data.get("pm25Value"),
                "pm25_grade": data.get("pm25Grade1h") or data.get("pm25Grade"),
                "o3": data.get("o3Value"),
                "no2": data.get("no2Value"),
                "co": data.get("coValue"),
                "so2": data.get("so2Value"),
                "khai_value": data.get("khaiValue"),
                "khai_grade": data.get("khaiGrade"),
            })

        forecast = coord.data.get("forecast") or []
        forecast_out = [
            {
                "date": f.get("dataTime"),
                "informCode": f.get("informCode"),
                "informGrade": f.get("informGrade"),
                "informOverall": f.get("informOverall"),
                "informCause": f.get("informCause"),
            }
            for f in forecast[:3]
        ]

        uv = coord.data.get("uv") or {}
        uv_now = uv.get("h0") or uv.get("today")
        stag = coord.data.get("stagnation") or {}
        stag_now = stag.get("h0") or stag.get("today")

        rows = [
            [
                s["station"],
                s.get("pm10") or "-",
                _PM_GRADE_KO.get(str(s.get("pm10_grade") or ""), "-"),
                s.get("pm25") or "-",
                _PM_GRADE_KO.get(str(s.get("pm25_grade") or ""), "-"),
                s.get("o3") or "-",
            ]
            for s in stations_out
        ]
        # Worst grade among stations sets accent
        worst_grade = max(
            (int(s.get("pm25_grade") or 0) for s in stations_out if s.get("pm25_grade")),
            default=0,
        )
        accent = {1: "#22c55e", 2: "#facc15", 3: "#fb923c", 4: "#ef4444"}.get(
            worst_grade, "#22c55e"
        )
        subtitle_bits = []
        if uv_now is not None:
            subtitle_bits.append(f"UV {uv_now} ({_grade(uv_now, UV_GRADES) or '-'})")
        if stag_now is not None:
            subtitle_bits.append(
                f"대기정체 {stag_now} ({_grade(stag_now, STAG_GRADES) or '-'})"
            )
        featured = svg_table(
            "대기질",
            ["측정소", "PM10", "PM10등급", "PM2.5", "PM2.5등급", "O3"],
            rows,
            subtitle=" · ".join(subtitle_bits) if subtitle_bits else None,
            accent=accent,
            empty_message="측정소 데이터가 없습니다.",
        )

        return self.envelope(
            stations=stations_out,
            forecast=forecast_out,
            uv_index=uv_now,
            uv_grade=_grade(uv_now, UV_GRADES),
            stagnation=stag_now,
            stagnation_grade=_grade(stag_now, STAG_GRADES),
            featured_image=featured,
            instruction=(
                "Summarise the air quality naturally. Korean grades (좋음/"
                "보통/나쁨/매우나쁨) describe PM10/PM2.5; translate them. "
                "Mention UV and stagnation only if they are notable. A "
                "table is shown — keep your reply brief."
            ),
        )
