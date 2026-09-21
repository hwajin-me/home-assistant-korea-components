"""RSA HTML parsing and real PKCS#1 decryption of login payloads."""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from Crypto.Cipher import PKCS1_v1_5
from Crypto.PublicKey import RSA

from custom_components.korea_incubator.kepco.api import KepcoApiClient
from custom_components.korea_incubator.kepco.exceptions import KepcoAuthError
from custom_components.korea_incubator.utils import RSAKey, pkcs1pad2


@pytest.fixture(scope="module")
def private_key():
    return RSA.generate(1024)


@pytest.fixture
def login_client(private_key):
    session = MagicMock()
    html = f'<input id="RSAModulus" value="{private_key.n:x}"><input id="RSAExponent" value="{private_key.e:x}"><input id="SESSID" value="session-secret">'
    session.get = AsyncMock(return_value=MagicMock(status_code=200, text=html))
    session.post = AsyncMock(
        return_value=MagicMock(
            status_code=200, url="https://pp.kepco.co.kr:8030/confirmInfo.do"
        )
    )
    return KepcoApiClient(session)


async def test_session_and_rsa_key(login_client, private_key):
    assert await login_client.async_get_session_and_rsa_key() == (
        f"{private_key.n:x}",
        f"{private_key.e:x}",
        "session-secret",
    )
    login_client._session.get.return_value.raise_for_status.assert_called_once()


@pytest.mark.parametrize(
    "html",
    [
        "<html></html>",
        '<input id="RSAModulus"><input id="RSAExponent" value="10001"><input id="SESSID" value="s">',
    ],
)
async def test_missing_rsa_fields(login_client, html):
    login_client._session.get.return_value.text = html
    with pytest.raises(KepcoAuthError):
        await login_client.async_get_session_and_rsa_key()
    assert await login_client.async_login("u", "p") is False


@pytest.mark.parametrize("text", ["test_username", "비밀번호🙂"])
def test_rsa_encryption_roundtrip(private_key, text):
    key = RSAKey()
    key.set_public(f"{private_key.n:x}", f"{private_key.e:x}")
    ciphertext = bytes.fromhex(key.encrypt(text)).rjust(
        private_key.size_in_bytes(), b"\x00"
    )
    assert PKCS1_v1_5.new(private_key).decrypt(ciphertext, b"bad") == text.encode()
    assert key.encrypt(text) != key.encrypt(text)


def test_rsa_invalid_and_oversized():
    with pytest.raises(ValueError):
        RSAKey().set_public("", "10001")
    with pytest.raises(ValueError, match="Message too long"):
        pkcs1pad2("x" * 100, 64)


async def test_login_payload_and_no_secrets_logged(login_client, private_key, caplog):
    caplog.set_level(logging.DEBUG)
    assert await login_client.async_login("secret-user", "secret-password") is True
    form = login_client._session.post.call_args.kwargs["data"]
    for name, plaintext in (("USER_ID", "secret-user"), ("USER_PW", "secret-password")):
        prefix, encoded = form[name].split("_", 1)
        assert prefix == "session-secret"
        encrypted = bytes.fromhex(encoded).rjust(private_key.size_in_bytes(), b"\x00")
        assert (
            PKCS1_v1_5.new(private_key).decrypt(encrypted, b"bad") == plaintext.encode()
        )
    for secret in ("secret-user", "secret-password", "session-secret", form["USER_ID"]):
        assert secret not in caplog.text


@pytest.mark.parametrize(
    "failure", ["intro", "rsa", "encrypt", "post", "rejected", "http"]
)
async def test_login_failures(login_client, failure):
    if failure == "intro":
        login_client._session.get.side_effect = TimeoutError("sensitive body")
    elif failure == "rsa":
        login_client._session.get.return_value.text = '<input id="RSAModulus" value="bad-key"><input id="RSAExponent" value="1"><input id="SESSID" value="s">'
    elif failure == "post":
        login_client._session.post.side_effect = TimeoutError("sensitive body")
    elif failure == "rejected":
        login_client._session.post.return_value.url = (
            "https://pp.kepco.co.kr:8030/login"
        )
    elif failure == "http":
        login_client._session.post.return_value.status_code = 503
    if failure == "encrypt":
        with patch(
            "custom_components.korea_incubator.kepco.api.RSAKey.encrypt",
            return_value=None,
        ):
            assert await login_client.async_login("user", "password") is False
    else:
        assert await login_client.async_login("user", "password") is False
    assert login_client.last_error
    assert "sensitive body" not in login_client.last_error


async def test_rejected_login_does_not_expose_reflected_body(login_client, caplog):
    caplog.set_level(logging.DEBUG)
    login_client._session.post.return_value.url = "https://pp.kepco.co.kr:8030/login"
    login_client._session.post.return_value.text = (
        "private-user private-password session-secret"
    )
    assert await login_client.async_login("private-user", "private-password") is False
    for secret in ("private-user", "private-password", "session-secret"):
        assert secret not in caplog.text
        assert secret not in login_client.last_error
