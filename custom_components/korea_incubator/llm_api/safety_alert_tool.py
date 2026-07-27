"""Safety alert (안전디딤돌) LLM tool."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm

from ..const import ENTRY_SAFETY_ALERT
from .base_tool import BaseKRTool
from .render import grid_results, svg_card

_SAFETY_ACCENT = "#ea580c"   # orange-red


class GetSafetyAlertsTool(BaseKRTool):
    service = ENTRY_SAFETY_ALERT
    name = "get_safety_alerts"
    description = (
        "Return the latest 안전디딤돌 alerts for the configured region(s)."
    )
    parameters = vol.Schema(
        {
            vol.Optional(
                "limit",
                description="Maximum alerts to return (1-20).",
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
        coords: dict[str, Any] = store.get("coordinators") or {}
        regions: list[dict[str, str]] = store.get("regions") or []
        if not coords:
            return self.error("등록된 지역이 없습니다.")

        limit = tool_input.tool_args.get("limit") or 5
        out: list[dict[str, Any]] = []
        for region in regions:
            code = region.get("code")
            coord = coords.get(code)
            if coord is None or coord.data is None:
                continue
            alerts = (coord.data.get("alerts") or [])[:limit]
            out.append({
                "region_name": region.get("name") or code,
                "region_code": code,
                "count": len(alerts),
                "alerts": [
                    {
                        "message": a.get("MSG_CN") or a.get("message"),
                        "category": a.get("DST_SE_NM"),
                        "level": a.get("EMRG_STEP_NM"),
                        "area": a.get("RCV_AREA_NM"),
                        "created_at": a.get("CRT_DT"),
                    }
                    for a in alerts
                ],
            })

        total = sum(r["count"] for r in out)
        items = []
        for r in out:
            for a in r["alerts"]:
                items.append((
                    f"{r['region_name']} · {a.get('category') or '경보'}",
                    [
                        ("등급", a.get("level") or "-"),
                        ("지역", a.get("area") or "-"),
                        ("시각", (a.get("created_at") or "")[:16]),
                        ("내용", (a.get("message") or "")[:60]),
                    ],
                    None,
                ))

        if items:
            results = grid_results(items, accent=_SAFETY_ACCENT)
            featured = None
        else:
            results = []
            featured = svg_card(
                "안전디딤돌 경보",
                [],
                subtitle="활성 경보 없음",
                accent="#64748b",
                big_value="안전",
                big_value_caption="현재 발효 중인 경보가 없습니다.",
            )

        envelope = self.envelope(
            total_active=total,
            regions=out,
            results=results,
            instruction=(
                "Summarise the active safety alerts. If none are active say "
                "so. Cards are shown — keep your reply brief."
            ),
        )
        if featured:
            envelope["featured_image"] = featured
        return envelope
