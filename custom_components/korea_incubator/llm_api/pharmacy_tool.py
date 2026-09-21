"""Selected-pharmacy LLM tool using the same date-specific state as its sensor."""

from __future__ import annotations

import voluptuous as vol

from ..animal_medical.hours import current_state
from ..const import ENTRY_PHARMACY
from ..pharmacy.api import weekly_hours
from .base_tool import BaseKRTool


class GetOpenPharmaciesTool(BaseKRTool):
    """Keep the existing tool name while reporting only the selected pharmacy."""

    service = ENTRY_PHARMACY
    name = "get_open_pharmacies"
    description = (
        "Return the selected pharmacy's current status, address, phone and hours. "
        "An unknown status must not be interpreted as open or closed."
    )
    parameters = vol.Schema(
        {
            vol.Optional("only_open"): bool,
            vol.Optional("limit"): vol.All(int, vol.Range(min=1, max=15)),
        }
    )

    async def async_call(self, hass, tool_input, llm_context):
        coord = self.store.get("coordinator")
        if coord is None or not coord.last_update_success or not coord.data:
            return self.error("약국 데이터가 아직 준비되지 않았습니다.")
        record = coord.data
        state = current_state(record.get("_kakao", {}).get("schedule", {}))
        only_open = tool_input.tool_args.get("only_open", False)
        pharmacies = (
            []
            if only_open and state != "open"
            else [
                {
                    "hpid": record.get("hpid"),
                    "name": record.get("dutyName"),
                    "address": record.get("dutyAddr"),
                    "phone": record.get("dutyTel1"),
                    "status": state,
                    "open_now": None if state is None else state == "open",
                    "weekly_hours": weekly_hours(record),
                    "opening_hours": record.get("_kakao", {}).get("open_hours"),
                }
            ]
        )
        return self.envelope(
            pharmacies=pharmacies,
            count=len(pharmacies),
            only_open_filter=only_open,
            instruction="Report only this selected pharmacy. Unknown status means opening hours could not be verified; do not infer closure or recommend it as open.",
        )
