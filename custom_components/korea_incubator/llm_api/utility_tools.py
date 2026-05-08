"""Utility-bill LLM tools: KEPCO electricity, GasApp gas, Arisu water."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm

from ..const import ENTRY_ARISU, ENTRY_GASAPP, ENTRY_KEPCO
from ..utils import get_value_from_path
from .base_tool import BaseKRTool
from .render import svg_card

_KEPCO_ACCENT = "#eab308"   # amber
_GAS_ACCENT = "#ef4444"     # red
_WATER_ACCENT = "#06b6d4"   # cyan


def _fmt_krw(v: Any) -> str | None:
    if v is None or v == "":
        return None
    try:
        return f"{int(float(str(v).replace(',', ''))):,}원"
    except (TypeError, ValueError):
        return str(v)


class GetElectricityUsageTool(BaseKRTool):
    service = ENTRY_KEPCO
    name = "get_electricity_usage"
    description = (
        "Return the household's recent electricity usage and current "
        "month bill from KEPCO (한국전력)."
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
            return self.error("한전 데이터가 아직 준비되지 않았습니다.")

        recent = coord.data.get("recent_usage") or {}
        usage_info = coord.data.get("usage_info") or {}

        contract = get_value_from_path(usage_info, "result.SESS_CNTR_KND_NM")
        custno = get_value_from_path(usage_info, "result.SESS_CUSTNO")
        usage = get_value_from_path(recent, "result.F_AP_QT")
        last = get_value_from_path(usage_info, "result.BILL_LAST_MONTH")
        predicted = get_value_from_path(usage_info, "result.PREDICT_TOTAL_CHARGE_REV")
        featured = svg_card(
            "한국전력 사용량",
            [
                ("계약 종류", contract or "-"),
                ("고객번호", custno or "-"),
                ("지난달 요금", _fmt_krw(last) or "-"),
                ("예상 요금", _fmt_krw(predicted) or "-"),
            ],
            subtitle="이번 청구주기 누적",
            accent=_KEPCO_ACCENT,
            big_value=f"{usage} kWh" if usage is not None else "-",
            big_value_caption="현재 사용량",
        )

        return self.envelope(
            customer_number=custno,
            contract_type=contract,
            current_usage_kwh=usage,
            last_month_bill_krw=last,
            predicted_bill_krw=predicted,
            featured_image=featured,
            instruction=(
                "Tell the user how much electricity they've used so far this "
                "billing cycle and the predicted vs last-month bill in KRW. "
                "A summary card is already shown — keep the reply brief."
            ),
        )


class GetGasBillTool(BaseKRTool):
    service = ENTRY_GASAPP
    name = "get_gas_bill"
    description = "Return the most recent city-gas bill and meter info."
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
            return self.error("도시가스 데이터가 아직 준비되지 않았습니다.")

        bill = coord.data.get("current_bill") or {}
        home = coord.data.get("home_data") or {}
        amount = _fmt_krw(bill.get("title2"))
        featured = svg_card(
            "도시가스 청구",
            [
                ("청구 제목", bill.get("title1") or "-"),
            ],
            subtitle="가스앱 기준",
            accent=_GAS_ACCENT,
            big_value=amount or "-",
            big_value_caption="총 요금",
        )
        return self.envelope(
            bill_title=bill.get("title1"),
            total_amount_krw=bill.get("title2"),
            home_summary=home,
            featured_image=featured,
            instruction=(
                "Read out the current gas bill amount in KRW and the bill "
                "title. A summary card is shown — keep it brief."
            ),
        )


class GetWaterBillTool(BaseKRTool):
    service = ENTRY_ARISU
    name = "get_water_bill"
    description = "Return the most recent Arisu water bill and usage."
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
            return self.error("아리수 데이터가 아직 준비되지 않았습니다.")

        d = coord.data or {}
        usage = d.get("current_usage")
        amount = _fmt_krw(d.get("total_amount"))
        featured = svg_card(
            "아리수 수도 요금",
            [
                ("청구월", d.get("billing_month") or "-"),
                ("사용량", f"{usage} ㎥" if usage is not None else "-"),
            ],
            subtitle="서울특별시 상수도",
            accent=_WATER_ACCENT,
            big_value=amount or "-",
            big_value_caption="총 요금",
        )
        return self.envelope(
            billing_month=d.get("billing_month"),
            usage_m3=usage,
            total_amount_krw=d.get("total_amount"),
            featured_image=featured,
            instruction=(
                "Tell the user the latest Arisu water bill and the cubic-"
                "metre usage. A summary card is shown — keep it brief."
            ),
        )
