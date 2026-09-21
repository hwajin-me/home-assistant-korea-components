"""Cookie-free Kakao web search and place details (unofficial endpoints)."""

from __future__ import annotations

import asyncio
import math
import re
from urllib.parse import urlencode

import aiohttp
from yarl import URL

HEADERS = {
    "Referer": "https://map.kakao.com/",
    "Origin": "https://map.kakao.com",
    "User-Agent": "Mozilla/5.0",
    "X-Requested-With": "XMLHttpRequest",
}
PAGE_SIZE = 15


class KakaoError(Exception):
    """Sanitized error safe to show in a flow or log."""


async def _request(session, method, url, **kwargs):
    try:
        async with session.request(
            method,
            url,
            timeout=aiohttp.ClientTimeout(total=20),
            allow_redirects=False,
            **kwargs,
        ) as response:
            if response.status != 200:
                raise KakaoError(f"Kakao HTTP {response.status}")
            result = await response.json()
            if not isinstance(result, dict):
                raise KakaoError("Kakao response is not an object")
            return result
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
        # Never log request headers, signed tokens, response bodies or cookies.
        raise KakaoError(f"Kakao request failed ({type(err).__name__})") from None


async def async_search(session, query, page=1):
    """Mint a token for the exact encoded URL; do not persist/reuse it."""
    path = "/api/v1/mapsearch/map?" + urlencode(
        {"q": query, "msFlag": "A", "sort": 0, "page": page}
    )
    gate = await _request(
        session,
        "POST",
        "https://map.kakao.com/api/v1/settings/web/gate-token",
        headers=HEADERS,
        json={"method": "GET", "url": path, "body": ""},
    )
    token = gate.get("token")
    if not isinstance(token, str) or not token:
        raise KakaoError("Kakao gate token unavailable; verification may be required")
    data = await _request(
        session,
        "GET",
        URL("https://map.kakao.com" + path, encoded=True),
        headers={**HEADERS, "x-kmap-captcha-token": token},
    )
    try:
        items = data["place"]
        # page_count is the accessible RESULT count (capped at 500), not pages.
        total = int(data["page_count"])
        if not isinstance(items, list) or total < 0 or int(data["page"]) != page:
            raise ValueError
        candidates = {}
        for item in items:
            if not isinstance(item, dict):
                raise TypeError
            identity = str(item.get("confirmid", ""))
            if re.fullmatch(r"[0-9]+", identity) and item.get("name"):
                candidates[identity] = {
                    "id": identity,
                    "name": str(item["name"]),
                    "address": str(
                        item.get("new_address") or item.get("address") or ""
                    ),
                    "phone": str(item.get("tel") or ""),
                }
        if not items and (page - 1) * PAGE_SIZE < total:
            raise ValueError
        return list(candidates.values()), max(1, math.ceil(total / PAGE_SIZE))
    except (KeyError, ValueError, TypeError, OverflowError):
        raise KakaoError("Kakao search response is incomplete") from None


async def async_place(session, place_id):
    if not re.fullmatch(r"[0-9]+", str(place_id)):
        raise KakaoError("Invalid Kakao place ID")
    data = await _request(
        session,
        "GET",
        f"https://place.map.kakao.com/places/panel3/{place_id}",
        headers={
            "Referer": f"https://place.map.kakao.com/{place_id}",
            "User-Agent": "Mozilla/5.0",
            "appversion": "6.6.0",
            "pf": "PC",
        },
    )
    summary = data.get("summary")
    if not isinstance(summary, dict) or str(summary.get("confirm_id")) != str(place_id):
        raise KakaoError("Kakao place identity missing or mismatched")
    hours = data.get("open_hours") or {}
    if not isinstance(hours, dict):
        raise KakaoError("Kakao opening hours malformed")
    # Keep relevant details only; never persist reviews, visitors, photos or tokens.
    return {"summary": summary, "open_hours": hours}


def _normal(value):
    return re.sub(r"[^0-9a-z가-힣]", "", str(value).lower())


def _address(value):
    value = str(value).strip()
    for suffix in ("특별자치도", "특별자치시", "특별시", "광역시"):
        value = value.replace(suffix, "")
    # Compare the complete road+building portion, not a substring (7 != 70).
    match = re.match(r"(.+?(?:로|길)\s*\d+(?:-\d+)?)(?:\s|,|\(|$)", value)
    return _normal(match[1]) if match else _normal(value)


def exact_candidate(record, candidates):
    """Name AND address/phone; ambiguous duplicates always require selection."""
    name = _normal(record.get("BPLC_NM", ""))
    address = _address(record.get("ROAD_NM_ADDR") or record.get("LOTNO_ADDR") or "")
    phone = re.sub(r"\D", "", record.get("TELNO") or "")
    matches = [
        candidate
        for candidate in candidates
        if name
        and _normal(candidate["name"]) == name
        and (
            (address and _address(candidate["address"]) == address)
            or (len(phone) >= 8 and re.sub(r"\D", "", candidate["phone"]) == phone)
        )
    ]
    return matches[0] if len(matches) == 1 else None
