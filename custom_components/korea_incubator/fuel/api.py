"""Opinet fuel price API client."""
from __future__ import annotations
import logging
import xml.etree.ElementTree as ET
from typing import Any
import aiohttp
from . import OPINET_AVG_URL, OPINET_LOWPRICE_URL

_LOGGER = logging.getLogger(__name__)

async def validate_opinet(api_key: str) -> bool:
    params = {"code": api_key, "out": "xml"}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(OPINET_AVG_URL, params=params,
                             timeout=aiohttp.ClientTimeout(total=15)) as r:
                return r.status == 200
    except Exception:
        return False

async def fetch_avg_price(session: aiohttp.ClientSession,
                           api_key: str) -> list[dict[str, str]]:
    params = {"code": api_key, "out": "xml"}
    async with session.get(OPINET_AVG_URL, params=params,
                           timeout=aiohttp.ClientTimeout(total=15)) as r:
        text = await r.text()
    root = ET.fromstring(text)
    results = []
    for oil in root.findall(".//OIL"):
        results.append({
            "product_code": oil.findtext("PRODCD", ""),
            "price": oil.findtext("PRICE", ""),
            "diff": oil.findtext("DIFF", ""),
        })
    return results

async def fetch_low_price(session: aiohttp.ClientSession, api_key: str,
                           sido_code: str, fuel_code: str) -> list[dict[str, Any]]:
    params = {"code": api_key, "out": "xml", "sido": sido_code, "prodcd": fuel_code, "cnt": "5"}
    async with session.get(OPINET_LOWPRICE_URL, params=params,
                           timeout=aiohttp.ClientTimeout(total=15)) as r:
        text = await r.text()
    root = ET.fromstring(text)
    results = []
    for oil in root.findall(".//OIL"):
        results.append({
            "station_name": oil.findtext("OS_NM", ""),
            "price": oil.findtext("PRICE", ""),
            "address": oil.findtext("NEW_ADR", "") or oil.findtext("VAN_ADR", ""),
            "brand": oil.findtext("POLL_DIV_CD", ""),
        })
    return results
