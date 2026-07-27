"""AirKorea API client - V4 for living index."""
from __future__ import annotations
import logging
import json
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo
import aiohttp
from . import STATION_URL, REALTIME_URL, FORECAST_URL

_LOGGER = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")


async def search_stations(session, api_key, addr="") -> list[dict]:
    params = {"serviceKey": api_key, "returnType": "json",
              "numOfRows": "100", "pageNo": "1"}
    if addr:
        params["addr"] = addr
    async with session.get(STATION_URL, params=params,
                           timeout=aiohttp.ClientTimeout(total=15)) as r:
        text = await r.text()
        if r.status != 200:
            return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    body = data.get("response", {}).get("body", {})
    items = body.get("items", [])
    if isinstance(items, dict):
        items = [items]
    return [{"stationName": i.get("stationName", ""), "addr": i.get("addr", "")}
            for i in items if i.get("stationName")]


async def fetch_realtime(session, api_key, station_name) -> dict[str, Any]:
    params = {"serviceKey": api_key, "returnType": "json", "numOfRows": "1",
              "pageNo": "1", "stationName": station_name, "dataTerm": "DAILY",
              "ver": "1.5"}
    async with session.get(REALTIME_URL, params=params,
                           timeout=aiohttp.ClientTimeout(total=15)) as r:
        text = await r.text()
        if r.status != 200:
            return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {}
    header = data.get("response", {}).get("header", {})
    if header.get("resultCode") != "00":
        return {}
    items = data.get("response", {}).get("body", {}).get("items", [])
    if isinstance(items, dict):
        items = [items]
    return items[0] if items else {}


async def fetch_forecast(session, api_key) -> list[dict]:
    params = {"serviceKey": api_key, "returnType": "json", "numOfRows": "10",
              "pageNo": "1", "searchDate": datetime.now(KST).strftime("%Y-%m-%d")}
    async with session.get(FORECAST_URL, params=params,
                           timeout=aiohttp.ClientTimeout(total=15)) as r:
        text = await r.text()
        if r.status != 200:
            return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    items = data.get("response", {}).get("body", {}).get("items", [])
    if isinstance(items, dict):
        items = [items]
    return items


async def _fetch_living_v4(session, api_key, url, area_no) -> dict[str, Any]:
    """Fetch V4 living index. time = YYYYMMDDHH, issued at 06/18 KST."""
    now = datetime.now(KST)
    # Try current issue time, then previous
    base_h = 18 if now.hour >= 18 else 6
    attempts = [
        now.strftime("%Y%m%d") + f"{base_h:02d}",
    ]
    if base_h == 6:
        attempts.append((now - timedelta(days=1)).strftime("%Y%m%d") + "18")
    else:
        attempts.append(now.strftime("%Y%m%d") + "06")

    for time_str in attempts:
        params = {"serviceKey": api_key, "dataType": "JSON",
                  "areaNo": area_no, "time": time_str,
                  "numOfRows": "10", "pageNo": "1"}
        try:
            async with session.get(url, params=params,
                                   timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status != 200:
                    _LOGGER.debug("Living V4 HTTP %s for time=%s", r.status, time_str)
                    continue
                text = await r.text()
            data = json.loads(text)
            header = data.get("response", {}).get("header", {})
            rc = header.get("resultCode", "")
            if rc == "00":
                items = data.get("response", {}).get("body", {}).get("items", {})
                if isinstance(items, dict):
                    items = items.get("item", [])
                if isinstance(items, dict):
                    items = [items]
                if isinstance(items, list) and items:
                    _LOGGER.debug("Living V4 OK: time=%s keys=%s", time_str,
                                  [k for k in items[0] if items[0].get(k)])
                    return items[0]
            else:
                _LOGGER.debug("Living V4 error: time=%s code=%s msg=%s",
                              time_str, rc, header.get("resultMsg", ""))
        except Exception as e:
            _LOGGER.debug("Living V4 exception: %s", e)
    return {}


async def fetch_uv_index(session, api_key, area_code) -> dict[str, Any]:
    from . import UV_IDX_URL
    return await _fetch_living_v4(session, api_key, UV_IDX_URL, area_code)


async def fetch_air_stagnation(session, api_key, area_code) -> dict[str, Any]:
    from . import AIR_STAG_URL
    return await _fetch_living_v4(session, api_key, AIR_STAG_URL, area_code)
