"""KMA Weather API - full attributes including dew point + apparent temp."""
from __future__ import annotations
import logging
import json
import math
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo
import aiohttp
from . import VILAGE_URL

_LOGGER = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")

SKY_MAP = {1: "sunny", 3: "partlycloudy", 4: "cloudy"}
SKY_CLOUD_PCT = {1: 10, 3: 70, 4: 95}
PTY_MAP_SHORT = {0: None, 1: "rainy", 2: "snowy", 3: "snowy", 4: "pouring"}

WIND_DIR_16 = ["N","NNE","NE","ENE","E","ESE","SE","SSE",
               "S","SSW","SW","WSW","W","WNW","NW","NNW","N"]

def _wind_direction_str(vec):
    if vec is None:
        return None
    idx = int((vec + 22.5 * 0.5) / 22.5)
    return WIND_DIR_16[min(idx, 16)]

def _base_time_vilage():
    now = datetime.now(KST)
    bases = [2, 5, 8, 11, 14, 17, 20, 23]
    hour = now.hour
    if now.minute < 10:
        hour -= 1
    base = max([b for b in bases if b <= hour], default=23)
    dt = now
    if base > hour:
        dt -= timedelta(days=1)
    return dt.strftime("%Y%m%d"), f"{base:02d}00"

def _float(v):
    if v is None or v == "" or v == "강수없음" or v == "적설없음":
        return None
    try:
        f = float(v)
        return None if abs(f) >= 900 else f
    except ValueError:
        return None

def _condition(sky, pty):
    return PTY_MAP_SHORT.get(pty) or SKY_MAP.get(sky, "cloudy")

def _dew_point(temp, humidity):
    """Approximate dew point using Magnus formula."""
    if temp is None or humidity is None or humidity <= 0:
        return None
    a, b = 17.27, 237.7
    alpha = (a * temp / (b + temp)) + math.log(humidity / 100.0)
    return round(b * alpha / (a - alpha), 1)

def _apparent_temp(temp, wind_speed, humidity):
    """Approximate apparent (feels-like) temperature.
    Uses wind chill for T<10°C, heat index for T>27°C, otherwise T itself."""
    if temp is None:
        return None
    ws = wind_speed if wind_speed else 0
    rh = humidity if humidity else 50

    if temp <= 10 and ws > 1.3:
        # Wind chill (Environment Canada formula, metric)
        wc = 13.12 + 0.6215 * temp - 11.37 * (ws * 3.6)**0.16 + 0.3965 * temp * (ws * 3.6)**0.16
        return round(wc, 1)
    elif temp >= 27:
        # Simplified heat index (Steadman)
        hi = -8.785 + 1.611*temp + 2.339*rh - 0.1461*temp*rh - 0.01231*temp**2 - 0.01642*rh**2 + 0.002212*temp**2*rh + 0.000725*temp*rh**2 - 0.000003582*temp**2*rh**2
        return round(hi, 1)
    return round(temp, 1)


async def fetch_vilage_forecast(session, api_key, nx, ny) -> list[dict]:
    base_date, base_time = _base_time_vilage()
    params = {"serviceKey": api_key, "numOfRows": "1000", "pageNo": "1",
              "dataType": "JSON", "base_date": base_date, "base_time": base_time,
              "nx": str(nx), "ny": str(ny)}
    async with session.get(VILAGE_URL, params=params,
                           timeout=aiohttp.ClientTimeout(total=20)) as r:
        text = await r.text()
        if r.status != 200:
            _LOGGER.error("KMA HTTP %s: %s", r.status, text[:200])
            return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        _LOGGER.error("KMA not JSON: %s", text[:200])
        return []
    rc = data.get("response", {}).get("header", {}).get("resultCode", "")
    if rc != "00":
        _LOGGER.warning("KMA error: %s", data.get("response",{}).get("header",{}).get("resultMsg",""))
        return []
    items = data.get("response", {}).get("body", {}).get("items", {}).get("item", [])
    return items if isinstance(items, list) else []


