"""Pharmacy LLM tool — uses the existing coordinator's most recent fetch.

The pharmacy coordinator already polls the configured (q0, q1) region; we
return its current data. To allow narrowing q1 on demand, this tool reads
straight from the coordinator's stored answer rather than re-querying.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm

from ..const import ENTRY_PHARMACY
from .base_tool import BaseKRTool
from .render import grid_results

_PHARMACY_ACCENT_OPEN = "#16a34a"   # green
_PHARMACY_ACCENT_CLOSED = "#64748b"  # slate


_DAY_NAMES_KO = ["월", "화", "수", "목", "금", "토", "일"]


def _is_open_now(duty_time: dict[str, str], now: datetime) -> bool:
    today_key = _DAY_NAMES_KO[now.weekday()]
    spec = duty_time.get(today_key) or duty_time.get("공휴일")
    if not spec or "~" not in spec:
        return False
    try:
        start_str, close_str = spec.split("~", 1)
        start_str, close_str = start_str.strip(), close_str.strip()
        if len(start_str) != 4 or len(close_str) != 4:
            return False
        start_min = int(start_str[:2]) * 60 + int(start_str[2:])
        close_min = int(close_str[:2]) * 60 + int(close_str[2:])
    except ValueError:
        return False
    cur = now.hour * 60 + now.minute
    if close_min <= start_min:
        # overnight
        return cur >= start_min or cur <= close_min
    return start_min <= cur <= close_min


class GetOpenPharmaciesTool(BaseKRTool):
    service = ENTRY_PHARMACY
    name = "get_open_pharmacies"
    description = (
        "Return pharmacies in the configured region, marking which are "
        "open right now (based on their duty hours). Useful for "
        "after-hours or holiday queries."
    )
    parameters = vol.Schema(
        {
            vol.Optional(
                "only_open",
                description="If true, only return pharmacies open now.",
            ): bool,
            vol.Optional(
                "limit",
                description="Maximum pharmacies to return (1-15).",
            ): vol.All(int, vol.Range(min=1, max=15)),
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
            return self.error("약국 데이터가 아직 준비되지 않았습니다.")

        only_open = tool_input.tool_args.get("only_open", False)
        limit = tool_input.tool_args.get("limit") or 8
        now = datetime.now()

        pharmacies = []
        for ph in coord.data:
            duty_time = ph.get("duty_time") or {}
            open_now = _is_open_now(duty_time, now)
            if only_open and not open_now:
                continue
            pharmacies.append({
                "name": ph.get("name"),
                "address": ph.get("address"),
                "phone": ph.get("phone"),
                "open_now": open_now,
                "today_hours": duty_time.get(_DAY_NAMES_KO[now.weekday()]),
            })
            if len(pharmacies) >= limit:
                break

        results = []
        for p in pharmacies:
            accent = (
                _PHARMACY_ACCENT_OPEN if p.get("open_now") else _PHARMACY_ACCENT_CLOSED
            )
            card = grid_results(
                [(
                    f"{'🟢' if p.get('open_now') else '⚪'} {p['name']}",
                    [
                        ("주소", p.get("address") or "-"),
                        ("전화", p.get("phone") or "-"),
                        ("오늘 영업", p.get("today_hours") or "-"),
                    ],
                    None,
                )],
                accent=accent,
            )
            results.extend(card)

        return self.envelope(
            count=len(pharmacies),
            only_open_filter=only_open,
            pharmacies=pharmacies,
            results=results,
            instruction=(
                "Tell the user which pharmacies are open now. Mention 1-2 "
                "names with their hours; offer the address/phone if asked. "
                "Cards are shown — keep it brief."
            ),
        )
