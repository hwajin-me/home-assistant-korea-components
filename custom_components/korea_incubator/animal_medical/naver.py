"""Optional Naver Place enrichment, without cookies or access-limit bypasses."""

import asyncio
import json
import re
from datetime import timedelta
from urllib.parse import urlencode, urlsplit

import aiohttp

from .hours import SEOUL, schedule
from .media import photo_url

# Naver serves the public document differently for a truncated User-Agent.
# Keep one deterministic compatibility profile, not rotating identities or tokens.
DOCUMENT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/153.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": "https://map.naver.com/",
}


class NaverError(Exception):
    """Sanitized public error."""

    def __init__(self, message, *, code="request_failed"):
        super().__init__(message)
        self.code = code


async def async_search(session, query, *, latitude=37.5665, longitude=126.978):
    """Instant search is public, but capped; never treat it as exhaustive."""
    data = await _get(
        session,
        "https://map.naver.com/p/api/search/instant-search?"
        + urlencode({"query": query, "coords": f"{latitude},{longitude}"}),
        json_response=True,
    )
    try:
        rows = data["place"]
        if not isinstance(rows, list):
            raise TypeError
        return [
            {
                "id": place_id(row["id"]),
                "name": str(row["title"]),
                "address": str(row.get("roadAddress") or row.get("jibunAddress") or ""),
            }
            for row in rows[:10]
        ]
    except (KeyError, TypeError, ValueError):
        raise NaverError("Naver search response malformed") from None


def place_id(value):
    value = str(value).strip()
    if re.fullmatch(r"[0-9]+", value):
        return value
    url = urlsplit(value)
    if (
        url.scheme == "https"
        and url.hostname
        in ("map.naver.com", "pcmap.place.naver.com", "m.place.naver.com")
        and not url.username
        and not url.password
        and url.port in (None, 443)
    ):
        match = re.fullmatch(
            r"/(?:p/entry/)?(?:place|pet|hospital|pharmacy)/([0-9]+)(?:/home)?/?",
            url.path,
        )
        if match:
            return match[1]
    raise ValueError("Enter a Naver Place URL or numeric place ID")


def parse_hours(html, identifier, stamp):
    """Read JSON only, never execute page scripts or retain unrelated page data."""
    marker = re.search(r"window\.__APOLLO_STATE__\s*=\s*", html)
    if marker is None:
        if "서비스 이용이 제한" in html or "과도한 접근 요청" in html:
            raise NaverError(
                "Naver document access restricted", code="access_restricted"
            )
        raise NaverError(
            "Naver hours unavailable (page structure changed)", code="page_changed"
        )
    try:
        state = json.JSONDecoder().raw_decode(html[marker.end() :])[0]
        details = [
            value
            for key, value in state["ROOT_QUERY"].items()
            if key.startswith("placeDetail(")
            and isinstance(value, dict)
            and value.get("base", {}).get("__ref") == f"PlaceDetailBase:{identifier}"
        ]
        groups = details[0]["newBusinessHours"]
        if not isinstance(groups, list) or len(groups) != 1:
            raise ValueError
        group = groups[0]
        today = stamp.astimezone(SEOUL).date()
        days = []
        for row in group["businessHours"]:
            label = row["day"]
            # The displayed seven-day view, not an indefinite weekly recurrence.
            if label in "월화수목금토일" and len(label) == 1:
                target = today + timedelta(
                    days=("월화수목금토일".index(label) - today.weekday()) % 7
                )
                label = f"{label}({target.month}/{target.day})"
            day = {"day_of_the_week_desc": label}
            opening = row.get("businessHours")
            if opening:
                day["on_days"] = {
                    "start_end_time_desc": f"{opening['start']} ~ {opening['end']}",
                    "break_times_desc": [
                        f"{b['start']} ~ {b['end']} 휴게시간"
                        for b in row.get("breakHours") or []
                    ],
                }
                if (
                    opening["start"] == opening["end"] == "00:00"
                    and row.get("showEndsNextDay") is True
                ):
                    day["on_days"]["start_end_time_desc"] = "24시간"
            else:
                reason = row.get("description") or ""
                day["off_days_desc"] = re.sub(
                    r"\s*\(매주 [월화수목금토일]요일\)$", "", reason
                )
            days.append(day)
        normalized = schedule(
            {"week_from_today": {"week_periods": [{"days": days}]}}, stamp
        )
        # Explicit upcoming ranges can extend beyond the displayed week. Resolve
        # only within the next year, and cap a single range to 31 days.
        for closed in group.get("comingIrregularClosedDays") or []:
            start = next(
                (
                    today + timedelta(days=n)
                    for n in range(-30, 366)
                    if (today + timedelta(days=n)).strftime("%m/%d")
                    == closed["startDate"]
                ),
                None,
            )
            if start is None:
                continue
            end = next(
                (
                    start + timedelta(days=n)
                    for n in range(31)
                    if (start + timedelta(days=n)).strftime("%m/%d")
                    == closed["endDate"]
                ),
                None,
            )
            if end is not None and end >= today:
                for n in range((end - start).days + 1):
                    normalized[(start + timedelta(days=n)).isoformat()] = {
                        "open": None,
                        "breaks": [],
                        "closure_reason": str(closed.get("name") or "임시휴무")[:255],
                    }
        return {"schedule": normalized, "hours": group}
    except (ValueError, TypeError, KeyError, IndexError, AttributeError):
        raise NaverError(
            "Naver hours malformed or place identity mismatched", code="invalid_hours"
        ) from None


