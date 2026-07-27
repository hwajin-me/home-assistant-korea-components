"""LLM API registration for kr_public_data services.

One llm.API is registered per added config entry, exposing only the tools
relevant to that service. The voice-satellite-card-llm-tools result schema
is used so the voice-satellite card can auto-render compatible payloads
(e.g. weather forecast).
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm

from ..const import (
    DOMAIN,
    ENTRY_AIRKOREA,
    ENTRY_ARISU,
    ENTRY_DISASTER,
    ENTRY_EARTHQUAKE,
    ENTRY_FUEL,
    ENTRY_GASAPP,
    ENTRY_KEPCO,
    ENTRY_KMA_WEATHER,
    ENTRY_PHARMACY,
    ENTRY_SAFETY_ALERT,
    ENTRY_SCHOOL,
    ENTRY_TRANSIT,
    ENTRY_WEATHER,
)
from .const import (
    API_DESCRIPTIONS,
    API_NAMES,
    API_PROMPTS,
)
from .tools import TOOLS_BY_ETYPE

_LOGGER = logging.getLogger(__name__)


def _api_id(etype: str, entry_id: str) -> str:
    return f"{DOMAIN}__{etype}__{entry_id}"


class _ServiceAPI(llm.API):
    """An llm.API bound to a single config entry of a given service type."""

    def __init__(
        self,
        hass: HomeAssistant,
        etype: str,
        entry_id: str,
        tool_factories: list[Callable[[HomeAssistant, str], llm.Tool]],
    ) -> None:
        super().__init__(
            hass=hass,
            id=_api_id(etype, entry_id),
            name=API_NAMES[etype],
        )
        self._etype = etype
        self._entry_id = entry_id
        self._tool_factories = tool_factories

    async def async_get_api_instance(
        self, llm_context: llm.LLMContext
    ) -> llm.APIInstance:
        tools = [factory(self.hass, self._entry_id) for factory in self._tool_factories]
        return llm.APIInstance(
            api=self,
            api_prompt=API_PROMPTS[self._etype],
            llm_context=llm_context,
            tools=tools,
        )


async def async_setup_llm_api(
    hass: HomeAssistant, entry: ConfigEntry, etype: str
) -> Callable[[], None] | None:
    """Register an llm.API for this entry.

    Returns the unregister callable (caller stores it for unload), or None
    if the service has no tools.
    """
    factories = TOOLS_BY_ETYPE.get(etype)
    if not factories:
        return None

    api = _ServiceAPI(hass, etype, entry.entry_id, factories)
    unreg = llm.async_register_api(hass, api)
    _LOGGER.info(
        "Registered LLM API %s for %s entry %s",
        api.id,
        etype,
        entry.entry_id,
    )
    return unreg


def async_cleanup_llm_api(unregister: Callable[[], None] | None) -> None:
    """Invoke the unregister callable returned by async_setup_llm_api."""
    if unregister is None:
        return
    try:
        unregister()
    except Exception as e:  # pragma: no cover
        _LOGGER.debug("Error unregistering LLM API: %s", e)


__all__ = [
    "async_setup_llm_api",
    "async_cleanup_llm_api",
]
