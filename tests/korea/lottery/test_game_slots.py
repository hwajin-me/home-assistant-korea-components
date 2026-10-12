"""Reusable slot lifecycle for pension and Lotto games."""

import asyncio
from dataclasses import dataclass, replace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.korea_incubator.const import DOMAIN
from custom_components.korea_incubator.lottery_sensor import LotteryGameSensors


@dataclass
class Registered:
    entity_id: str
    unique_id: str
    config_entry_id: str = "entry"
    platform: str = DOMAIN
    domain: str = "sensor"
    name: str | None = "사용자 이름"
    disabled_by: str | None = None


class Registry:
    def __init__(self):
        self.rows = {}
        self.removed = []

    def async_update_entity(self, entity_id, **changes):
        self.rows[entity_id] = replace(
            self.rows[entity_id],
            **{key.removeprefix("new_"): value for key, value in changes.items()},
        )

    def async_remove(self, entity_id):
        self.removed.append(entity_id)
        self.rows.pop(entity_id)


def game(kind, index=1, round_no=336):
    return {
        "game_id": f"{kind}_order-{round_no}_{index}",
        "order_no": f"order-{round_no}",
        "round": round_no,
        "purchased_at": "2026-10-12",
        "group": str(index),
        "number": f"{index:06}",
        "slot": chr(64 + index),
        "numbers": [index, 10, 20, 30, 40, 45],
    }


@pytest.fixture
def manager(mock_hass, mock_config_entry, mock_coordinator):
    registry = Registry()
    mock_config_entry.entry_id = "entry"
    mock_coordinator.client.username = "account"
    mock_coordinator.data = {"pension_unsettled_games": [], "lotto_unsettled_games": []}
    mock_hass.async_create_task.side_effect = asyncio.create_task
    added = []

    def add(entities):
        added.extend(entities)
        for sensor in entities:
            # A platform normally assigns the entity_id and registry entry.
            existing = next(
                (r for r in registry.rows.values() if r.unique_id == sensor.unique_id),
                None,
            )
            sensor.entity_id = (
                existing.entity_id if existing else f"sensor.{sensor.unique_id}"
            )
            if existing is None:
                registry.rows[sensor.entity_id] = Registered(
                    sensor.entity_id, sensor.unique_id
                )

    with (
        patch(
            "custom_components.korea_incubator.lottery_sensor.er.async_get",
            return_value=registry,
        ),
        patch(
            "custom_components.korea_incubator.lottery_sensor.er.async_entries_for_config_entry",
            side_effect=lambda reg, entry_id: [
                r for r in reg.rows.values() if r.config_entry_id == entry_id
            ],
        ),
    ):
        instance = LotteryGameSensors(
            mock_hass, mock_config_entry, mock_coordinator, add
        )
        yield instance, registry, added
        instance.stop()


@pytest.mark.parametrize("kind", ["pension", "lotto"])
async def test_group_number_round_and_order_changes_reuse_existing_entity(
    manager, kind
):
    slots, registry, added = manager
    slots.coordinator.data[f"{kind}_unsettled_games"] = [game(kind)]
    await slots.async_sync()
    sensor = added[0]
    original_id = sensor.entity_id
    original_unique_id = sensor.unique_id
    for round_no in (337, 338, 339):
        replacement = game(kind, index=5, round_no=round_no)
        slots.coordinator.data[f"{kind}_unsettled_games"] = [replacement]
        await slots.async_sync()
        assert added == [sensor]
        assert slots.entities[(kind, 1)] is sensor
        assert sensor.entity_id == original_id
        assert sensor.unique_id == original_unique_id
        assert sensor.extra_state_attributes["회차"] == round_no
        if kind == "pension":
            assert sensor.native_value == "5조 000005"
        else:
            assert sensor.native_value == "5 10 20 30 40 45"
    assert len(registry.rows) == 1 and not registry.removed


