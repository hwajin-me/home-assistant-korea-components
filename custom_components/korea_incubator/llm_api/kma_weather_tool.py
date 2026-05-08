"""KMA weather forecast LLM tool.

Returns a payload shaped like voice-satellite-card-llm-tools'
``get_weather_forecast``, so the voice-satellite card renders the
built-in weather panel (matched by ``toolName.endsWith('get_weather_forecast')
&& toolResult.forecast``).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm

from ..const import ENTRY_KMA_WEATHER
from .base_tool import BaseKRTool

_LOGGER = logging.getLogger(__name__)

RANGE_OPTIONS = [
    "week",
    "today",
    "tomorrow",
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]
DAY_NAMES = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]

PRECIPITATION_THRESHOLDS = [
    (0, "no chance"),
    (5, "very unlikely"),
    (15, "unlikely"),
    (30, "possible"),
    (50, "moderate"),
    (70, "likely"),
    (85, "very likely"),
    (95, "extremely likely"),
    (100, "almost guaranteed"),
]


def _describe_precipitation(prob: Any) -> str | None:
    if prob is None:
        return None
    try:
        p = int(prob)
    except (ValueError, TypeError):
        return None
    for threshold, desc in PRECIPITATION_THRESHOLDS:
        if p <= threshold:
            return desc
    return "almost guaranteed"


def _resolve_target_date(range_value: str, today):
    if range_value == "week":
        return None
    if range_value == "today":
        return today
    if range_value == "tomorrow":
        return today + timedelta(days=1)
    if range_value in DAY_NAMES:
        idx = DAY_NAMES.index(range_value)
        days_ahead = (idx - today.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7
        return today + timedelta(days=days_ahead)
    return today


class GetKMAWeatherForecastTool(BaseKRTool):
    """KMA village forecast packaged as a voice-satellite weather payload."""

    service = ENTRY_KMA_WEATHER
    source = "kma"  # used by base envelope; voice-satellite ignores the value
    name = "get_weather_forecast"
    description = (
        "Get the weather forecast from the Korean Meteorological "
        "Administration (KMA). 'today'/'tomorrow' or a weekday name returns "
        "hourly entries for that day; 'week' returns a daily outlook."
    )

    parameters = vol.Schema(
        {
            vol.Required(
                "range",
                description=(
                    "'week', 'today', 'tomorrow', or a day name "
                    "(monday-sunday)."
                ),
            ): vol.In(RANGE_OPTIONS),
            vol.Optional(
                "region_name",
                description=(
                    "Configured region name to look up. Omit to use the "
                    "first configured region."
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
        range_value = tool_input.tool_args["range"]
        wanted_region = tool_input.tool_args.get("region_name")

        store = self.store
        coord = store.get("coordinator")
        regions = store.get("regions", [])
        if coord is None or not coord.data:
            return self.error("기상청 데이터가 아직 준비되지 않았습니다.")

        # Resolve region
        region_name = None
        if wanted_region and wanted_region in coord.data:
            region_name = wanted_region
        else:
            for r in regions:
                if r.get("name") in coord.data:
                    region_name = r["name"]
                    break
            if region_name is None and coord.data:
                region_name = next(iter(coord.data.keys()))
        if region_name is None:
            return self.error("등록된 지역이 없습니다.")

        region_data = coord.data.get(region_name) or {}
        hourly = region_data.get("hourly_forecasts") or []
        daily = region_data.get("daily_forecasts") or []

        today = datetime.now().date()
        target_date = _resolve_target_date(range_value, today)

        if range_value == "week":
            entries = daily[:7]
            forecast_type = "daily"
            formatted = self._format_daily(entries)
        else:
            filtered = [
                h for h in hourly
                if h.get("datetime", "")[:10] == (target_date.isoformat() if target_date else "")
            ]
            if filtered:
                forecast_type = "hourly"
                formatted = self._format_hourly(filtered)
            else:
                # Fall back to the daily summary entry for that date
                day_entry = next(
                    (d for d in daily if d.get("datetime") == target_date.isoformat()),
                    None,
                )
                if not day_entry:
                    return self.envelope(
                        range=range_value,
                        region=region_name,
                        message="해당 날짜의 예보 데이터를 찾을 수 없습니다.",
                    )
                forecast_type = "daily"
                formatted = self._format_daily([day_entry])

        if not formatted:
            return self.envelope(
                range=range_value,
                region=region_name,
                message="해당 범위의 예보 데이터가 없습니다.",
            )

        response: dict[str, Any] = {
            "source": "kma",
            "service": self.service,
            "range": range_value,
            "region": region_name,
            "forecast_type": forecast_type,
            "forecast": formatted,
            "instruction": (
                "Summarize this Korean weather forecast naturally in the "
                "user's language. Mention temperatures, conditions, and "
                "precipitation chance. If current temperature/humidity are "
                "provided, include them. Do NOT list raw numbers verbatim — "
                "give a short conversational summary."
            ),
        }

        # Current conditions (only meaningful for today / week views)
        if range_value in ("today", "week"):
            cur_temp = region_data.get("temperature")
            cur_hum = region_data.get("humidity")
            if cur_temp is not None:
                response["current_temperature"] = f"{round(float(cur_temp))}°C"
            if cur_hum is not None:
                response["current_humidity"] = f"{round(float(cur_hum))}%"

        return response

    @staticmethod
    def _format_hourly(entries: list[dict]) -> list[dict]:
        formatted = []
        for entry in entries:
            dt_str = entry.get("datetime", "")
            item: dict[str, Any] = {}
            if dt_str:
                try:
                    dt = datetime.fromisoformat(dt_str)
                    item["time"] = dt.strftime("%-I%p").lower()
                except (ValueError, TypeError):
                    item["datetime"] = dt_str

            item["condition"] = entry.get("condition", "")
            t = entry.get("temperature")
            if t is not None:
                item["temperature"] = str(round(t))
            desc = _describe_precipitation(entry.get("precipitation_probability"))
            if desc:
                item["precipitation"] = desc
            if entry.get("humidity") is not None:
                item["humidity"] = f"{round(entry['humidity'])}%"
            if entry.get("wind_speed") is not None:
                item["wind_speed"] = entry["wind_speed"]
            formatted.append(item)
        return formatted

    @staticmethod
    def _format_daily(entries: list[dict]) -> list[dict]:
        formatted = []
        for entry in entries:
            item: dict[str, Any] = {}
            dt_str = entry.get("datetime", "")
            if dt_str:
                try:
                    dt = datetime.fromisoformat(dt_str)
                    item["date"] = dt.strftime("%A")
                except (ValueError, TypeError):
                    item["datetime"] = dt_str

            item["condition"] = entry.get("condition", "")
            templow = entry.get("templow")
            temphigh = entry.get("temphigh")
            if templow is not None and temphigh is not None:
                item["temperature"] = f"{round(templow)} - {round(temphigh)}"
            elif entry.get("temperature") is not None:
                item["temperature"] = str(round(entry["temperature"]))

            desc = _describe_precipitation(entry.get("precipitation_probability"))
            if desc:
                item["precipitation"] = desc
            if entry.get("humidity") is not None:
                item["humidity"] = f"{round(entry['humidity'])}%"
            if entry.get("wind_speed") is not None:
                item["wind_speed"] = entry["wind_speed"]
            formatted.append(item)
        return formatted
