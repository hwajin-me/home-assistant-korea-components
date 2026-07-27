"""Base tool class for kr_public_data LLM tools."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import llm

from ..const import DOMAIN
from .const import SOURCE

_LOGGER = logging.getLogger(__name__)


class BaseKRTool(llm.Tool):
    """Reads its bound config entry's coordinator data via hass.data."""

    service: str = ""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        super().__init__()
        self.hass = hass
        self.entry_id = entry_id

    @property
    def store(self) -> dict[str, Any]:
        return self.hass.data.get(DOMAIN, {}).get(self.entry_id, {})

    def envelope(self, **fields: Any) -> dict[str, Any]:
        """Build a standard response envelope for tools without a card UI."""
        out: dict[str, Any] = {"source": SOURCE, "service": self.service}
        out.update(fields)
        return out

    def error(self, message: str) -> dict[str, Any]:
        return {"source": SOURCE, "service": self.service, "error": message}
