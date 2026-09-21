"""Cached date-specific closure action shared by all medical entries."""

import voluptuous as vol
from homeassistant.core import SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from ..const import DOMAIN
from .closed_days import closed_day_status
from .hours import effective_schedule

SERVICE = "check_medical_closed_day"
STORE = f"{DOMAIN}_medical_hours"


def group_title(data):
    if data["service"] == "pharmacy":
        return "약국"
    return "동물병원" if data["institution_type"] == "hospital" else "동물약국"


def register_medical_action(hass, entry, coordinator):
    hass.data.setdefault(STORE, {})[entry.entry_id] = coordinator

    async def check(call):
        coord = hass.data.get(STORE, {}).get(call.data["config_entry_id"])
        if coord is None:
            raise ServiceValidationError("선택한 의료기관 설정이 로드되지 않았습니다.")
        requested = call.data["date"]
        days = effective_schedule(coord.data)
        closed = (
            closed_day_status(days, requested) if coord.last_update_success else None
        )
        return {
            "date": requested.isoformat(),
            "is_closed": closed,
            "closure_reason": (
                days[requested.isoformat()].get("closure_reason")
                if closed is True
                else None
            ),
            "status": "unknown" if closed is None else "closed" if closed else "open",
            "full_day_only": True,
            "source": "naver+kakao" if (coord.data or {}).get("_naver") else "kakao",
            "known_dates": sorted(
                day for day, value in days.items() if value is not None
            ),
        }

    hass.services.async_register(
        DOMAIN,
        SERVICE,
        check,
        schema=vol.Schema(
            {
                vol.Required("config_entry_id"): str,
                vol.Required("date"): cv.date,
            }
        ),
        supports_response=SupportsResponse.ONLY,
    )


def unregister_medical_action(hass, entry_id):
    entries = hass.data.get(STORE, {})
    entries.pop(entry_id, None)
    if not entries:
        hass.data.pop(STORE, None)
        hass.services.async_remove(DOMAIN, SERVICE)