async def _get(session, url, *, json_response=False):
    try:
        async with session.get(
            url,
            headers={**DOCUMENT_HEADERS, "Accept": "application/json"}
            if json_response
            else DOCUMENT_HEADERS,
            timeout=aiohttp.ClientTimeout(total=20),
            allow_redirects=False,
        ) as response:
            if response.status != 200:
                raise NaverError(
                    f"Naver HTTP {response.status}",
                    code="rate_limited"
                    if response.status == 429
                    else "access_denied"
                    if response.status in (401, 403)
                    else "http_error",
                )
            if json_response:
                return await response.json()
            chunks, size = [], 0
            async for chunk in response.content.iter_chunked(65536):
                size += len(chunk)
                if size > 5_000_000:
                    raise NaverError("Naver page exceeds size limit")
                chunks.append(chunk)
            body = b"".join(chunks)
            return body.decode("utf-8")
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
        raise NaverError(f"Naver request failed ({type(err).__name__})") from None


async def async_place(session, identifier, stamp):
    identifier = place_id(identifier)
    data = await _get(
        session,
        f"https://map.naver.com/p/api/place/summary/{identifier}",
        json_response=True,
    )
    try:
        detail = data["data"]["placeDetail"]
        if str(detail["id"]) != identifier:
            raise ValueError
        kind = detail["businessType"]
        if kind not in ("pet", "hospital", "pharmacy", "place"):
            raise ValueError
        result = {
            "place_id": identifier,
            "name": detail["name"],
            "place_url": f"https://map.naver.com/p/entry/place/{identifier}",
            "coordinate": detail.get("coordinate") or {},
            "address": detail.get("address") or {},
            "main_photo": next(
                (
                    url
                    for row in (detail.get("images") or {}).get("images", [])
                    if (url := photo_url(row.get("originalUrl") or row.get("origin")))
                ),
                None,
            ),
            "fetched_at": stamp.isoformat(),
        }
    except (KeyError, TypeError, ValueError, AttributeError):
        raise NaverError("Naver place identity or summary malformed") from None
    try:
        html = await _get(
            session, f"https://pcmap.place.naver.com/{kind}/{identifier}/home"
        )
        result.update(parse_hours(html, identifier, stamp))
    except NaverError as err:
        result["hours_error"] = str(err)
        result["hours_error_code"] = err.code
    return result
