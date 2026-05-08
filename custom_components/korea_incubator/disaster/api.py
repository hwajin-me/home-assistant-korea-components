"""Disaster message API (재난안전데이터포털).

safetydata.go.kr drops connections from clients with Python's default TLS
fingerprint ("Connection reset by peer" during SSL handshake). curl_cffi's
browser impersonation produces a TLS ClientHello the server accepts — but
the server's TLS stack is picky about which profile, and the bare alias
``"chrome"`` (which resolves to whichever Chrome curl_cffi has packaged
most recently) sometimes gets reset. We try a small list of widely-tested
profiles in order and reuse the first one that works for the rest of the
process lifetime.
"""
from __future__ import annotations
import asyncio
import json
import logging
import xml.etree.ElementTree as ET
from typing import Any

from curl_cffi import requests as cffi_requests

_LOGGER = logging.getLogger(__name__)
DISASTER_URL = "https://www.safetydata.go.kr/V2/api/DSSP-IF-00247"
_TIMEOUT = 20

# Order matters: middle-aged Chrome profiles are the most consistently
# accepted by Korean government endpoints. Newer ones occasionally trip
# server-side TLS feature checks; very old ones get rejected by HSTS.
_IMPERSONATE_PROFILES = (
    "chrome120",
    "chrome124",
    "chrome131",
    "chrome116",
    "safari17_0",
)
_BROWSER_HEADERS = {
    "Accept": "application/json, text/xml, */*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Connection": "keep-alive",
}

# Cache the first profile we observed to work — avoids burning seconds on
# retries every poll once we know which one the server likes.
_working_profile: str | None = None


async def validate_disaster_api(api_key: str) -> bool:
    try:
        await fetch_disaster_messages(api_key, count=1)
        return True
    except Exception:
        return False


def _parse_payload(text: str) -> list[dict[str, Any]]:
    try:
        root = ET.fromstring(text)
        return [
            {
                "message": item.findtext("MSG_CN", ""),
                "area": item.findtext("RCPTN_RGN_NM", ""),
                "create_date": item.findtext("CRT_DT", ""),
                "level": item.findtext("EMRG_STEP_NM", ""),
                "disaster_type": item.findtext("DST_SE_NM", ""),
            }
            for item in root.findall(".//row")
        ]
    except ET.ParseError:
        pass
    data = json.loads(text)
    body = data.get("body", [])
    return [
        {
            "message": i.get("MSG_CN", ""),
            "area": i.get("RCPTN_RGN_NM", ""),
            "create_date": i.get("CRT_DT", ""),
            "level": i.get("EMRG_STEP_NM", ""),
            "disaster_type": i.get("DST_SE_NM", ""),
        }
        for i in body
    ]


async def _fetch_with_profile(profile: str, params: dict[str, str]) -> str:
    async with cffi_requests.AsyncSession(impersonate=profile) as s:
        r = await s.get(
            DISASTER_URL,
            params=params,
            headers=_BROWSER_HEADERS,
            timeout=_TIMEOUT,
        )
        return r.text


async def fetch_disaster_messages(api_key: str, count: int = 30) -> list[dict[str, Any]]:
    global _working_profile
    params = {"serviceKey": api_key, "numOfRows": str(count), "pageNo": "1"}

    # Build the order to try: known-good first, then the rest.
    if _working_profile and _working_profile in _IMPERSONATE_PROFILES:
        ordered = (_working_profile, *(p for p in _IMPERSONATE_PROFILES if p != _working_profile))
    else:
        ordered = _IMPERSONATE_PROFILES

    last_err: Exception | None = None
    for attempt, profile in enumerate(ordered):
        try:
            text = await _fetch_with_profile(profile, params)
            if profile != _working_profile:
                _LOGGER.info("Disaster API: using impersonation profile %s", profile)
                _working_profile = profile
            return _parse_payload(text)
        except Exception as err:  # noqa: BLE001 — curl_cffi raises plain Exception subclasses
            last_err = err
            _LOGGER.debug(
                "Disaster API attempt %d with %s failed: %s",
                attempt + 1,
                profile,
                err,
            )
            # Short backoff before trying the next profile so we don't hammer
            # a flapping server with a tight loop.
            if attempt + 1 < len(ordered):
                await asyncio.sleep(0.5 * (attempt + 1))

    raise RuntimeError(
        f"safetydata.go.kr rejected all impersonation profiles: {last_err}"
    ) from last_err
