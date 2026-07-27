"""Seoul subway bulk arrival API client."""
from __future__ import annotations
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
import aiohttp
from . import SUBWAY_BULK_URL, SUBWAY_LINES

_LOGGER = logging.getLogger(__name__)
KST = timezone(timedelta(hours=9))


async def validate_seoul_api(api_key: str) -> bool:
    url = SUBWAY_BULK_URL.format(key=api_key, station="서울")
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status != 200:
                    return False
                d = await r.json(content_type=None)
                if "realtimeArrivalList" in d:
                    return True
                err = d.get("errorMessage", {})
                return err.get("code") in ("INFO-200", "INFO-000")
    except Exception:
        return False


async def fetch_bulk_arrivals(session: aiohttp.ClientSession, api_key: str,
                               station: str) -> list[dict[str, Any]]:
    """Fetch all arrivals for a station using bulk API."""
    url = SUBWAY_BULK_URL.format(key=api_key, station=station)
    async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
        if r.status != 200:
            return []
        data = await r.json(content_type=None)

    # 데이터가 있으면 바로 반환
    if "realtimeArrivalList" in data:
        return data["realtimeArrivalList"]

    # 데이터 없이 errorMessage만 있는 경우
    if "errorMessage" in data:
        code = data["errorMessage"].get("code", "")
        # INFO-200: 데이터 없음 (운행 종료 등), INFO-000: 정상 처리 (데이터 0건)
        if code in ("INFO-200", "INFO-000"):
            return []
        msg = data["errorMessage"].get("message", "Unknown error")
        raise Exception(f"Subway API error {code}: {msg}")

    return []


def filter_arrivals(arrivals: list[dict], direction: str,
                    line_id: str | None = None) -> list[dict[str, Any]]:
    """Filter and parse arrivals for a specific direction/line."""
    filtered = [a for a in arrivals if a.get("updnLine") == direction]
    if line_id:
        filtered = [a for a in filtered if a.get("subwayId") == line_id]
    filtered.sort(key=lambda a: a.get("ordkey", ""))

    results = []
    for item in filtered[:2]:
        barvl = int(item.get("barvlDt", 0) or 0)
        recptn = item.get("recptnDt", "")
        arrival_dt = None
        if recptn:
            try:
                rdt = datetime.strptime(recptn, "%Y-%m-%d %H:%M:%S").replace(tzinfo=KST)
                arrival_dt = rdt + timedelta(seconds=max(barvl, 0))
            except (ValueError, TypeError):
                pass
        sid = item.get("subwayId", "")
        results.append({
            "arrival_time": arrival_dt,
            "destination": item.get("bstatnNm", ""),
            "arrival_message": item.get("arvlMsg2", ""),
            "train_type": item.get("btrainSttus", ""),
            "barvl_dt": barvl,
            "line_name": SUBWAY_LINES.get(sid, sid),
            "subway_id": sid,
            "train_no": item.get("btrainNo", ""),
        })
    return results
