"""Actual curl_cffi contract, bounded authentication recovery and error handling."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from curl_cffi import AsyncSession
from curl_cffi.requests.exceptions import RequestException as RequestsError

from custom_components.korea_incubator.kepco.api import KepcoApiClient
from custom_components.korea_incubator.kepco.exceptions import KepcoAuthError

pytestmark = pytest.mark.asyncio


@pytest.fixture
def session():
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def client(session):
    client = KepcoApiClient(session)
    client.set_credentials("test_user", "test_password")
    return client


def response(status=200, body=None, url="https://pp.kepco.co.kr:8030/api"):
    result = MagicMock(status_code=status, text=json.dumps(body), url=url)
    if status >= 400:
        result.raise_for_status.side_effect = RequestsError(f"HTTP {status}")
    return result


@pytest.mark.parametrize(
    "method,path",
    [
        ("async_get_recent_usage", "recent_usage.do"),
        ("async_get_usage_info", "usage_info.do"),
    ],
)
async def test_usage_success(client, session, method, path):
    body = {"result": {"F_AP_QT": "123.45"}}
    session.request.return_value = response(body=body)
    assert await getattr(client, method)() == body
    assert session.request.call_args.args[0] == "POST"
    assert session.request.call_args.args[1].endswith(path)


@pytest.mark.parametrize(
    "status,url",
    [
        (401, "https://example.test/api"),
        (403, "https://example.test/api"),
        (200, "https://pp.kepco.co.kr:8030/intro.do"),
    ],
)
async def test_auth_refresh_once(client, session, status, url):
    session.request.side_effect = [
        response(status, url=url),
        response(body={"ok": True}),
    ]
    with patch.object(
        client, "async_login", new_callable=AsyncMock, return_value=True
    ) as login:
        assert await client.async_get_recent_usage() == {"ok": True}
        login.assert_awaited_once_with("test_user", "test_password")
    assert session.request.await_count == 2


@pytest.mark.parametrize("login_ok", [False, True])
async def test_rejected_or_repeated_auth_failure(client, session, login_ok):
    session.request.return_value = response(401)
    with patch.object(
        client, "async_login", new_callable=AsyncMock, return_value=login_ok
    ) as login:
        with pytest.raises(KepcoAuthError):
            await client.async_get_recent_usage()
        login.assert_awaited_once()
    assert session.request.await_count == (2 if login_ok else 1)


@pytest.mark.parametrize("failure", ["transport", "http", "json"])
async def test_non_auth_error_does_not_relogin(client, session, failure):
    if failure == "transport":
        session.request.side_effect = RequestsError("connection failed")
    elif failure == "http":
        session.request.return_value = response(500)
    else:
        session.request.return_value = response()
        session.request.return_value.text = "invalid JSON"
    with patch.object(client, "async_login", new_callable=AsyncMock) as login:
        with pytest.raises((RequestsError, ValueError)):
            await client.async_get_usage_info()
        login.assert_not_awaited()


@pytest.mark.parametrize(
    "username,password",
    [("", "password"), ("username", ""), (None, "password"), ("username", None)],
)
async def test_invalid_credentials_no_network(client, session, username, password):
    assert await client.async_login(username, password) is False
    assert client.last_error == "Username and password are required"
    session.get.assert_not_awaited()


@pytest.mark.integration
async def test_real_login_invalid_credentials():
    async with AsyncSession() as session:
        assert (
            await KepcoApiClient(session).async_login("invalid_user", "invalid_pass")
            is False
        )


@pytest.mark.integration
async def test_real_api_without_credentials():
    async with AsyncSession() as session:
        with pytest.raises(KepcoAuthError):
            await KepcoApiClient(session).async_get_recent_usage()
