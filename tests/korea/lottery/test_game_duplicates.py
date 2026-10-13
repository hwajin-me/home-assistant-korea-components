"""Repeated ledger/detail records must not multiply game entities."""

from unittest.mock import AsyncMock

import pytest

from custom_components.korea_incubator.lottery import (
    LotteryClient,
    unique_lottery_games,
)


@pytest.fixture
async def client():
    instance = LotteryClient("test-user", "test-password")
    yield instance
    await instance.close()


def purchase(order="one-order", barcode="1:733524"):
    return {
        "order_no": order,
        "round": 337,
        "result": "미추첨",
        "quantity": 5,
        "purchased_at": "2026-10-13",
        "barcode": barcode,
    }


async def test_pension_repeated_ledger_and_full_set_detail_rows(client):
    client.pension_purchase_history = AsyncMock(return_value=[purchase()] * 5)
    raw = ",".join(f"{group}:733524" for group in range(1, 6))
    client._get_json_with_login = AsyncMock(
        return_value={"list": [{"ltGmInfoCn": raw}] * 5}
    )
    games = await client.pension_unsettled_games()
    assert len(games) == 5
    assert [item["group"] for item in games] == list("12345")
    client._get_json_with_login.assert_awaited_once()


async def test_pension_repeated_order_uses_each_ledger_number_if_details_missing(
    client,
):
    client.pension_purchase_history = AsyncMock(
        return_value=[purchase(barcode=f"{group}:733524") for group in range(1, 6)] * 3
    )
    client._get_json_with_login = AsyncMock(return_value={"list": []})
    games = await client.pension_unsettled_games()
    assert len(games) == 5
    client._get_json_with_login.assert_awaited_once()


async def test_lotto_repeated_receipt_and_game_detail_rows(client):
    client.lotto_645_purchase_history = AsyncMock(
        return_value=[purchase(barcode="receipt-one")] * 5
    )
    details = [
        {"idx": label, "num": [1, 2, 3, 4, 5, 6], "type": "자동"} for label in "ABCDE"
    ]
    client._get_json_with_login = AsyncMock(
        return_value={"ticket": {"game_dtl": details * 5}}
    )
    games = await client.lotto_645_unsettled_games()
    assert len(games) == 5
    assert [item["slot"] for item in games] == list("ABCDE")
    client._get_json_with_login.assert_awaited_once()


@pytest.mark.parametrize("kind", ["pension", "lotto"])
async def test_same_numbers_in_separate_orders_are_preserved(client, kind):
    if kind == "pension":
        client.pension_purchase_history = AsyncMock(
            return_value=[purchase("one"), purchase("two")]
        )
        client._get_json_with_login = AsyncMock(
            return_value={"list": [{"ltGmInfoCn": "1:733524"}]}
        )
        games = await client.pension_unsettled_games()
    else:
        client.lotto_645_purchase_history = AsyncMock(
            return_value=[purchase("one"), purchase("two")]
        )
        client._get_json_with_login = AsyncMock(
            return_value={
                "ticket": {"game_dtl": [{"idx": "A", "num": [1, 2, 3, 4, 5, 6]}]}
            }
        )
        games = await client.lotto_645_unsettled_games()
    assert len(games) == 2
    assert {item["order_no"] for item in games} == {"one", "two"}


async def test_lotto_same_numbers_in_separate_receipts_are_preserved(client):
    client.lotto_645_purchase_history = AsyncMock(
        return_value=[purchase(barcode="first"), purchase(barcode="second")]
    )
    client._get_json_with_login = AsyncMock(
        return_value={"ticket": {"game_dtl": [{"idx": "A", "num": [1, 2, 3, 4, 5, 6]}]}}
    )
    games = await client.lotto_645_unsettled_games()
    assert len(games) == 2


def test_lotto_number_order_does_not_create_extra_game():
    game = {"order_no": "one", "round": 337, "slot": "A", "numbers": [1, 2, 3, 4, 5, 6]}
    assert unique_lottery_games(
        [game, {**game, "numbers": [6, 5, 4, 3, 2, 1]}], "lotto"
    ) == [game]
