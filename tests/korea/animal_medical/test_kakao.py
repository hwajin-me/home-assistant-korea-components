"""Signed URL fidelity, sanitized failures and conservative place identity."""

from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from custom_components.korea_incubator.animal_medical.kakao import (
    KakaoError,
    _request,
    async_place,
    async_search,
    exact_candidate,
)


def session_for(*responses):
    session = MagicMock()
    calls = []
    for status, body in responses:
        response = MagicMock(status=status)
        response.json = AsyncMock(
            side_effect=body if isinstance(body, Exception) else None, return_value=body
        )
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=response)
        context.__aexit__ = AsyncMock(return_value=False)
        calls.append(context)
    session.request.side_effect = calls
    return session


@pytest.mark.asyncio
async def test_signed_search_pagination():
    session = session_for(
        (200, {"token": "ephemeral"}),
        (
            200,
            {
                "page": 2,
                "page_count": 500,
                "place_totalcount": 1026,
                "place": [
                    {
                        "confirmid": "1",
                        "name": "A",
                        "new_address": "Road",
                        "tel": "123",
                    },
                    {"confirmid": 2, "name": "B", "address": "Lot"},
                    {"confirmid": "invalid", "name": "C"},
                    {"confirmid": "3"},
                ],
            },
        ),
    )
    items, pages = await async_search(session, "서울 동물병원", 2)
    assert pages == 34 and len(items) == 2
    post, get = session.request.call_args_list
    assert str(get.args[1]) == "https://map.kakao.com" + post.kwargs["json"]["url"]
    assert "%EC%84%9C%EC%9A%B8" in str(get.args[1])
    assert "page=2" in str(get.args[1])
    assert get.kwargs["headers"]["x-kmap-captcha-token"] == "ephemeral"
    assert "Cookie" not in get.kwargs["headers"]
    assert not get.kwargs["allow_redirects"]
    assert items[1] == {"id": "2", "name": "B", "address": "Lot", "phone": ""}


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [[], {}, {"token": ""}, {"token": 1}])
async def test_bad_gate(body):
    with pytest.raises(KakaoError):
        await async_search(session_for((200, body)), "A")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "update",
    [
        {"page": 2},
        {"page_count": -1},
        {"page_count": "bad"},
        {"page_count": None},
        {"page_count": float("inf")},
        {"place": None},
        {"place": [None]},
        {"place": []},
        {"page_count": 1, "page": None},
    ],
)
async def test_bad_search_schema(update):
    body = {
        "page": 1,
        "page_count": 1,
        "place": [{"confirmid": "1", "name": "A"}],
        **update,
    }
    with pytest.raises(KakaoError, match="incomplete"):
        await async_search(session_for((200, {"token": "secret"}), (200, body)), "A")


@pytest.mark.asyncio
async def test_search_missing_fields_and_empty():
    with pytest.raises(KakaoError):
        await async_search(session_for((200, {"token": "t"}), (200, {})), "A")
    assert await async_search(
        session_for(
            (200, {"token": "t"}), (200, {"page": 1, "page_count": 0, "place": []})
        ),
        "A",
    ) == ([], 1)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,body",
    [
        (403, {}),
        (429, {}),
        (302, {}),
        (500, {}),
        (200, []),
        (200, ValueError("secret token")),
        (200, TimeoutError("secret cookie")),
        (200, aiohttp.ClientConnectionError("secret URL")),
    ],
)
async def test_safe_http_errors(status, body):
    with pytest.raises(KakaoError) as error:
        await _request(session_for((status, body)), "GET", "https://example.test")
    assert "secret" not in str(error.value)


@pytest.mark.asyncio
async def test_place_relevant_details_only():
    details = {
        "summary": {"confirm_id": "123", "point": {"lat": 37, "lon": 127}},
        "open_hours": {"headline": {}},
        "visitor": "private",
        "photos": [],
    }
    session = session_for((200, details))
    result = await async_place(session, "123")
    assert {key: result[key] for key in ("summary", "open_hours")} == {
        key: details[key] for key in ("summary", "open_hours")
    }
    assert "visitor" not in result
    assert result["media"]["photos"] == []
    assert "appversion" in session.request.call_args.kwargs["headers"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "place_id,body",
    [
        ("../foo", {}),
        ("1", {}),
        ("1", {"summary": []}),
        ("1", {"summary": {"confirm_id": "2"}}),
        ("1", {"summary": {"confirm_id": "1"}, "open_hours": [1]}),
    ],
)
async def test_invalid_place(place_id, body):
    with pytest.raises(KakaoError):
        await async_place(session_for((200, body)), place_id)


@pytest.mark.asyncio
async def test_no_hours_is_valid():
    assert (
        await async_place(session_for((200, {"summary": {"confirm_id": "1"}})), "1")
    )["open_hours"] == {}


def test_exact_matching(record):
    candidate = {
        "id": "1",
        "name": record["BPLC_NM"],
        "address": "서울 종로구 사직로 1 2층",
        "phone": "",
    }
    assert exact_candidate(record, [candidate]) == candidate
    assert exact_candidate(record, [candidate, {**candidate, "id": "2"}]) is None
    assert (
        exact_candidate(record, [{**candidate, "address": "서울 종로구 사직로 10"}])
        is None
    )
    assert exact_candidate(record, [{**candidate, "name": "다른동물병원"}]) is None
    assert exact_candidate(
        record, [{**candidate, "address": "이전 주소", "phone": "021234567"}]
    )
    assert exact_candidate({}, [candidate]) is None
    assert exact_candidate(
        {"BPLC_NM": "A", "LOTNO_ADDR": "주소"},
        [{"id": "1", "name": "A", "address": "주소", "phone": ""}],
    )
