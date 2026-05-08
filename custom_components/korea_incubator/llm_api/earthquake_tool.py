"""Earthquake LLM tool."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm

from ..const import ENTRY_EARTHQUAKE
from .base_tool import BaseKRTool
from .render import svg_table

_EQ_ACCENT = "#7c3aed"  # violet


class GetRecentEarthquakesTool(BaseKRTool):
    service = ENTRY_EARTHQUAKE
    name = "get_recent_earthquakes"
    description = (
        "Return earthquakes recently observed in/around Korea (KMA "
        "earthquake database, last ~30 days)."
    )
    parameters = vol.Schema(
        {
            vol.Optional(
                "limit",
                description="Maximum events to return (1-20).",
            ): vol.All(int, vol.Range(min=1, max=20)),
            vol.Optional(
                "min_magnitude",
                description="Filter to events with at least this magnitude.",
            ): vol.All(vol.Coerce(float), vol.Range(min=0.0)),
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
            return self.error("지진 데이터가 아직 준비되지 않았습니다.")

        limit = tool_input.tool_args.get("limit") or 5
        min_mag = tool_input.tool_args.get("min_magnitude")
        events = []
        for eq in coord.data:
            if min_mag is not None:
                mag = eq.get("magnitude")
                if mag is None or mag < min_mag:
                    continue
            events.append({
                "datetime": eq.get("datetime"),
                "magnitude": eq.get("magnitude"),
                "depth_km": eq.get("depth"),
                "location": eq.get("location"),
                "latitude": eq.get("latitude"),
                "longitude": eq.get("longitude"),
            })
            if len(events) >= limit:
                break

        rows = [
            [
                (e.get("datetime") or "")[:16],
                f"M {e['magnitude']:.1f}" if e.get("magnitude") is not None else "-",
                f"{e['depth_km']} km" if e.get("depth_km") not in (None, "") else "-",
                e.get("location") or "",
            ]
            for e in events
        ]
        featured = svg_table(
            "최근 지진",
            ["발생", "규모", "깊이", "진앙지"],
            rows,
            subtitle=f"최대 {limit}건" + (f" / 규모≥{min_mag}" if min_mag else ""),
            accent=_EQ_ACCENT,
            empty_message="해당 조건의 지진이 없습니다.",
        )

        return self.envelope(
            count=len(events),
            min_magnitude=min_mag,
            events=events,
            featured_image=featured,
            instruction=(
                "Mention the most recent 1-2 events with magnitude, depth, "
                "and a brief location. A table is shown — keep it short. "
                "If list is empty, say so."
            ),
        )
