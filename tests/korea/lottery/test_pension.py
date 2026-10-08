"""Pension contracts taken from the browser flow; all HTTP is mocked."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, unquote

import pytest

from custom_components.korea_incubator.const import DOMAIN
from custom_components.korea_incubator.lottery import (
    Balance,
    LotteryClient,
    LotteryError,
    LotteryUnsettledGameSensor,
)
from custom_components.korea_incubator.sensor import async_setup_entry

# Synthetic payment form. No account cookies or identifiers are test fixtures.
FORM = """<form id="frm"><input name="USER_ID" value="test-user">
<input name="FLAG" value=""><input name="DSEC" value="0">
<input name="CLOSE_DATE" value=""><input name="DROUND" value="336">
<input name="lotto720_radio_group" type="radio" checked>
<input name="unchecked" type="radio"><input name="disabled" disabled>
</form>"""


@pytest.fixture
async def client():
    instance = LotteryClient("test-user", "test-password")
    instance.balance = AsyncMock(return_value=Balance(10000, 10000))
    instance._async_open_pension_game = AsyncMock(return_value=FORM)
    instance._pension_round_remain_time = AsyncMock(return_value={"ROUND": "336"})
    instance.pension_purchase_history = AsyncMock(return_value=[])
    instance._pension_ticket_exists = AsyncMock(return_value=False)
    yield instance
    await instance.close()


def transport(client, result_code="100", sold_groups=None):
    async def step(path, fields, **kwargs):
        data = dict(fields)
        if path == "/checkDeposit.do":
            return {"deposit": "10000"}
        if path == "/makeAutoNo.do":
            return {
                "resultCode": "100",
                "selYN": "Y",
                "round": "336",
                "autoSelSet": data["AUTO_SEL_SET"],
                "selLotNo": "000019",
                "selClsNo": "S" if data["AUTO_SEL_SET"] == "SA" else data["SEL_CLASS"],
            }
        if path == "/makeOrderNo.do":
            return {
                "resultCode": "100",
                "orderNo": "new-order",
                "orderDate": "20261008",
            }
        if path == "/connPro.do":
            if result_code == "E002":
                return {"resultCode": "E002", "resultMsg": "구매 진행중인 복권 존재"}
            sold = data["BUY_NO"].split(",")
            if sold_groups is not None:
                sold = [value for value in sold if int(value[0]) in sold_groups]
            return {
                "resultCode": result_code,
                "saleCnt": len(sold),
                "saleTicket": ",".join(sold),
            }
        pytest.fail(f"Unexpected endpoint: {path}")

    client._pension_step = AsyncMock(side_effect=step)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("1:836319", [("1", "836319")]),
        (
            "1000019,2000019,3000019,4000019,5000019",
            [(str(i), "000019") for i in range(1, 6)],
        ),
        ("1조 000019 / 2조 000019", [("1", "000019"), ("2", "000019")]),
        ("<span>1조</span>&nbsp;<span>0</span><span>0</span>0019", [("1", "000019")]),
        ("6:123456; 11:123456; 10000199", []),
    ],
)
def test_browser_number_formats(raw, expected):
    assert LotteryClient._pension_numbers({"ltGmInfoCn": raw}) == expected


@pytest.mark.parametrize("games", [1, 2, 3, 4, 5])
async def test_single_payment_and_automatic_verification(client, games):
    transport(client)
    tickets = await client.buy_pension_auto(games)
    assert len(tickets) == games
    assert [item["group"] for item in tickets] == list(range(1, games + 1))
    assert all(item["number"] == "000019" for item in tickets)
    calls = client._pension_step.call_args_list
    paths = [call.args[0] for call in calls]
    assert paths.count("/makeAutoNo.do") == (1 if games == 5 else games)
    assert paths.count("/makeOrderNo.do") == paths.count("/connPro.do") == 1
    assert "/checkVerifyNo.do" not in paths
    assert paths.index("/checkDeposit.do") < paths.index("/makeOrderNo.do")
    payment = dict(calls[-1].args[1])
    assert payment["BUY_CNT"] == str(games)
    assert payment["BUY_SET_TYPE"] == ",".join(["SA" if games == 5 else "S"] * games)
    assert payment["BUY_TYPE"] == ",".join(["A"] * games)
    assert payment["WORKING_FLAG"] == "true"
    assert payment["verifyYN"] == payment["auto_process"] == "N"
    assert payment["curdeposit"] == "10000"
    assert payment["curpay"] == str(games * 1000)
    assert payment["classnum"] == payment["selnum"] == payment["num1"] == ""
    assert payment["DROUND"] == "336"
    assert payment["lotto720_radio_group"] == "on"
    assert "unchecked" not in payment and "disabled" not in payment
    client._pension_ticket_exists.assert_not_awaited()


async def test_partial_receipt_returns_only_sold_games(client):
    transport(client, "110", {1, 3})
    assert [item["group"] for item in await client.buy_pension_auto(5)] == [1, 3]
    assert [c.args[0] for c in client._pension_step.call_args_list].count(
        "/connPro.do"
    ) == 1


async def test_no_ticket_sold_is_not_success(client):
    transport(client, "120", set())
    with pytest.raises(LotteryError, match="구매 가능한 티켓이 없습니다"):
        await client.buy_pension_auto(5)


async def test_in_progress_error_never_retries(client):
    transport(client, "E002")
    client.pension_purchase_history.return_value = [{"order_no": "old-order"}]
    with pytest.raises(LotteryError, match="E002.*구매 진행중"):
        await client.buy_pension_auto(1)
    assert [c.args[0] for c in client._pension_step.call_args_list].count(
        "/connPro.do"
    ) == 1
    client._pension_ticket_exists.assert_awaited_once_with(
        336, "1", "000019", excluded_orders={"old-order"}
    )


@pytest.mark.parametrize(
    "response", [None, TimeoutError(), LotteryError("invalid receipt")]
)
async def test_uncertain_payment_checks_ledger_without_resubmitting(client, response):
    transport(client)
    normal_step = client._pension_step.side_effect

    async def step(path, fields, **kwargs):
        if path == "/connPro.do":
            if isinstance(response, Exception):
                raise response
            return response
        return await normal_step(path, fields, **kwargs)

    client._pension_step.side_effect = step
    client._pension_ticket_exists.return_value = True
    assert len(await client.buy_pension_auto(1)) == 1
    assert [c.args[0] for c in client._pension_step.call_args_list].count(
        "/connPro.do"
    ) == 1


async def test_overlapping_button_and_service_requests_are_rejected(client):
    transport(client)
    entered, release = asyncio.Event(), asyncio.Event()

    async def balance():
        entered.set()
        await release.wait()
        return Balance(10000, 10000)

    client.balance.side_effect = balance
    first = asyncio.create_task(client.buy_pension_auto(1))
    try:
        await entered.wait()
        with pytest.raises(LotteryError, match="이미 진행 중"):
            await client.buy_pension_auto(5)
    finally:
        release.set()
        await first


async def test_previous_identical_number_cannot_confirm_payment(client):
    client.pension_purchase_history.return_value = [{"order_no": "old", "round": 336}]
    client._get_json_with_login = AsyncMock(
        return_value={"list": [{"ltGmInfoCn": "1:000019"}]}
    )
    assert not await LotteryClient._pension_ticket_exists(
        client, 336, "1", "000019", excluded_orders={"old"}
    )
    client._get_json_with_login.assert_not_awaited()
    client.pension_purchase_history.return_value.append(
        {"order_no": "new", "round": 336}
    )
    assert await LotteryClient._pension_ticket_exists(
        client, 336, "1", "000019", excluded_orders={"old"}
    )


@pytest.mark.parametrize(
    "detail",
    [{"list": [{"ltGmInfoCn": "1:836319"}]}, {"list": []}, LotteryError("unavailable")],
)
async def test_ledger_number_creates_individual_sensor(
    client, detail, mock_hass, mock_config_entry, mock_coordinator
):
    purchase = {
        "order_no": "synthetic",
        "round": 336,
        "result": "미추첨",
        "purchased_at": "2026-10-08",
        "barcode": "1:836319",
    }
    client.pension_purchase_history.return_value = [purchase]
    client._get_json_with_login = AsyncMock(
        **(
            {"side_effect": detail}
            if isinstance(detail, Exception)
            else {"return_value": detail}
        )
    )
    games = await client.pension_unsettled_games()
    assert len(games) == 1
    mock_coordinator.client = client
    mock_coordinator.data = {"pension_unsettled_games": games}
    mock_config_entry.data = {"service": "dh_lottery"}
    mock_hass.data[DOMAIN][mock_config_entry.entry_id] = {
        "coordinator": mock_coordinator
    }
    add = MagicMock()
    await async_setup_entry(mock_hass, mock_config_entry, add)
    sensors = [
        sensor
        for call in add.call_args_list
        for sensor in call.args[0]
        if isinstance(sensor, LotteryUnsettledGameSensor)
    ]
    assert len(sensors) == 1
    assert sensors[0].name == "연금복권 720+ 336회 1조"
    assert sensors[0].native_value == "1조 836319"
    listener = mock_coordinator.async_add_listener.call_args.args[0]
    listener()
    assert add.call_count == 2  # Existing game not added twice.
    mock_coordinator.data["pension_unsettled_games"].append(
        {**games[0], "game_id": "new", "group": "2"}
    )
    listener()
    assert add.call_count == 3


async def test_transport_preserves_browser_double_plus_encoding(client):
    response = MagicMock(status=200, content_type="application/json")
    response.text = AsyncMock(return_value='{"resultCode":"100"}')
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=response)
    context.__aexit__ = AsyncMock(return_value=False)
    with (
        patch.object(client, "_el_session_id", return_value="synthetic-session"),
        patch.object(client, "_encrypt", return_value="abc+/="),
        patch.object(client.session, "post", return_value=context) as post,
    ):
        await client._pension_step("/makeAutoNo.do", [("ROUND", "336")])
    encoded = post.call_args.kwargs["data"]
    assert encoded == "q=abc%252B%2F%3D"
    assert unquote(parse_qs(encoded)["q"][0]) == "abc+/="


async def test_current_cookie_is_forwarded_and_preferred_over_stale_alias(client):
    from yarl import URL

    client.session.cookie_jar.update_cookies(
        {"DHJSESSIONID": "current-session"},
        response_url=URL("https://www.dhlottery.co.kr"),
    )
    client.session.cookie_jar.update_cookies(
        {"JSESSIONID": "stale-session"}, response_url=URL("https://el.dhlottery.co.kr")
    )
    client._copy_game_session_cookie()
    assert client._el_session_id() == "current-session"


async def test_new_ledger_number_can_confirm_without_detail_endpoint(client):
    client.pension_purchase_history.return_value = [
        {"order_no": "new", "round": 336, "barcode": "1:000019"}
    ]
    client._get_json_with_login = AsyncMock(side_effect=LotteryError("unavailable"))
    assert await LotteryClient._pension_ticket_exists(
        client, 336, "1", "000019", excluded_orders={"old"}
    )
    client._get_json_with_login.assert_not_awaited()


async def test_refresh_waits_until_purchase_session_is_released(client):
    from custom_components.korea_incubator.lottery import LotteryCoordinator

    coordinator = object.__new__(LotteryCoordinator)
    coordinator.client = client
    coordinator._async_read_data = AsyncMock(return_value={"fresh": True})
    async with client._operation_lock:
        refresh = asyncio.create_task(coordinator._async_update_data())
        await asyncio.sleep(0)
        coordinator._async_read_data.assert_not_awaited()
    assert await refresh == {"fresh": True}


async def test_lotto_does_not_overlap_pension_purchase(client):
    async with client._purchase_lock:
        with pytest.raises(LotteryError, match="이미 진행 중"):
            await client.buy_lotto_645_auto(1)


async def test_failed_preflight_does_not_create_order(client):
    transport(client)
    client._check_pension_deposit = AsyncMock(
        side_effect=LotteryError("예치금 확인 실패")
    )
    with pytest.raises(LotteryError, match="예치금 확인 실패"):
        await client.buy_pension_auto(1)
    client._pension_step.assert_not_awaited()


async def test_button_reports_actual_partial_purchase_count(client, mock_coordinator):
    from custom_components.korea_incubator.button import PensionAutoPurchaseButton

    mock_coordinator.client = client
    mock_coordinator.async_request_refresh = AsyncMock()
    client.buy_pension_auto = AsyncMock(
        return_value=[{"round": 336, "group": 1, "number": "000019"}]
    )
    button = PensionAutoPurchaseButton(mock_coordinator, 5)
    button.hass = MagicMock()
    with patch(
        "custom_components.korea_incubator.button.persistent_notification.async_create"
    ) as notify:
        await button.async_press()
    assert "요청 5게임 중 1게임 구매 확인" in notify.call_args.args[1]
    assert "(1게임)" in notify.call_args.args[2]


async def test_failed_service_refreshes_ledger(mock_hass, mock_coordinator):
    from custom_components.korea_incubator import _async_setup_lottery_services

    mock_hass.data[DOMAIN]["lottery-entry"] = {"coordinator": mock_coordinator}
    mock_coordinator.client.buy_pension_auto = AsyncMock(
        side_effect=LotteryError("E002")
    )
    mock_coordinator.async_request_refresh = AsyncMock()
    await _async_setup_lottery_services(mock_hass)
    service = next(
        call.args[2]
        for call in mock_hass.services.async_register.call_args_list
        if call.args[1] == "buy_pension_720_auto"
    )
    registry = MagicMock()
    registry.async_get.return_value.config_entry_id = "lottery-entry"
    call = MagicMock(data={"entity_id": "sensor.balance", "games": 1})
    with (
        patch("homeassistant.helpers.entity_registry.async_get", return_value=registry),
        patch("custom_components.korea_incubator.persistent_notification.async_create"),
    ):
        result = await service(call)
    assert result == {"result": "fail", "message": "E002"}
    mock_coordinator.async_request_refresh.assert_awaited_once()
