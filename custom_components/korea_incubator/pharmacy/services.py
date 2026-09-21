"""Pharmacy search action."""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from ..animal_medical.api import AnimalMedicalApiError
from ..const import DOMAIN
from .api import fetch_pharmacies

_LOGGER = logging.getLogger(__name__)
KEYS = f"{DOMAIN}_pharmacy_keys"


def async_register_pharmacy_service(
    hass: HomeAssistant, api_key: str, entry_id: str = "legacy"
) -> None:
    """Track active entry credentials, never keep unloaded keys in a closure."""

    async def handle_search(call: ServiceCall) -> ServiceResponse:
        keys = hass.data.get(KEYS, {})
        selected = call.data.get("config_entry_id")
        if selected is None:
            selected = next(iter(keys), None)
        key = keys.get(selected)
        if not key:
            raise ServiceValidationError(
                "No active pharmacy configuration for this request"
            )
        region = call.data["region"]
        district = call.data.get("district", "")
        count = call.data.get("count", 10)
        try:
            results = await fetch_pharmacies(
                async_get_clientsession(hass), key, region, district, num=int(count)
            )
        except AnimalMedicalApiError as err:
            _LOGGER.warning("Pharmacy search: %s", err)
            raise HomeAssistantError(str(err)) from err
        return {"pharmacies": results, "count": len(results)}

    # Replace the callback on reload so reauthenticated keys are not left stale.
    if api_key:
        hass.data.setdefault(KEYS, {})[entry_id] = api_key
        hass.services.async_register(
            DOMAIN,
            "search_pharmacy",
            handle_search,
            schema=vol.Schema(
                {
                    vol.Required("region"): str,
                    vol.Optional("config_entry_id"): str,
                    vol.Optional("district", default=""): str,
                    vol.Optional("count", default=10): vol.All(
                        vol.Coerce(int), vol.Range(min=1, max=100)
                    ),
                }
            ),
            supports_response=SupportsResponse.ONLY,
        )


def async_unregister_pharmacy_service(hass: HomeAssistant, entry_id: str) -> None:
    """Leave the action available while at least one pharmacy is loaded."""
    keys = hass.data.get(KEYS, {})
    keys.pop(entry_id, None)
    if not keys:
        hass.data.pop(KEYS, None)
        hass.services.async_remove(DOMAIN, "search_pharmacy")