@pytest.mark.parametrize("kind", ["pension", "lotto"])
async def test_shrink_removes_surplus_runtime_and_registry_then_regrow_uses_same_slots(
    manager, kind
):
    slots, registry, added = manager
    slots.coordinator.data[f"{kind}_unsettled_games"] = [
        game(kind, i) for i in range(1, 4)
    ]
    await slots.async_sync()
    first = added[0]
    retired = added[1:]
    for sensor in retired:
        sensor.hass = MagicMock()
        sensor.platform = MagicMock()
        sensor.platform.entities = {sensor.entity_id: sensor}
        sensor.async_remove = AsyncMock()
    slots.coordinator.data[f"{kind}_unsettled_games"] = [game(kind, 5)]
    await slots.async_sync()
    assert slots.entities == {(kind, 1): first}
    assert len(registry.rows) == 1
    for sensor in retired:
        sensor.async_remove.assert_awaited_once_with(force_remove=True)
        assert sensor.entity_id in registry.removed
    slots.coordinator.data[f"{kind}_unsettled_games"] = [
        game(kind, i, 337) for i in range(1, 4)
    ]
    await slots.async_sync()
    assert slots.entities[(kind, 1)] is first
    assert [sensor.unique_id for sensor in added[-2:]] == [
        sensor.unique_id for sensor in retired
    ]
    assert len(registry.rows) == 3
    slots.coordinator.data[f"{kind}_unsettled_games"] = []
    await slots.async_sync()
    assert not slots.entities and not registry.rows


async def test_migrate_keeps_entity_ids_names_and_other_accounts(manager):
    slots, registry, added = manager
    legacy = [
        Registered("sensor.pension_old", "donghaeng_lottery_account_pension_order_1_1"),
        Registered("sensor.lotto_old", "donghaeng_lottery_account_lotto_order_1"),
    ]
    unrelated = [
        Registered("sensor.balance", "donghaeng_lottery_account_balance"),
        Registered(
            "sensor.pension_winning", "donghaeng_lottery_account_pension_winning"
        ),
        Registered(
            "sensor.another_account", "donghaeng_lottery_other_pension_order_1_1"
        ),
        Registered(
            "sensor.another_entry",
            "donghaeng_lottery_account_lotto_another_1",
            config_entry_id="another",
        ),
        Registered(
            "button.buy", "donghaeng_lottery_account_pension_auto_1", domain="button"
        ),
    ]
    registry.rows = {r.entity_id: r for r in legacy + unrelated}
    for kind in ("pension", "lotto"):
        slots.coordinator.data[f"{kind}_unsettled_games"] = [game(kind)]
    await slots.async_sync()
    assert {sensor.entity_id for sensor in added} == {r.entity_id for r in legacy}
    for kind, old in zip(("pension", "lotto"), legacy):
        new = registry.rows[old.entity_id]
        assert new.unique_id == f"donghaeng_lottery_account_{kind}_game_1"
        assert new.name == old.name
    assert all(registry.rows[r.entity_id] == r for r in unrelated)


async def test_startup_removes_disabled_and_legacy_surplus_without_slot_conflict(
    manager,
):
    slots, registry, _ = manager
    current = Registered("sensor.kept", "donghaeng_lottery_account_pension_game_1")
    stale = [
        Registered("sensor.legacy", "donghaeng_lottery_account_pension_old_1_1"),
        Registered(
            "sensor.disabled",
            "donghaeng_lottery_account_pension_game_5",
            disabled_by="user",
        ),
    ]
    registry.rows = {r.entity_id: r for r in [current, *stale]}
    slots.coordinator.data["pension_unsettled_games"] = [game("pension")]
    await slots.async_sync()
    assert registry.rows == {current.entity_id: current}
    assert set(registry.removed) == {r.entity_id for r in stale}


