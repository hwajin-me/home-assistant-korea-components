"""Validate public-data credentials without treating an empty dataset as a failure."""

import json
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from urllib.parse import unquote
from zoneinfo import ZoneInfo

import aiohttp


class PublicDataAuthError(ValueError):
    """The service rejected the key or its permissions."""


async def validate_response(session, url, params):
    """Check JSON and XML result headers, including gateway authentication errors."""
    async with session.get(
        url, params=params, timeout=aiohttp.ClientTimeout(total=20)
    ) as response:
        text = await response.text()
        if response.status in {401, 403}:
            raise PublicDataAuthError(f"HTTP {response.status}")
        response.raise_for_status()
    code = message = None
    try:
        data = json.loads(text)
        header = data["response"]["header"]
        code, message = header.get("resultCode"), header.get("resultMsg", "")
    except (ValueError, TypeError, KeyError, AttributeError):
        try:
            root = ET.fromstring(text)
        except ET.ParseError as err:
            raise ConnectionError("The API returned an invalid response") from err
        code = root.findtext(".//resultCode") or root.findtext(".//returnReasonCode")
        message = (
            root.findtext(".//resultMsg") or root.findtext(".//returnAuthMsg") or ""
        )
    normalized = str(code).strip().lstrip("0") or "0" if code is not None else None
    # NO_DATA is a valid response, particularly for earthquake notifications.
    if normalized in {"0", "3"}:
        return
    detail = f"Public Data API {code}: {message}"[:500]
    if normalized in {"20", "30", "31", "32"}:
        raise PublicDataAuthError(detail)
    raise ConnectionError(detail)


async def validate_service(session, service, data):
    """Probe the endpoint actually used by the selected service."""
    key = data.get("api_key", "").strip()
    if not key:
        raise PublicDataAuthError("Enter an API key")
    params = {"serviceKey": unquote(key), "numOfRows": "1", "pageNo": "1"}
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    if service == "airkorea":
        from .airkorea import REALTIME_URL, STATIONS_BY_SIDO, UV_IDX_URL, SIDO_AREA_CODE

        params.update(
            returnType="json",
            stationName=STATIONS_BY_SIDO[data["sido"]][0],
            dataTerm="DAILY",
            ver="1.5",
        )
        await validate_response(session, REALTIME_URL, params)
        if data.get("living_api_key", "").strip():
            await validate_response(
                session,
                UV_IDX_URL,
                {
                    "serviceKey": unquote(data["living_api_key"].strip()),
                    "dataType": "JSON",
                    "areaNo": SIDO_AREA_CODE[data["sido"]],
                    "time": now.strftime("%Y%m%d%H"),
                    "numOfRows": "1",
                    "pageNo": "1",
                },
            )
    elif service == "kma_weather":
        from .kma_weather import VILAGE_URL, SIDO_LIST
        from .kma_weather.api import _base_time_vilage

        nx, ny = next(iter(SIDO_LIST[data["sido"]].values()))
        date, time = _base_time_vilage()
        params.update(
            dataType="JSON", base_date=date, base_time=time, nx=str(nx), ny=str(ny)
        )
        await validate_response(session, VILAGE_URL, params)
    elif service == "earthquake":
        from .earthquake import EQ_URL

        params.update(
            dataType="JSON",
            fromTmFc=(now - timedelta(days=30)).strftime("%Y%m%d"),
            toTmFc=now.strftime("%Y%m%d"),
        )
        await validate_response(session, EQ_URL, params)
