"""Disaster message coordinator - resilient to intermittent SSL errors."""
from __future__ import annotations
import logging
from datetime import timedelta
from typing import Any

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from . import DISASTER_SCAN_INTERVAL
from .api import fetch_disaster_messages

_LOGGER = logging.getLogger(__name__)

_REGION_ALIASES = {
    "서울특별시": "서울",
    "부산광역시": "부산",
    "대구광역시": "대구",
    "인천광역시": "인천",
    "광주광역시": "광주",
    "대전광역시": "대전",
    "울산광역시": "울산",
    "세종특별자치시": "세종",
    "경기도": "경기",
    "강원특별자치도": "강원",
    "강원도": "강원",
    "충청북도": "충북",
    "충청남도": "충남",
    "전북특별자치도": "전북",
    "전라북도": "전북",
    "전라남도": "전남",
    "경상북도": "경북",
    "경상남도": "경남",
    "제주특별자치도": "제주",
}


def _normalize_region(value: str) -> str:
    """Normalize official and abbreviated Korean region names for matching."""
    normalized = value
    for official_name, short_name in _REGION_ALIASES.items():
        normalized = normalized.replace(official_name, short_name)
    return "".join(character for character in normalized if character.isalnum())


def _matches_region(area: str, region_filter: str) -> bool:
    """Return whether an API reception area matches the configured filter."""
    return _normalize_region(region_filter) in _normalize_region(area)


class DisasterCoordinator(DataUpdateCoordinator[list[dict[str, Any]]]):
    def __init__(self, hass, api_key, region_filter=""):
        super().__init__(hass, _LOGGER, name="disaster",
                         update_interval=timedelta(seconds=DISASTER_SCAN_INTERVAL))
        self._api_key = api_key
        self._region_filter = region_filter
        self._consecutive_failures = 0

    async def _async_update_data(self):
        try:
            all_msgs = await fetch_disaster_messages(self._api_key, count=30)
            self._consecutive_failures = 0
        except ValueError as err:
            # API-declared failures such as an expired key are permanent until
            # the user updates the configuration; do not hide them as empty data.
            raise UpdateFailed(f"Disaster API rejected the request: {err}") from err
        except Exception as err:
            self._consecutive_failures += 1
            # Tolerate transient TLS/connection errors. If we have stale data,
            # keep serving it; on first load (no stale data), return an empty
            # list so the entry still loads instead of marking the whole
            # integration as failed. UpdateFailed kicks in only after we've
            # observed sustained failures.
            if self._consecutive_failures <= 5:
                _LOGGER.warning(
                    "Disaster API transient error (%d/5): %s",
                    self._consecutive_failures, err)
                return self.data if self.data is not None else []
            raise UpdateFailed(f"Disaster API error: {err}") from err

        if self._region_filter:
            return [m for m in all_msgs
                    if _matches_region(m.get("area") or "", self._region_filter)]
        return all_msgs
