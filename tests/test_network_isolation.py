"""Accidental live traffic fails unit tests before any request is sent."""

import aiohttp
import pytest
from curl_cffi import AsyncSession, Session


async def test_aiohttp_external_requests_are_blocked():
    async with aiohttp.ClientSession() as session:
        with pytest.raises(pytest.fail.Exception, match="External HTTP"):
            await session.get("https://example.invalid/")


async def test_curl_external_requests_are_blocked():
    async with AsyncSession() as session:
        with pytest.raises(pytest.fail.Exception, match="External HTTP"):
            await session.get("https://example.invalid/")


def test_sync_curl_external_requests_are_blocked():
    with (
        Session() as session,
        pytest.raises(pytest.fail.Exception, match="External HTTP"),
    ):
        session.get("https://example.invalid/")
