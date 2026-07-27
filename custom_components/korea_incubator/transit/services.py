"""Transit services: location search + path search."""
from __future__ import annotations
import logging
import voluptuous as vol
import aiohttp
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from ..const import DOMAIN
from .transfer_api import search_location, search_path

_LOGGER = logging.getLogger(__name__)


def async_register_services(hass: HomeAssistant, api_key: str) -> None:
    """Register transit action services."""

    async def handle_search_location(call: ServiceCall) -> ServiceResponse:
        keyword = call.data["keyword"]
        async with aiohttp.ClientSession() as session:
            results = await search_location(session, api_key, keyword)
        return {"locations": results}

    async def handle_search_path(call: ServiceCall) -> ServiceResponse:
        sx = call.data["start_x"]
        sy = call.data["start_y"]
        ex = call.data["end_x"]
        ey = call.data["end_y"]
        async with aiohttp.ClientSession() as session:
            results = await search_path(session, api_key, sx, sy, ex, ey)
        return {"paths": results}

    if not hass.services.has_service(DOMAIN, "search_location"):
        hass.services.async_register(
            DOMAIN, "search_location", handle_search_location,
            schema=vol.Schema({vol.Required("keyword"): str}),
            supports_response=SupportsResponse.ONLY,
        )

    if not hass.services.has_service(DOMAIN, "search_transit_path"):
        hass.services.async_register(
            DOMAIN, "search_transit_path", handle_search_path,
            schema=vol.Schema({
                vol.Required("start_x"): str,
                vol.Required("start_y"): str,
                vol.Required("end_x"): str,
                vol.Required("end_y"): str,
            }),
            supports_response=SupportsResponse.ONLY,
        )
