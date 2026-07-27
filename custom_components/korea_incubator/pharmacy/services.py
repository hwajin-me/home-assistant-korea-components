"""Pharmacy search action."""
from __future__ import annotations
import logging
import voluptuous as vol
import aiohttp
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from ..const import DOMAIN
from .api import fetch_pharmacies

_LOGGER = logging.getLogger(__name__)


def async_register_pharmacy_service(hass: HomeAssistant, api_key: str) -> None:
    async def handle_search(call: ServiceCall) -> ServiceResponse:
        region = call.data["region"]
        district = call.data.get("district", "")
        count = call.data.get("count", 10)
        async with aiohttp.ClientSession() as session:
            results = await fetch_pharmacies(session, api_key, region, district, num=int(count))
        return {"pharmacies": results, "count": len(results)}

    if not hass.services.has_service(DOMAIN, "search_pharmacy"):
        hass.services.async_register(
            DOMAIN, "search_pharmacy", handle_search,
            schema=vol.Schema({
                vol.Required("region"): str,
                vol.Optional("district", default=""): str,
                vol.Optional("count", default=10): vol.Coerce(int),
            }),
            supports_response=SupportsResponse.ONLY,
        )
