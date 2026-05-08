"""NEIS Open API Client."""
from __future__ import annotations
import logging, xml.etree.ElementTree as ET
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo
from aiohttp import ClientSession
from . import NEIS_BASE, ENDPOINTS

_LOGGER = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")

def _ay() -> int:
    now = datetime.now(KST)
    return now.year - 1 if now.month < 2 or (now.month == 2 and now.day < 15) else now.year

class NeisApiClient:
    def __init__(self, session: ClientSession, api_key: str):
        self.session = session
        self.api_key = api_key

    async def _req(self, ep: str, params: dict | None = None) -> dict[str, Any]:
        p = {"KEY": self.api_key, "Type": "xml", "pIndex": 1, "pSize": 1000, **(params or {})}
        async with self.session.get(f"{NEIS_BASE}/{ep}", params=p) as r:
            text = await r.text()
        root = ET.fromstring(text)
        res = root.find(".//RESULT")
        if res is not None:
            code = res.findtext("CODE", "")
            if code != "INFO-000":
                raise Exception(f"NEIS {code}: {res.findtext('MESSAGE','')}")
        rows = []
        for row in root.findall(".//row"):
            rows.append({c.tag: c.text for c in row})
        return {"row": rows}

    async def search_school(self, name: str):
        return (await self._req(ENDPOINTS["school_info"], {"SCHUL_NM": name})).get("row", [])

    async def get_school_info(self, rc: str, sc: str):
        rows = (await self._req(ENDPOINTS["school_info"],
                {"ATPT_OFCDC_SC_CODE": rc, "SD_SCHUL_CODE": sc})).get("row", [])
        return rows[0] if rows else None

    async def get_meal(self, rc, sc, s: date, e: date):
        return (await self._req(ENDPOINTS["meal"], {
            "ATPT_OFCDC_SC_CODE": rc, "SD_SCHUL_CODE": sc,
            "MLSV_FROM_YMD": s.strftime("%Y%m%d"), "MLSV_TO_YMD": e.strftime("%Y%m%d")
        })).get("row", [])

    async def get_schedule_month(self, rc, sc, y, m):
        return (await self._req(ENDPOINTS["calendar"], {
            "ATPT_OFCDC_SC_CODE": rc, "SD_SCHUL_CODE": sc,
            "AA_YMD": f"{y:04d}{m:02d}"
        })).get("row", [])

    async def get_timetable(self, rc, sc, level, grade, cls, s: date, e: date):
        ep = ENDPOINTS["timetable"][level]
        p = {"ATPT_OFCDC_SC_CODE": rc, "SD_SCHUL_CODE": sc, "GRADE": str(grade),
             "TI_FROM_YMD": s.strftime("%Y%m%d"), "TI_TO_YMD": e.strftime("%Y%m%d"),
             "AY": str(_ay())}
        p["CLRM_NM" if level == "high" else "CLASS_NM"] = str(cls)
        return (await self._req(ep, p)).get("row", [])

    async def get_classroom_info(self, rc, sc, grade):
        return (await self._req(ENDPOINTS["classroom_info"], {
            "ATPT_OFCDC_SC_CODE": rc, "SD_SCHUL_CODE": sc,
            "GRADE": str(grade), "AY": str(_ay())
        })).get("row", [])
