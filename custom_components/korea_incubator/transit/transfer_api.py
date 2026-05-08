"""Transit path/location search APIs.

Location search: ws.bus.go.kr getLocationInfo (서울시 공공 API)
Path search: ws.bus.go.kr getPathInfoByBusNSub

Note: These APIs require a data.go.kr service key registered for
서울특별시_대중교통환승경로 조회 서비스 (API key = bus_api_key).
The stSrch parameter must be URL-encoded Korean text.
"""
from __future__ import annotations
import logging
import json
import xml.etree.ElementTree as ET
from typing import Any
from urllib.parse import quote
import aiohttp

_LOGGER = logging.getLogger(__name__)

LOC_URL = "http://ws.bus.go.kr/api/rest/pathinfo/getLocationInfo"
PATH_URL = "http://ws.bus.go.kr/api/rest/pathinfo/getPathInfoByBusNSub"


def _extract_items_from_response(text: str) -> list[dict[str, str]]:
    """Extract items from XML or JSON response."""
    # Try XML first
    try:
        root = ET.fromstring(text)
        # Check for error
        header_cd = root.findtext(".//headerCd", "")
        header_msg = root.findtext(".//headerMsg", "")
        if header_cd and header_cd not in ("0", "4"):  # 4 = no data
            _LOGGER.debug("API header: code=%s msg=%s", header_cd, header_msg)

        results = []
        for item in root.iter():
            if item.tag.endswith("itemList") or item.tag == "itemList":
                entry = {}
                for child in item:
                    tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                    entry[tag] = (child.text or "").strip()
                if entry:
                    results.append(entry)
        if results:
            return results
    except ET.ParseError:
        pass

    # Try JSON
    try:
        data = json.loads(text)
        msg_body = data.get("msgBody", {})
        items = msg_body.get("itemList", [])
        if isinstance(items, dict):
            items = [items]
        return items
    except (json.JSONDecodeError, AttributeError):
        pass

    _LOGGER.debug("Could not parse response (len=%d): %s", len(text), text[:300])
    return []


async def search_location(session: aiohttp.ClientSession,
                           api_key: str, keyword: str) -> list[dict[str, str]]:
    """Search location by keyword using Seoul bus API."""
    # URL-encode the keyword properly
    params = {"serviceKey": api_key, "stSrch": keyword}
    _LOGGER.debug("search_location: keyword=%s", keyword)

    try:
        async with session.get(LOC_URL, params=params,
                               timeout=aiohttp.ClientTimeout(total=15)) as r:
            text = await r.text()
            _LOGGER.debug("search_location: status=%s len=%d", r.status, len(text))
    except Exception as e:
        _LOGGER.error("search_location request error: %s", e)
        return []

    items = _extract_items_from_response(text)
    results = []
    for item in items:
        name = item.get("poiNm", "") or item.get("stationNm", "")
        gx = item.get("gpsX", "") or item.get("posX", "")
        gy = item.get("gpsY", "") or item.get("posY", "")
        if name and (gx or gy):
            results.append({"name": name, "gps_x": gx, "gps_y": gy})
    _LOGGER.debug("search_location: %d results", len(results))
    return results


async def search_path(session: aiohttp.ClientSession, api_key: str,
                       sx: str, sy: str, ex: str, ey: str) -> list[dict[str, Any]]:
    """Search transit path between two coordinates."""
    params = {"serviceKey": api_key, "startX": sx, "startY": sy,
              "endX": ex, "endY": ey}
    _LOGGER.debug("search_path: %s,%s -> %s,%s", sx, sy, ex, ey)

    try:
        async with session.get(PATH_URL, params=params,
                               timeout=aiohttp.ClientTimeout(total=15)) as r:
            text = await r.text()
            _LOGGER.debug("search_path: status=%s len=%d", r.status, len(text))
    except Exception as e:
        _LOGGER.error("search_path request error: %s", e)
        return []

    results = _extract_items_from_response(text)
    _LOGGER.debug("search_path: %d results", len(results))
    return results
