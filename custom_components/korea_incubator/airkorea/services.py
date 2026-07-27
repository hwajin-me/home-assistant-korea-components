"""AirKorea actions - living index forecast with region selection."""
from __future__ import annotations
import logging
import voluptuous as vol
import aiohttp
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from ..const import DOMAIN
from .api import fetch_uv_index, fetch_air_stagnation
from . import SIDO_AREA_CODE

_LOGGER = logging.getLogger(__name__)


def async_register_airkorea_services(hass: HomeAssistant, api_key: str,
                                      living_key: str, sido: str) -> None:
    default_area = SIDO_AREA_CODE.get(sido, "1100000000")

    async def handle_living_forecast(call: ServiceCall) -> ServiceResponse:
        index_type = call.data.get("index_type", "uv")
        region = call.data.get("region", "")
        area_code = SIDO_AREA_CODE.get(region, default_area) if region else default_area

        async with aiohttp.ClientSession() as session:
            key = living_key or api_key
            if index_type == "uv":
                data = await fetch_uv_index(session, key, area_code)
            else:
                data = await fetch_air_stagnation(session, key, area_code)

        if not data:
            return {"error": "No data available", "forecasts": []}

        forecasts = []
        for key_name in sorted(data.keys()):
            if key_name.startswith("h") and key_name[1:].isdigit():
                val = data.get(key_name)
                if val is not None and str(val).strip():
                    hour = int(key_name[1:])
                    try:
                        value = int(val)
                    except (ValueError, TypeError):
                        continue
                    if index_type == "uv":
                        from . import UV_GRADES
                        grade = next((g for t, g in UV_GRADES if value < t), "위험")
                    else:
                        from . import STAG_GRADES
                        grade = next((g for t, g in STAG_GRADES if value <= t), "매우높음")
                    forecasts.append({
                        "hour_offset": hour,
                        "value": value,
                        "grade": grade,
                    })

        region_name = region or sido
        return {
            "index_type": "자외선지수" if index_type == "uv" else "대기정체지수",
            "region": region_name,
            "area_code": area_code,
            "date": data.get("date", ""),
            "forecasts": forecasts,
        }

    if not hass.services.has_service(DOMAIN, "get_living_index_forecast"):
        hass.services.async_register(
            DOMAIN, "get_living_index_forecast", handle_living_forecast,
            schema=vol.Schema({
                vol.Required("index_type", default="uv"): vol.In(
                    {"uv": "자외선지수", "stagnation": "대기정체지수"}),
                vol.Optional("region", default=""): str,
            }),
            supports_response=SupportsResponse.ONLY,
        )
