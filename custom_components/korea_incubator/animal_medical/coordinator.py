"""Persistent interval-based refresh using only list queries."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import timedelta
from typing import Any

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from ..const import DOMAIN
from . import CONF_INTERVAL, DEFAULT_INTERVAL
from .api import (
    MAX_ROWS,
    AnimalMedicalApiError,
    AnimalMedicalAuthError,
    async_fetch_institutions,
    find_selected_institution,
)
from .hours import SEOUL, schedule, valid_schedule
from .kakao import KakaoError, async_place


class AnimalMedicalCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Identify the same business across pagination, relocation and renaming."""

    service_name = "animal_medical"
    record_name_key = "BPLC_NM"

    def __init__(self, hass, entry_data: dict[str, Any], *, config_entry=None) -> None:
        options = dict(config_entry.options) if config_entry is not None else {}
        self.interval_minutes = options.get(
            CONF_INTERVAL, entry_data.get(CONF_INTERVAL, DEFAULT_INTERVAL)
        )
        super().__init__(
            hass,
            logging.getLogger(__name__),
            name=self.service_name,
            update_interval=timedelta(minutes=self.interval_minutes),
            config_entry=config_entry,
        )
        self._entry_data = entry_data
        self._business_name = entry_data["business_name"]
        self.last_refresh = None
        self._restored_data = None
        self._store = (
            Store(hass, 1, f"{DOMAIN}.{self.service_name}.{config_entry.entry_id}")
            if config_entry is not None
            else None
        )
        self._fingerprint = hashlib.sha256(
            json.dumps({**entry_data, **options}, sort_keys=True).encode()
        ).hexdigest()

    @property
    def next_refresh(self):
        """Next regular refresh measured from the last successful API result."""
        if self.last_refresh is None or not self.last_update_success:
            return None
        return self.last_refresh + timedelta(minutes=self.interval_minutes)

    def _matches_identity(self, record):
        return (
            find_selected_institution(
                [record],
                self._entry_data["management_number"],
                self._entry_data["municipality_code"],
            )
            is not None
        )

    async def async_restore(self):
        """Restore a fresh, matching cache only during the first startup setup."""
        if self._store is None:
            return
        try:
            cached = await self._store.async_load()
            if (
                not isinstance(cached, dict)
                or cached.get("fingerprint") != self._fingerprint
            ):
                return
            stamp = dt_util.parse_datetime(cached["last_refresh"])
            record = cached["record"]
            now = dt_util.utcnow()
            if (
                stamp is None
                or stamp.tzinfo is None
                or stamp > now
                or not isinstance(record, dict)
                or not self._matches_identity(record)
                or stamp + timedelta(minutes=self.interval_minutes) <= now
            ):
                return
            if "_kakao" in record:
                place = record["_kakao"]
                if (
                    not isinstance(place, dict)
                    or not isinstance(place.get("summary"), dict)
                    or not isinstance(place.get("open_hours"), dict)
                    or not valid_schedule(place.get("schedule"))
                    or place.get("place_id") != self._entry_data.get("kakao_place_id")
                ):
                    return
            self.last_refresh = stamp
            self._restored_data = record
            self._business_name = record.get(self.record_name_key) or ""
        except (OSError, KeyError, TypeError, ValueError):
            self.logger.warning(
                "Animal medical cache could not be restored; fetching API data"
            )

    def _schedule_refresh(self):
        """After restore, schedule only the remaining time, not a new interval."""
        interval = self.update_interval
        if self.last_update_success and self.next_refresh is not None:
            self.update_interval = timedelta(
                seconds=max(1, (self.next_refresh - dt_util.utcnow()).total_seconds())
            )
        try:
            super()._schedule_refresh()
        finally:
            self.update_interval = interval

    async def _find(self, business_name: str) -> dict[str, Any] | None:
        page = 1
        seen: set[tuple[tuple[str, str], ...]] = set()
        while True:
            items, total = await async_fetch_institutions(
                async_get_clientsession(self.hass),
                self._entry_data["api_key"],
                self._entry_data["institution_type"],
                page=page,
                municipality_code=self._entry_data["municipality_code"],
                business_name=business_name,
            )
            selected = find_selected_institution(
                items,
                self._entry_data["management_number"],
                self._entry_data["municipality_code"],
            )
            if selected is not None:
                return selected
            signature = tuple(
                (i.get("OPN_ATMY_GRP_CD", ""), i.get("MNG_NO", "")) for i in items
            )
            if signature in seen or (not items and (page - 1) * MAX_ROWS < total):
                raise AnimalMedicalApiError("Incomplete or repeated API page")
            seen.add(signature)
            if page * MAX_ROWS >= total:
                return None
            page += 1

    async def _async_update_data(self) -> dict[str, Any]:
        if self._restored_data is not None:
            restored, self._restored_data = self._restored_data, None
            return restored
        try:
            selected = await self._find(self._business_name)
            # A municipality-only fallback finds renamed/relocated businesses.
            # Never filter on operating status: closed records must update too.
            if selected is None and self._business_name:
                selected = await self._find("")
            if selected is None:
                raise AnimalMedicalApiError("Selected institution is no longer listed")
            self._business_name = selected.get(self.record_name_key) or ""
            selected = dict(selected)
            if place_id := self._entry_data.get("kakao_place_id"):
                try:
                    place = await async_place(
                        async_get_clientsession(self.hass), place_id
                    )
                    stamp = dt_util.utcnow()
                    days = schedule(place["open_hours"], stamp)
                    yesterday = (
                        stamp.astimezone(SEOUL).date() - timedelta(days=1)
                    ).isoformat()
                    previous = (self.data or {}).get("_kakao", {})
                    if previous.get(
                        "place_id"
                    ) == place_id and yesterday in previous.get("schedule", {}):
                        days[yesterday] = previous["schedule"][yesterday]
                    selected["_kakao"] = {
                        **place,
                        "schedule": days,
                        "fetched_at": stamp.isoformat(),
                        "place_id": place_id,
                    }
                except KakaoError as err:
                    # Public licensing data remains available, but stale hours must
                    # not leave the current-open sensor falsely reporting open.
                    self.logger.warning("Animal medical Kakao refresh: %s", err)
                    selected["_kakao_error"] = str(err)
            self.last_refresh = dt_util.utcnow()
            if self._store is not None:
                try:
                    await self._store.async_save(
                        {
                            "fingerprint": self._fingerprint,
                            "last_refresh": self.last_refresh.isoformat(),
                            "record": selected,
                        }
                    )
                except OSError:
                    self.logger.warning("Animal medical cache could not be saved")
            return selected
        except AnimalMedicalAuthError as err:
            self.logger.error(
                "Animal medical %s authentication: %s",
                self._entry_data.get("institution_type", self.service_name),
                err,
            )
            raise ConfigEntryAuthFailed(str(err)) from err
        except AnimalMedicalApiError as err:
            self.logger.warning(
                "Animal medical %s refresh: %s",
                self._entry_data.get("institution_type", self.service_name),
                err,
            )
            raise UpdateFailed(str(err)) from err
