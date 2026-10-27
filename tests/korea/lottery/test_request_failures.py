"""Request classification, session refresh and setup recovery regressions."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.korea_incubator import async_setup_entry
from custom_components.korea_incubator.const import DOMAIN
from custom_components.korea_incubator.lottery import (
    Balance,
    LotteryAuthError,
    LotteryClient,
    LotteryConnectionError,
    LotteryCoordinator,
    LotteryDataError,
    LotteryHTTPError,
)


@pytest.fixture
async def client():
    instance = LotteryClient("test-user", "test-password")
    yield instance
    await instance.close()


def response_context(status=200, data=None):
    response = MagicMock(status=status)
    response.json = AsyncMock(return_value=data)
    response.read = AsyncMock()
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=response)
    context.__aexit__ = AsyncMock(return_value=False)
    return context, response


@pytest.mark.parametrize("status", [401, 403, 429, 500, 503])
async def test_http_status_and_safe_path_are_preserved(client, status):
    context, _ = response_context(status)
    expected = LotteryAuthError if status == 401 else LotteryHTTPError
    with patch.object(client.session, "get", return_value=context):
        with pytest.raises(expected) as caught:
            await client._get_json("mypage/selectUserMndp.do", {"secret": "private"})
    assert caught.value.status == status
    assert caught.value.path == "mypage/selectUserMndp.do"
    assert f"HTTP {status}" in str(caught.value)
    assert "private" not in str(caught.value)


@pytest.mark.parametrize("failure", [TimeoutError(), aiohttp.ClientConnectionError()])
async def test_connection_error_keeps_cause_and_has_deadline(client, failure):
    context, _ = response_context()
    context.__aenter__.side_effect = failure
    with patch.object(client.session, "get", return_value=context) as get:
        with pytest.raises(LotteryConnectionError) as caught:
            await client._get_json("test.do")
    assert caught.value.__cause__ is failure
    assert "test.do" in str(caught.value)
    assert get.call_args.kwargs["timeout"].total == 30
    assert get.call_args.kwargs["timeout"].connect == 10


@pytest.mark.parametrize("data", [[], {"data": []}])
async def test_invalid_response_is_data_error(client, data):
    context, _ = response_context(data=data)
    with patch.object(client.session, "get", return_value=context):
        with pytest.raises(LotteryDataError, match="test.do"):
            await client._get_json("test.do")


async def test_bad_json_is_not_an_authentication_error(client):
    context, response = response_context()
    response.json.side_effect = ValueError("not JSON")
    with patch.object(client.session, "get", return_value=context):
        with pytest.raises(LotteryDataError, match="test.do"):
            await client._get_json("test.do")


async def test_null_ledger_is_still_empty(client):
    context, _ = response_context(data={"data": None})
    with patch.object(client.session, "get", return_value=context):
        assert await client._get_json("test.do") == {}


@pytest.mark.parametrize("stage", ["key", "credentials"])
@pytest.mark.parametrize("status", [401, 403, 503])
async def test_login_http_errors_identify_stage(client, stage, status):
    key_context, _ = response_context(
        status=status if stage == "key" else 200,
        data={"data": {"rsaModulus": "abcd", "publicExponent": "10001"}},
    )
    login_context, _ = response_context(status=status)
    with (
        patch.object(client.session, "get", return_value=key_context),
        patch.object(client.session, "post", return_value=login_context),
        patch("custom_components.korea_incubator.lottery._RSAKey"),
    ):
        with pytest.raises(LotteryHTTPError) as caught:
            await client.login()
    assert caught.value.path == (
        "login/selectRsaModulus.do" if stage == "key" else "login/securityLoginCheck.do"
    )
    assert caught.value.status == status
    assert not client.logged_in
    assert client._login_generation == 0


@pytest.mark.parametrize("data", [None, [], {}, {"data": None}, {"data": {}}])
async def test_bad_login_key_response_is_data_error(client, data):
    context, _ = response_context(data=data)
    with patch.object(client.session, "get", return_value=context):
        with pytest.raises(LotteryDataError, match="login/selectRsaModulus.do"):
            await client.login()
    assert not client.logged_in


async def test_login_network_timeout_is_connection_error(client):
    context, _ = response_context()
    failure = TimeoutError()
    context.__aenter__.side_effect = failure
    with patch.object(client.session, "get", return_value=context):
        with pytest.raises(LotteryConnectionError) as caught:
            await client.login()
    assert caught.value.__cause__ is failure
    assert not client.logged_in


async def test_successful_login_advances_session_generation(client):
    key_context, _ = response_context(
        data={"data": {"rsaModulus": "abcd", "publicExponent": "10001"}},
    )
    login_context, _ = response_context()
    with (
        patch.object(client.session, "get", return_value=key_context),
        patch.object(client.session, "post", return_value=login_context),
        patch("custom_components.korea_incubator.lottery._RSAKey"),
    ):
        await client.login()
    assert client.logged_in
    assert client._login_generation == 1


@pytest.mark.parametrize(
    "failure",
    [
        LotteryHTTPError("test.do", 403),
        LotteryHTTPError("test.do", 429),
        LotteryHTTPError("test.do", 503),
        LotteryConnectionError("timeout"),
        LotteryDataError("invalid JSON"),
    ],
)
async def test_non_auth_failures_do_not_log_in_again(client, failure):
    client._get_json = AsyncMock(side_effect=failure)
    client._login = AsyncMock()
    with pytest.raises(type(failure)) as caught:
        await client._get_json_with_login("test.do")
    assert caught.value is failure
    client._login.assert_not_awaited()
    client._get_json.assert_awaited_once()


async def test_confirmed_auth_failure_refreshes_only_once(client):
    client._get_json = AsyncMock(side_effect=LotteryAuthError("test.do", 401))
    client._login = AsyncMock()
    with pytest.raises(LotteryAuthError):
        await client._get_json_with_login("test.do")
    assert client._get_json.await_count == 2
    client._login.assert_awaited_once()


async def test_concurrent_expired_reads_share_one_login(client):
    both_started = asyncio.Event()
    calls = 0

    async def read(path, params):
        nonlocal calls
        if client._login_generation:
            return {"ok": True}
        calls += 1
        if calls == 2:
            both_started.set()
        await both_started.wait()
        raise LotteryAuthError(path, 401)

    async def login():
        # Give the other rejected read time to wait on the login lock.
        await asyncio.sleep(0)
        client._login_generation += 1

    client._get_json = AsyncMock(side_effect=read)
    client._login = AsyncMock(side_effect=login)
    assert await asyncio.gather(
        client._get_json_with_login("first.do"),
        client._get_json_with_login("second.do"),
    ) == [{"ok": True}, {"ok": True}]
    client._login.assert_awaited_once()


async def test_missing_balance_is_data_error_without_login(client):
    client._get_json = AsyncMock(return_value={})
    client._login = AsyncMock()
    with pytest.raises(LotteryDataError, match="totalAmt"):
        await client.balance()
    client._login.assert_not_awaited()


@pytest.mark.parametrize("stage", ["login", "refresh"])
async def test_setup_failure_can_be_retried_with_a_fresh_client(mock_hass, stage):
    entry = SimpleNamespace(
        entry_id="lottery",
        data={
            "service": "dh_lottery",
            "username": "test-user",
            "password": "test-password",
        },
    )
    first = MagicMock(login=AsyncMock(), close=AsyncMock())
    second = MagicMock(login=AsyncMock(), close=AsyncMock())
    coordinator = MagicMock(async_config_entry_first_refresh=AsyncMock())
    failure = (
        LotteryConnectionError("login timeout")
        if stage == "login"
        else ConfigEntryNotReady("first refresh failed")
    )
    if stage == "login":
        first.login.side_effect = failure
    else:
        coordinator.async_config_entry_first_refresh.side_effect = [failure, None]
    with (
        patch(
            "custom_components.korea_incubator.lottery.LotteryClient",
            side_effect=[first, second],
        ),
        patch(
            "custom_components.korea_incubator.lottery.LotteryCoordinator",
            return_value=coordinator,
        ),
        patch(
            "custom_components.korea_incubator._async_setup_lottery_services",
            new_callable=AsyncMock,
        ),
    ):
        with pytest.raises(ConfigEntryNotReady) as caught:
            await async_setup_entry(mock_hass, entry)
        if stage == "refresh":
            assert caught.value is failure
        else:
            assert caught.value.__cause__ is failure
        first.close.assert_awaited_once()
        assert entry.entry_id not in mock_hass.data[DOMAIN]
        mock_hass.config_entries.async_forward_entry_setups.assert_not_awaited()
        assert await async_setup_entry(mock_hass, entry)
    assert mock_hass.data[DOMAIN][entry.entry_id]["device"] is second
    second.close.assert_not_awaited()


@pytest.mark.parametrize("failure", [asyncio.CancelledError(), RuntimeError("bug")])
async def test_setup_preserves_cancellation_and_unexpected_errors(mock_hass, failure):
    entry = SimpleNamespace(
        data={
            "service": "dh_lottery",
            "username": "test-user",
            "password": "test-password",
        }
    )
    client = MagicMock(login=AsyncMock(side_effect=failure), close=AsyncMock())
    with patch(
        "custom_components.korea_incubator.lottery.LotteryClient", return_value=client
    ):
        with pytest.raises(type(failure)) as caught:
            await async_setup_entry(mock_hass, entry)
    assert caught.value is failure
    client.close.assert_awaited_once()


@pytest.mark.parametrize("cancel", [False, True])
async def test_failed_or_cancelled_refresh_drains_other_requests(cancel):
    started = asyncio.Event()
    finished = asyncio.Event()

    async def pending():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            finished.set()

    async def failure():
        await started.wait()
        if cancel:
            await asyncio.Event().wait()
        raise LotteryHTTPError("test.do", 503)

    coordinator = object.__new__(LotteryCoordinator)
    coordinator.client = MagicMock(balance=AsyncMock(return_value=Balance(0, 0)))
    methods = (
        "pension_winning_numbers",
        "pension_purchase_history",
        "pension_winning_history",
        "pension_high_prize_history",
        "lotto_645_winning_numbers",
        "lotto_645_purchase_history",
        "lotto_645_winning_history",
        "lotto_645_high_prize_history",
        "pension_unsettled_games",
        "lotto_645_unsettled_games",
    )
    for method in methods:
        setattr(coordinator.client, method, AsyncMock(return_value=[]))
    coordinator.client.pension_winning_numbers.side_effect = failure
    coordinator.client.lotto_645_winning_numbers.side_effect = pending
    task = asyncio.create_task(coordinator._async_read_data())
    if cancel:
        await started.wait()
        task.cancel()
    with pytest.raises(asyncio.CancelledError if cancel else UpdateFailed):
        await task
    assert finished.is_set()
