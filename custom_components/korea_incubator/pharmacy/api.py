"""NMC pharmacy list/details with stable HPID identity and safe API errors."""

from __future__ import annotations

import asyncio
import xml.etree.ElementTree as ET
from urllib.parse import unquote

import aiohttp

from ..animal_medical.api import AnimalMedicalApiError, AnimalMedicalAuthError
from . import PAGE_SIZE, PHARMACY_DETAIL_URL, PHARMACY_URL


class PharmacyApiError(AnimalMedicalApiError):
    """Pharmacy transport, quota or data error."""


class PharmacyAuthError(AnimalMedicalAuthError):
    """Pharmacy API key rejected."""


async def _fetch(session, url, api_key, params):
    try:
        async with session.get(
            url,
            params={"serviceKey": unquote(api_key), **params},
            timeout=aiohttp.ClientTimeout(total=20),
        ) as response:
            if response.status in (401, 403):
                raise PharmacyAuthError(f"Pharmacy HTTP {response.status}")
            if response.status != 200:
                raise PharmacyApiError(f"Pharmacy HTTP {response.status}")
            root = ET.fromstring(await response.text())
    except (aiohttp.ClientError, asyncio.TimeoutError, ET.ParseError) as err:
        raise PharmacyApiError(
            f"Pharmacy request failed ({type(err).__name__})"
        ) from None
    code = root.findtext(".//resultCode") or root.findtext(".//returnReasonCode")
    if code not in ("00", "0"):
        message = (
            root.findtext(".//resultMsg")
            or root.findtext(".//returnAuthMsg")
            or "Missing result code"
        )
        for secret in (api_key, unquote(api_key)):
            if secret:
                message = message.replace(secret, "[REDACTED]")
        error = (
            PharmacyAuthError if code in ("20", "30", "31", "32") else PharmacyApiError
        )
        raise error(f"Pharmacy API {code}: {message[:300]}")
    body = root.find("body")
    if body is None:
        raise PharmacyApiError("Pharmacy response missing body")
    records = [
        {child.tag: child.text or "" for child in item}
        for item in body.findall("./items/item")
    ]
    try:
        total = int(body.findtext("totalCount", str(len(records))))
        if total < len(records) or total < 0:
            raise ValueError
    except ValueError:
        raise PharmacyApiError("Invalid pharmacy totalCount") from None
    return records, total


async def fetch_page(session, api_key, q0, q1="", *, name="", page=1, num=PAGE_SIZE):
    return await _fetch(
        session,
        PHARMACY_URL,
        api_key,
        {
            "Q0": q0,
            "Q1": q1,
            "QN": name,
            "ORD": "NAME",
            "pageNo": str(max(1, int(page))),
            "numOfRows": str(min(PAGE_SIZE, max(1, int(num)))),
        },
    )


async def fetch_detail(session, api_key, hpid):
    records, _ = await _fetch(session, PHARMACY_DETAIL_URL, api_key, {"HPID": hpid})
    matches = [record for record in records if record.get("hpid") == hpid]
    if len(matches) != 1:
        raise PharmacyApiError("Selected pharmacy is missing or ambiguous")
    return matches[0]


def weekly_hours(record):
    return {
        name: {
            "start": record.get(f"dutyTime{day}s"),
            "end": record.get(f"dutyTime{day}c"),
        }
        for day, name in enumerate(
            ("mon", "tue", "wed", "thu", "fri", "sat", "sun", "holiday"), 1
        )
    }


async def fetch_complete_detail(session, api_key, hpid):
    """The detail endpoint omits list-only fields such as dutyEtc; merge by HPID."""
    detail = await fetch_detail(session, api_key, hpid)
    name = detail.get("dutyName", "").strip()
    if not name:
        raise PharmacyApiError("Pharmacy detail is missing dutyName")
    # Search using the current name/address, not stale config values after a move.
    address = detail.get("dutyAddr", "").split()
    region = address[0] if address else ""
    page, seen = 1, set()
    while True:
        records, total = await fetch_page(
            session, api_key, region, name=name, page=page
        )
        matches = [r for r in records if r.get("hpid") == hpid]
        if len(matches) == 1:
            return {**matches[0], **detail}
        signature = tuple(r.get("hpid", "") for r in records)
        if len(matches) > 1 or signature in seen or not records:
            raise PharmacyApiError(
                "Pharmacy supplemental list is incomplete or ambiguous"
            )
        seen.add(signature)
        if page * PAGE_SIZE >= total:
            raise PharmacyApiError(
                "Selected pharmacy is missing from supplemental list"
            )
        page += 1


async def fetch_pharmacies(session, api_key, q0, q1="", page=1, num=20):
    """Retain the existing search action response contract, adding ID/raw data."""
    records, _ = await fetch_page(session, api_key, q0, q1, page=page, num=num)
    return [
        {
            "hpid": r.get("hpid"),
            "name": r.get("dutyName", ""),
            "address": r.get("dutyAddr", ""),
            "phone": r.get("dutyTel1", ""),
            "lat": r.get("wgs84Lat", ""),
            "lon": r.get("wgs84Lon", ""),
            "duty_time": {
                name: f"{r.get(f'dutyTime{day}s', '')}~{r.get(f'dutyTime{day}c', '')}"
                for day, name in enumerate(
                    ("월", "화", "수", "목", "금", "토", "일", "공휴일"), 1
                )
                if r.get(f"dutyTime{day}s") or r.get(f"dutyTime{day}c")
            },
            "api_record": r,
        }
        for r in records
    ]
