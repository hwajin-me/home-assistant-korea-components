"""Disaster message (재난문자) LLM tool."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm

from ..const import ENTRY_DISASTER
from .base_tool import BaseKRTool
from .render import grid_results

_DISASTER_ACCENT = "#f59e0b"  # amber


class GetDisasterMessagesTool(BaseKRTool):
    service = ENTRY_DISASTER
    name = "get_disaster_messages"
    description = (
        "Return the most recent civil-defense disaster messages "
        "(재난문자) issued in Korea, optionally filtered by region."
    )
    parameters = vol.Schema(
        {
            vol.Optional(
                "limit",
                description="Maximum messages to return (1-20).",
            ): vol.All(int, vol.Range(min=1, max=20)),
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
            return self.error("재난문자 데이터가 아직 준비되지 않았습니다.")

        limit = tool_input.tool_args.get("limit") or 5
        messages = (coord.data or [])[:limit]

        results = grid_results(
            (
                (
                    m.get("disaster_type") or "재난문자",
                    [
                        ("지역", m.get("area") or "-"),
                        ("등급", m.get("level") or "-"),
                        ("시각", (m.get("create_date") or "")[:16]),
                        ("내용", (m.get("message") or "")[:60]),
                    ],
                    None,
                )
                for m in messages
            ),
            accent=_DISASTER_ACCENT,
        )

        return self.envelope(
            region_filter=store.get("region") or None,
            count=len(messages),
            messages=[
                {
                    "message": m.get("message"),
                    "area": m.get("area"),
                    "created_at": m.get("create_date"),
                    "level": m.get("level"),
                    "disaster_type": m.get("disaster_type"),
                }
                for m in messages
            ],
            results=results,
            instruction=(
                "Summarise the most recent disaster messages briefly. "
                "Cards are shown to the user — keep it short. Mention the "
                "issuing area and time. If filter returned nothing, say so."
            ),
        )
