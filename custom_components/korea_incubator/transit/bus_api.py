"""Bus arrival API using KakaoMap (reliable, no API key needed)."""
from __future__ import annotations
import logging
import json
from typing import Any
import aiohttp

_LOGGER = logging.getLogger(__name__)

KAKAO_BUS_URL = "https://map.kakao.com/bus/stop.json?busstopid={}"


async def fetch_stop_data(session: aiohttp.ClientSession, stop_id: str) -> dict[str, Any]:
    """Fetch stop data from KakaoMap Bus."""
    url = KAKAO_BUS_URL.format(stop_id)
    headers = {"User-Agent": "Mozilla/5.0"}
    async with session.get(url, headers=headers,
                           timeout=aiohttp.ClientTimeout(total=10)) as r:
        r.raise_for_status()
        return json.loads(await r.text())


def build_bus_dict(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Convert KakaoMap payload into dict keyed by bus name."""
    lines = data.get("lines", [])
    return {line["name"]: line for line in lines if line.get("name")}


def build_bus_labels(data: dict[str, Any]) -> dict[str, str]:
    """Build selectable bus labels for config flow."""
    bus_dict = build_bus_dict(data)
    labels = {}
    for name, line in bus_dict.items():
        direction = line.get("arrival", {}).get("direction", "")
        labels[name] = f"{name} ({direction})" if direction else name
    return labels
