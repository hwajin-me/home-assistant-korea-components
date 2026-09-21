"""List-only public-data API for animal hospitals and pharmacies."""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import quote, unquote

import aiohttp

from . import ANIMAL_MEDICAL_TYPES

MAX_ROWS = 100
AUTH_CODES = {"-4", "20", "30", "31"}


class AnimalMedicalApiError(Exception):
    """The API is unavailable or returned invalid data."""


class AnimalMedicalAuthError(AnimalMedicalApiError):
    """The service key is invalid, expired or not approved."""


def _check_code(code: str, message: str = "") -> None:
    code = code.strip()
    detail = f" ({message})" if message else ""
    if code in AUTH_CODES:
        raise AnimalMedicalAuthError(f"API authentication error ({code}){detail}")
    if code not in {"00", "0"}:
        category = {
            "22": "daily quota exceeded",
            "23": "rate limit exceeded",
            "-10": "quota exceeded",
            "10": "invalid parameters",
            "-2": "invalid parameters",
            "-11": "required parameters missing",
            "05": "upstream timeout",
            "-5": "upstream server error",
        }.get(code, "API error")
        raise AnimalMedicalApiError(f"{category} ({code[:30]}){detail}")


def _parse_response(text: str) -> tuple[list[dict[str, Any]], int]:
    """Validate JSON and recognize XML gateway errors for JSON requests."""
    if text.lstrip().startswith("<"):
        try:
            root = ET.fromstring(text)
        except ET.ParseError as err:
            raise AnimalMedicalApiError("Invalid API XML response") from err
        code = root.findtext(".//returnReasonCode") or root.findtext(".//resultCode")
        message = (
            root.findtext(".//returnAuthMsg")
            or root.findtext(".//errMsg")
            or root.findtext(".//resultMsg")
            or ""
        )
        _check_code(code or "unknown", message)
        raise AnimalMedicalApiError("Expected JSON response")
    try:
        payload = json.loads(text)
        if "OpenAPI_ServiceResponse" in payload:
            header = payload["OpenAPI_ServiceResponse"]["cmmMsgHeader"]
            _check_code(
                str(header.get("returnReasonCode", "unknown")),
                str(header.get("returnAuthMsg") or header.get("errMsg") or ""),
            )
        response = payload["response"]
        code = str(response["header"]["resultCode"])
        _check_code(code, str(response["header"].get("resultMsg") or ""))
        body = response["body"]
        count = body["totalCount"]
        if isinstance(count, bool) or not str(count).isdigit():
            raise ValueError("Invalid total count")
        total = int(count)
        container = body.get("items")
        if container in (None, ""):
            items = []
        else:
            items = container.get("item")
            if items in (None, ""):
                items = []
            elif isinstance(items, dict):
                items = [items]
        if not isinstance(items, list) or any(not isinstance(i, dict) for i in items):
            raise ValueError("Invalid items")
        if len(items) > total:
            raise ValueError("Inconsistent total count")
    except (ValueError, KeyError, TypeError, AttributeError) as err:
        raise AnimalMedicalApiError(
            f"Invalid API JSON response: {type(err).__name__}: {str(err)[:200]}"
        ) from err
    return items, total


async def async_fetch_institutions(
    session: aiohttp.ClientSession,
    api_key: str,
    institution_type: str,
    *,
    page: int = 1,
    rows: int = MAX_ROWS,
    road_address: str = "",
    municipality_code: str = "",
    business_name: str = "",
) -> tuple[list[dict[str, Any]], int]:
    """Fetch a page with bounded size and supported query conditions."""
    if institution_type not in ANIMAL_MEDICAL_TYPES:
        raise AnimalMedicalApiError("Unknown animal medical institution type")
    params = {
        # Accept both portal key formats; aiohttp performs the URL encoding.
        "serviceKey": unquote(api_key.strip()),
        "pageNo": str(max(1, page)),
        "numOfRows": str(min(MAX_ROWS, max(1, rows))),
        "returnType": "json",
    }
    for field, operator, value in (
        ("ROAD_NM_ADDR", "LIKE", road_address),
        ("OPN_ATMY_GRP_CD", "EQ", municipality_code),
        ("BPLC_NM", "LIKE", business_name),
    ):
        if value.strip():
            params[f"cond[{field}::{operator}]"] = value.strip()
    try:
        async with session.get(
            ANIMAL_MEDICAL_TYPES[institution_type]["url"],
            params=params,
            timeout=aiohttp.ClientTimeout(total=20),
        ) as response:
            if response.status in (401, 403):
                raise AnimalMedicalAuthError(
                    f"HTTP {response.status}: API key not authorized"
                )
            if response.status >= 400:
                try:
                    _parse_response(await response.text())
                except AnimalMedicalApiError as err:
                    raise type(err)(f"HTTP {response.status}: {err}") from None
            response.raise_for_status()
            return _parse_response(await response.text())
    except AnimalMedicalApiError as err:
        # Upstream messages can echo credentials. Keep useful code/message only.
        detail = str(err)
        for secret in {
            api_key.strip(),
            unquote(api_key.strip()),
            quote(unquote(api_key.strip()), safe=""),
        }:
            if secret:
                detail = detail.replace(secret, "[redacted]")
        detail = re.sub(
            r"(?i)servicekey\s*[=:]\s*[^\s&<>]+", "serviceKey=[redacted]", detail
        )
        detail = " ".join(detail.split())[:500]
        raise type(err)(detail) from None
    except aiohttp.ClientResponseError as err:
        raise AnimalMedicalApiError(
            f"HTTP {err.status}: API server request failed"
        ) from None
    except TimeoutError:
        raise AnimalMedicalApiError("API request timed out (20 seconds)") from None
    except UnicodeError:
        raise AnimalMedicalApiError("API response text decoding failed") from None
    except aiohttp.ClientError as err:
        raise AnimalMedicalApiError(
            f"API connection failed (DNS/TLS/network): {type(err).__name__}"
        ) from None


def find_selected_institution(
    items: list[dict[str, Any]], management_number: str, municipality_code: str
) -> dict[str, Any] | None:
    """Disambiguate names using the municipality and management number."""
    return next(
        (
            item
            for item in items
            if item.get("MNG_NO") == management_number
            and item.get("OPN_ATMY_GRP_CD") == municipality_code
        ),
        None,
    )
