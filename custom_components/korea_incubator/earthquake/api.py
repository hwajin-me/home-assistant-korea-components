"""Earthquake API - uses params= dict."""
from __future__ import annotations
import logging
import json
import math
import xml.etree.ElementTree as ET
from typing import Any
import aiohttp
from . import EQ_URL

_LOGGER = logging.getLogger(__name__)


async def fetch_earthquakes(session, api_key, count=20) -> list[dict]:
    from datetime import datetime, timedelta
    end = datetime.now()
    start = end - timedelta(days=30)
    params = {"serviceKey": api_key, "numOfRows": str(count), "pageNo": "1",
              "dataType": "JSON",
              "fromTmFc": start.strftime("%Y%m%d"),
              "toTmFc": end.strftime("%Y%m%d")}
    async with session.get(EQ_URL, params=params,
                           timeout=aiohttp.ClientTimeout(total=15)) as r:
        text = await r.text()
    try:
        data = json.loads(text)
        total = data.get("response", {}).get("body", {}).get("totalCount", 0)
        if total == 0:
            return []
        items = data.get("response", {}).get("body", {}).get("items", {})
        if isinstance(items, dict):
            items = items.get("item", [])
        if isinstance(items, dict):
            items = [items]
        return [_parse(i) for i in items]
    except (json.JSONDecodeError, AttributeError):
        pass
    try:
        root = ET.fromstring(text)
        return [_parse_xml(i) for i in root.findall(".//item")]
    except ET.ParseError:
        pass
    return []


def _parse(i):
    return {"latitude": _f(i.get("lat")), "longitude": _f(i.get("lon")),
            "magnitude": _f(i.get("mt")), "location": i.get("loc", ""),
            "datetime": i.get("tmEqk", ""), "depth": i.get("dep", "")}


def _parse_xml(item):
    return {"latitude": _f(item.findtext("lat")), "longitude": _f(item.findtext("lon")),
            "magnitude": _f(item.findtext("mt")), "location": item.findtext("loc", ""),
            "datetime": item.findtext("tmEqk", ""), "depth": item.findtext("dep", "")}


def _f(v):
    try:
        return float(v) if v else None
    except (ValueError, TypeError):
        return None


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians((lat2 or 0) - (lat1 or 0))
    dlon = math.radians((lon2 or 0) - (lon1 or 0))
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1 or 0)) * math.cos(math.radians(lat2 or 0)) *
         math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