async def test_failed_refresh_preserves_entities_and_registry(manager):
    slots, registry, added = manager
    slots.coordinator.data["pension_unsettled_games"] = [game("pension")]
    await slots.async_sync()
    slots.coordinator.last_update_success = False
    slots.coordinator.data = {}
    await slots.async_sync()
    slots.async_request_sync()
    assert slots.entities[("pension", 1)] is added[0]
    assert len(registry.rows) == 1 and not registry.removed
    assert slots._task is None


async def test_refresh_after_previous_task_completed_and_unload(manager):
    slots, registry, added = manager
    slots.coordinator.data["lotto_unsettled_games"] = [game("lotto")]
    slots.async_request_sync()
    await slots._task
    slots.coordinator.data["lotto_unsettled_games"].append(game("lotto", 2))
    slots.async_request_sync()
    await slots._task
    assert len(added) == 2
    slots.coordinator.data["lotto_unsettled_games"].append(game("lotto", 3))
    slots.async_request_sync()
    task = slots._task
    slots.stop()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(added) == len(registry.rows) == 2


async def test_disabled_sensor_is_not_removed_as_a_live_platform_entity(manager):
    slots, registry, added = manager
    slots.coordinator.data["pension_unsettled_games"] = [game("pension")]
    await slots.async_sync()
    disabled = added[0]
    disabled.platform = MagicMock()
    disabled.platform.entities = {}
    disabled.async_remove = AsyncMock()
    slots.coordinator.data["pension_unsettled_games"] = []
    await slots.async_sync()
    disabled.async_remove.assert_not_awaited()
    assert not registry.rows and not slots.entities


async def test_eager_completed_task_does_not_block_future_refreshes(manager):
    slots, _, added = manager
    loop = asyncio.get_running_loop()
    original_factory = loop.get_task_factory()
    loop.set_task_factory(asyncio.eager_task_factory)
    try:
        slots.coordinator.data["lotto_unsettled_games"] = [game("lotto")]
        slots.async_request_sync()
        assert slots._task.done()
        slots.coordinator.data["lotto_unsettled_games"].append(game("lotto", 2))
        slots.async_request_sync()
        assert len(added) == 2
    finally:
        loop.set_task_factory(original_factory)


async def test_grow_during_removal_waits_and_reconciles_again(manager):
    slots, registry, added = manager
    slots.coordinator.data["lotto_unsettled_games"] = [game("lotto", i) for i in (1, 2)]
    await slots.async_sync()
    retired = added[1]
    retired.platform = MagicMock()
    retired.platform.entities = {retired.entity_id: retired}
    entered, release = asyncio.Event(), asyncio.Event()

    async def remove(**kwargs):
        entered.set()
        await release.wait()

    retired.async_remove = AsyncMock(side_effect=remove)
    slots.coordinator.data["lotto_unsettled_games"] = [game("lotto")]
    slots.async_request_sync()
    task = slots._task
    try:
        await entered.wait()
        slots.coordinator.data["lotto_unsettled_games"] = [
            game("lotto", i, 337) for i in (1, 2, 3)
        ]
        slots.async_request_sync()
        assert slots._task is task
    finally:
        release.set()
        await task
    assert len(slots.entities) == len(registry.rows) == 3
    assert slots.entities[("lotto", 1)] is added[0]
    assert len(added) == 4  # Two original slots, then only slots 2 and 3 recreated.


async def test_migration_prefers_current_game_over_retired_registry_entry(manager):
    slots, registry, added = manager
    active = game("pension")
    current = Registered(
        "sensor.z_current", f"donghaeng_lottery_account_{active['game_id']}"
    )
    retired = Registered(
        "sensor.a_retired", "donghaeng_lottery_account_pension_retired_1_1"
    )
    registry.rows = {r.entity_id: r for r in (retired, current)}
    slots.coordinator.data["pension_unsettled_games"] = [active]
    await slots.async_sync()
    assert added[0].entity_id == current.entity_id
    assert registry.removed == [retired.entity_id]
