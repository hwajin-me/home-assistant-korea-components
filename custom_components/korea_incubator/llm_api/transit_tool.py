"""Transit (Seoul subway + KakaoMap bus) LLM tools."""
from __future__ import annotations

from datetime import datetime
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm

from ..const import ENTRY_TRANSIT
from .base_tool import BaseKRTool
from .render import svg_table

_SUBWAY_ACCENT = "#0ea5e9"  # sky
_BUS_ACCENT = "#16a34a"     # green


def _seconds_to_min(seconds: Any) -> str:
    try:
        s = int(seconds or 0)
    except (TypeError, ValueError):
        return "-"
    if s <= 0:
        return "-"
    if s < 60:
        return f"{s}s"
    return f"{s // 60}m"


def _format_bus_eta(t: Any, *, novehicle: bool = False) -> str:
    """KakaoMap returns arrival time in seconds (0 = no data)."""
    if novehicle:
        return "운행종료"
    try:
        s = int(t or 0)
    except (TypeError, ValueError):
        return "-"
    if s <= 0:
        return "-"
    if s <= 60:
        return "곧 도착"
    return f"{s // 60}분 후"


class GetSubwayArrivalsTool(BaseKRTool):
    service = ENTRY_TRANSIT
    name = "get_subway_arrivals"
    description = (
        "Return upcoming Seoul subway arrivals at a configured station. "
        "Returns the next two trains per direction filter."
    )
    parameters = vol.Schema(
        {
            vol.Optional(
                "station",
                description=(
                    "Station name (Korean, e.g. '강남'). Omit to use the "
                    "first configured station."
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
        coords: dict[str, Any] = store.get("subway_coords") or {}
        if not coords:
            return self.error("등록된 지하철 역이 없습니다.")

        wanted = tool_input.tool_args.get("station")
        if wanted is None:
            station = next(iter(coords.keys()))
        elif wanted in coords:
            station = wanted
        else:
            return self.error(f"'{wanted}' 역이 등록되어 있지 않습니다.")

        coord = coords[station]
        if coord.data is None:
            return self.error("지하철 도착 데이터가 아직 준비되지 않았습니다.")

        arrivals: list[dict[str, Any]] = []
        for key, items in coord.data.items():
            for item in items:
                arrivals.append({
                    "line": item.get("line_name"),
                    "direction": key.split("_")[0],
                    "destination": item.get("destination"),
                    "arrival_message": item.get("arrival_message"),
                    "arrival_in_seconds": item.get("barvl_dt"),
                    "train_type": item.get("train_type"),
                })

        rows = [
            [
                a.get("line") or "",
                a.get("direction") or "",
                a.get("destination") or "",
                _seconds_to_min(a.get("arrival_in_seconds")),
                a.get("arrival_message") or "",
            ]
            for a in arrivals
        ]
        featured = svg_table(
            "지하철 도착 정보",
            ["노선", "방향", "행선", "도착", "안내"],
            rows,
            subtitle=f"{station}역",
            accent=_SUBWAY_ACCENT,
            empty_message="현재 도착 예정 정보가 없습니다.",
        )

        return self.envelope(
            station=station,
            arrivals=arrivals,
            featured_image=featured,
            instruction=(
                "Summarise the next subway arrivals naturally. The user is "
                "already shown a table; keep your reply short. Translate "
                "the Korean direction (상행/하행/내선/외선) and "
                "arrival_message. Convert arrival_in_seconds to minutes "
                "for the user."
            ),
        )


class GetBusArrivalsTool(BaseKRTool):
    service = ENTRY_TRANSIT
    name = "get_bus_arrivals"
    description = (
        "Return upcoming bus arrivals (next two per route) for a "
        "configured stop, sourced from KakaoMap."
    )
    parameters = vol.Schema(
        {
            vol.Optional(
                "stop_name",
                description=(
                    "Configured stop name. Omit to use the first stop."
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
        coords: dict[str, Any] = store.get("bus_coords") or {}
        stops: list[dict] = store.get("bus_stops") or []
        if not coords or not stops:
            return self.error("등록된 버스 정류장이 없습니다.")

        wanted = tool_input.tool_args.get("stop_name")
        chosen = None
        for s in stops:
            if wanted is None or s.get("stop_name") == wanted:
                chosen = s
                break
        if chosen is None:
            return self.error(f"'{wanted}' 정류장을 찾을 수 없습니다.")

        coord = coords.get(chosen["stop_id"])
        if coord is None or coord.data is None:
            return self.error("버스 도착 데이터가 아직 준비되지 않았습니다.")

        # KakaoMap arrival fields:
        #   line.arrival.arrivalTime  — seconds to first bus (0 = no data)
        #   line.arrival.arrivalTime2 — seconds to second bus
        #   line.arrival.direction    — destination text
        #   line.realtimeState        — "NOVEHICLE" when service has ended
        buses_out: list[dict[str, Any]] = []
        for name, line in coord.data.items():
            line = line or {}
            arrival = line.get("arrival") or {}
            novehicle = line.get("realtimeState") == "NOVEHICLE"
            t1 = arrival.get("arrivalTime") or 0
            t2 = arrival.get("arrivalTime2") or 0
            buses_out.append({
                "name": name,
                "direction": arrival.get("direction"),
                "first_arrival_seconds": t1 or None,
                "second_arrival_seconds": t2 or None,
                "first_arrival": _format_bus_eta(t1, novehicle=novehicle),
                "second_arrival": _format_bus_eta(t2, novehicle=novehicle and not t2),
                "no_service": novehicle,
            })

        # Sort: arriving buses first (by ETA asc), then no-data, then 운행종료
        def _sort_key(b: dict) -> tuple[int, int]:
            if b["no_service"] and not b["first_arrival_seconds"]:
                return (2, 0)
            t = b["first_arrival_seconds"] or 0
            if t <= 0:
                return (1, 0)
            return (0, t)
        buses_out.sort(key=_sort_key)

        rows = [
            [
                b["name"] or "",
                b["direction"] or "",
                b["first_arrival"],
                b["second_arrival"],
            ]
            for b in buses_out
        ]
        featured = svg_table(
            "버스 도착 정보",
            ["노선", "방향", "1번째", "2번째"],
            rows,
            subtitle=chosen.get("stop_name") or "",
            accent=_BUS_ACCENT,
            empty_message="현재 도착 예정 버스가 없습니다.",
        )

        return self.envelope(
            stop_name=chosen.get("stop_name"),
            stop_id=chosen.get("stop_id"),
            buses=buses_out,
            featured_image=featured,
            instruction=(
                "Summarise upcoming bus arrivals naturally. A table is "
                "already shown; keep the reply brief. Use first_arrival/"
                "second_arrival (already-formatted Korean strings like "
                "'5분 후', '곧 도착', '운행종료', '-')."
            ),
        )
