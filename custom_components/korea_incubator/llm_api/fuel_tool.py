"""Fuel (Opinet) price LLM tool."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm

from ..const import ENTRY_FUEL
from ..fuel import FUEL_TYPES, SIDO_CODES
from .base_tool import BaseKRTool
from .render import svg_table

_FUEL_ACCENT = "#f97316"  # orange


def _fmt_price(p: Any) -> str:
    try:
        return f"{float(p):,.1f}"
    except (TypeError, ValueError):
        return str(p or "-")


def _fmt_diff(d: Any) -> str:
    try:
        f = float(d)
    except (TypeError, ValueError):
        return str(d or "")
    return f"+{f:.1f}" if f > 0 else f"{f:.1f}"


class GetFuelPricesTool(BaseKRTool):
    service = ENTRY_FUEL
    name = "get_fuel_prices"
    description = (
        "Return the latest national average price and the lowest-price "
        "stations for each configured (sido, fuel) combination. Prices "
        "are KRW per litre."
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
        if coord is None or coord.data is None:
            return self.error("유가 데이터가 아직 준비되지 않았습니다.")

        avg = coord.data.get("average") or []
        national_avg = [
            {
                "fuel_code": a["product_code"],
                "fuel_name": FUEL_TYPES.get(a["product_code"], a["product_code"]),
                "price": a.get("price"),
                "change_vs_yesterday": a.get("diff"),
            }
            for a in avg
        ]

        low_by_combo = []
        for cfg in store.get("configs") or []:
            sido = cfg["sido_code"]
            fuel = cfg["fuel_code"]
            stations = coord.data.get(f"low_{sido}_{fuel}") or []
            low_by_combo.append({
                "sido_code": sido,
                "sido_name": SIDO_CODES.get(sido, sido),
                "fuel_code": fuel,
                "fuel_name": FUEL_TYPES.get(fuel, fuel),
                "stations": stations[:5],
            })

        # Build a table with the national average + cheapest per combo
        rows = [
            [a["fuel_name"], _fmt_price(a["price"]), _fmt_diff(a["change_vs_yesterday"]), "전국 평균"]
            for a in national_avg
        ]
        for combo in low_by_combo:
            stations = combo["stations"] or []
            if not stations:
                continue
            cheapest = stations[0]
            rows.append([
                combo["fuel_name"],
                _fmt_price(cheapest.get("price")),
                "",
                f"{combo['sido_name']} · {cheapest.get('station_name', '')}",
            ])
        featured = svg_table(
            "유가 정보",
            ["연료", "가격(원/L)", "전일대비", "지역/주유소"],
            rows,
            subtitle="Opinet 기준",
            accent=_FUEL_ACCENT,
            empty_message="유가 정보가 아직 없습니다.",
        )

        return self.envelope(
            national_average=national_avg,
            lowest_by_region=low_by_combo,
            currency="KRW/L",
            featured_image=featured,
            instruction=(
                "Summarise the fuel prices briefly — a table is already "
                "shown. Mention the national average and the cheapest 1-2 "
                "stations per configured region/fuel."
            ),
        )
