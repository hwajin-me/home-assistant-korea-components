"""Shared Public Data Portal credential helpers."""

from __future__ import annotations

from typing import Any

from .const import (
    DOMAIN,
    ENTRY_AIRKOREA,
    ENTRY_ANIMAL_MEDICAL,
    ENTRY_EARTHQUAKE,
    ENTRY_KMA_WEATHER,
    ENTRY_PHARMACY,
    ENTRY_WEATHER,
)


# Only these services use a service key issued through data.go.kr.  Keep
# service-specific credentials (for example NEIS and safetydata.go.kr) out of
# this list even though their setup form may also call the field ``api_key``.
DATA_GO_KR_SERVICES = frozenset(
    {
        ENTRY_AIRKOREA,
        ENTRY_ANIMAL_MEDICAL,
        ENTRY_EARTHQUAKE,
        ENTRY_KMA_WEATHER,
        ENTRY_PHARMACY,
        ENTRY_WEATHER,
    }
)


def configured_data_go_kr_api_key(hass: Any) -> str:
    """Return a saved Public Data Portal key suitable as a form default.

    Config entries retain their own key so a user can still override one
    service.  This only pre-populates new setup forms with the first existing
    non-empty data.go.kr key.
    """
    if hass is None:
        return ""
    config_entries = getattr(hass, "config_entries", None)
    if config_entries is None:
        return ""

    for entry in config_entries.async_entries(DOMAIN):
        if entry.data.get("service") not in DATA_GO_KR_SERVICES:
            continue
        key = entry.options.get("api_key") or entry.data.get("api_key", "")
        if isinstance(key, str) and key.strip():
            return key
    return ""
