"""Pharmacy API client."""
from __future__ import annotations
import logging
import xml.etree.ElementTree as ET
from typing import Any
import aiohttp
from . import PHARMACY_URL

_LOGGER = logging.getLogger(__name__)

async def fetch_pharmacies(session, api_key, q0, q1="", page=1, num=20):
    """Search pharmacies by region. q0=시도, q1=시군구."""
    params = {"serviceKey": api_key, "Q0": q0, "Q1": q1,
              "ORD": "NAME", "pageNo": str(page), "numOfRows": str(num)}
    async with session.get(PHARMACY_URL, params=params,
                           timeout=aiohttp.ClientTimeout(total=15)) as r:
        text = await r.text()
    root = ET.fromstring(text)
    results = []
    for item in root.findall(".//item"):
        duty_time = {}
        for day_n in range(1, 9):  # dutyTime1~8 (월~일+공휴일)
            s = item.findtext(f"dutyTime{day_n}s", "")
            c = item.findtext(f"dutyTime{day_n}c", "")
            if s or c:
                day_names = {1:"월",2:"화",3:"수",4:"목",5:"금",6:"토",7:"일",8:"공휴일"}
                duty_time[day_names.get(day_n, str(day_n))] = f"{s}~{c}"
        results.append({
            "name": item.findtext("dutyName", ""),
            "address": item.findtext("dutyAddr", ""),
            "phone": item.findtext("dutyTel1", ""),
            "lat": item.findtext("wgs84Lat", ""),
            "lon": item.findtext("wgs84Lon", ""),
            "duty_time": duty_time,
        })
    return results

async def validate_pharmacy_api(api_key):
    try:
        async with aiohttp.ClientSession() as s:
            r = await fetch_pharmacies(s, api_key, "서울특별시", num=1)
            return len(r) > 0
    except Exception:
        return False
