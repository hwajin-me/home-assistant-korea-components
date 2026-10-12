"""Reconcile reusable lottery game slots with the entity registry."""

from __future__ import annotations

import asyncio
import re

from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN
from .lottery import LotteryUnsettledGameSensor


class LotteryGameSensors:
    """Reuse slots across rounds and remove surplus live and registered entities."""

    def __init__(self, hass, entry, coordinator, add) -> None:
        self.hass = hass
        self.entry = entry
        self.coordinator = coordinator
        self.add = add
        self.registry = er.async_get(hass)
        self.entities: dict[tuple[str, int], LotteryUnsettledGameSensor] = {}
        self._task: asyncio.Task | None = None
        self._dirty = False
        self._stopped = False
        self._migrated = False
        self._prefix = f"donghaeng_lottery_{coordinator.client.username}_"

    @callback
    def async_request_sync(self) -> None:
        """Coalesce refreshes and finish removals before reusing a freed slot."""
        if self._stopped or not self.coordinator.last_update_success:
            return
        self._dirty = True
        if self._task is None or self._task.done():
            self._task = self.hass.async_create_task(self._async_sync_updates())

    async def _async_sync_updates(self) -> None:
        try:
            while self._dirty:
                self._dirty = False
                await self.async_sync()
        finally:
            self._task = None

    @callback
    def stop(self) -> None:
        """Prevent queued refreshes from adding entities during unload."""
        self._stopped = True
        if self._task is not None:
            self._task.cancel()

    def _registered_games(self, lottery_type):
        prefix = f"{self._prefix}{lottery_type}_"
        return [
            entity
            for entity in er.async_entries_for_config_entry(
                self.registry, self.entry.entry_id
            )
            if entity.platform == DOMAIN
            and entity.domain == "sensor"
            and entity.unique_id.startswith(prefix)
            and re.fullmatch(
                r"(?:game_[1-9]\d*|.+_\d+(?:_\d+)?)", entity.unique_id[len(prefix) :]
            )
        ]

    def _migrate(self, lottery_type: str, count: int) -> None:
        """Keep old entity IDs and user customizations when moving to slots."""
        prefix = f"{self._prefix}{lottery_type}_game_"
        registered = self._registered_games(lottery_type)
        occupied = {
            entity.unique_id
            for entity in registered
            if entity.unique_id.startswith(prefix)
        }
        free = [
            slot for slot in range(1, count + 1) if f"{prefix}{slot}" not in occupied
        ]
        active_order = {
            f"{self._prefix}{game['game_id']}": index
            for index, game in enumerate(
                self.coordinator.data.get(f"{lottery_type}_unsettled_games", [])
            )
            if game.get("game_id")
        }
        legacy = sorted(
            (
                entity
                for entity in registered
                if not entity.unique_id.startswith(prefix)
            ),
            key=lambda entity: (
                active_order.get(entity.unique_id, count),
                entity.entity_id,
            ),
        )
        for entity, slot in zip(legacy, free):
            self.registry.async_update_entity(
                entity.entity_id, new_unique_id=f"{prefix}{slot}"
            )
        for entity in legacy[len(free) :]:
            self.registry.async_remove(entity.entity_id)

    async def async_sync(self) -> None:
        """Keep only the number of slots needed by the latest successful data."""
        if self._stopped or not self.coordinator.last_update_success:
            return
        for lottery_type in ("pension", "lotto"):
            count = len(
                self.coordinator.data.get(f"{lottery_type}_unsettled_games", [])
            )
            if not self._migrated:
                self._migrate(lottery_type, count)
            expected = {
                f"{self._prefix}{lottery_type}_game_{slot}"
                for slot in range(1, count + 1)
            }
            for key, sensor in list(self.entities.items()):
                if key[0] != lottery_type or key[1] <= count:
                    continue
                if (
                    sensor.platform is not None
                    and sensor.entity_id in sensor.platform.entities
                ):
                    await sensor.async_remove(force_remove=True)
                self.entities.pop(key)
            # Also prune disabled slots or leftovers from a previous HA run.
            for entity in self._registered_games(lottery_type):
                if entity.unique_id not in expected:
                    self.registry.async_remove(entity.entity_id)
            new_entities = []
            for slot in range(1, count + 1):
                key = (lottery_type, slot)
                if key not in self.entities:
                    sensor = LotteryUnsettledGameSensor(
                        self.coordinator, lottery_type, slot
                    )
                    self.entities[key] = sensor
                    new_entities.append(sensor)
            if new_entities:
                self.add(new_entities)
        self._migrated = True