def parse_weather(items: list[dict]) -> dict[str, Any]:
    if not items:
        return {}

    by_time: dict[str, dict[str, str]] = defaultdict(dict)
    for item in items:
        key = f"{item.get('fcstDate','')}_{item.get('fcstTime','')}"
        by_time[key][item.get("category", "")] = item.get("fcstValue", "")

    times = sorted(by_time.keys())
    if not times:
        return {}

    cur = by_time[times[0]]
    sky = int(cur.get("SKY", "1") or "1")
    pty = int(cur.get("PTY", "0") or "0")
    vec = _float(cur.get("VEC"))
    temp = _float(cur.get("TMP") or cur.get("T1H"))
    humidity = _float(cur.get("REH"))
    wind_speed = _float(cur.get("WSD"))

    result = {
        "condition": _condition(sky, pty),
        "temperature": temp,
        "humidity": humidity,
        "wind_speed": wind_speed,
        "wind_bearing": vec,
        "wind_bearing_str": _wind_direction_str(vec),
        "precipitation": _float(cur.get("PCP") or cur.get("RN1")),
        "sky_code": sky,
        "cloud_coverage": SKY_CLOUD_PCT.get(sky),
        "dew_point": _dew_point(temp, humidity),
        "apparent_temperature": _apparent_temp(temp, wind_speed, humidity),
    }

    # Hourly forecasts
    hourly = []
    for t in times:
        fc = by_time[t]
        parts = t.split("_")
        if len(parts) != 2 or len(parts[0]) != 8 or len(parts[1]) < 4:
            continue
        d, tm = parts
        iso = f"{d[:4]}-{d[4:6]}-{d[6:8]}T{tm[:2]}:{tm[2:4]}:00+09:00"
        s = int(fc.get("SKY", "1") or "1")
        p = int(fc.get("PTY", "0") or "0")
        v = _float(fc.get("VEC"))
        t_val = _float(fc.get("TMP") or fc.get("T1H"))
        h_val = _float(fc.get("REH"))
        w_val = _float(fc.get("WSD"))
        hourly.append({
            "datetime": iso,
            "condition": _condition(s, p),
            "temperature": t_val,
            "precipitation_probability": _float(fc.get("POP")),
            "precipitation": _float(fc.get("PCP") or fc.get("RN1")),
            "humidity": h_val,
            "wind_speed": w_val,
            "wind_bearing": v,
            "cloud_coverage": SKY_CLOUD_PCT.get(s),
            "dew_point": _dew_point(t_val, h_val),
            "apparent_temperature": _apparent_temp(t_val, w_val, h_val),
        })

    # Daily forecasts
    by_date: dict[str, list[dict]] = defaultdict(list)
    for h in hourly:
        by_date[h["datetime"][:10]].append(h)

    daily = []
    for dt_str in sorted(by_date.keys()):
        entries = by_date[dt_str]
        temps = [e["temperature"] for e in entries if e["temperature"] is not None]
        pops = [e["precipitation_probability"] for e in entries if e["precipitation_probability"] is not None]
        humids = [e["humidity"] for e in entries if e["humidity"] is not None]
        winds = [e["wind_speed"] for e in entries if e["wind_speed"] is not None]

        tmn = tmx = None
        for tt in times:
            if tt.startswith(dt_str.replace("-", "")):
                raw = by_time[tt]
                v = _float(raw.get("TMN"))
                if v is not None: tmn = v
                v = _float(raw.get("TMX"))
                if v is not None: tmx = v

        conditions = [e["condition"] for e in entries if e["condition"]]
        day_cond = "cloudy"
        for p in ["pouring", "snowy", "rainy", "cloudy", "partlycloudy", "sunny"]:
            if p in conditions:
                day_cond = p
                break

        daily.append({
            "datetime": dt_str,
            "condition": day_cond,
            "temperature": round(sum(temps) / len(temps), 1) if temps else None,
            "templow": tmn if tmn is not None else (round(min(temps), 1) if temps else None),
            "temphigh": tmx if tmx is not None else (round(max(temps), 1) if temps else None),
            "precipitation_probability": round(max(pops)) if pops else None,
            "humidity": round(sum(humids) / len(humids)) if humids else None,
            "wind_speed": round(sum(winds) / len(winds), 1) if winds else None,
        })

    result["hourly_forecasts"] = hourly
    result["daily_forecasts"] = daily
    return result
