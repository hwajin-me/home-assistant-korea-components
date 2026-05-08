"""Weather warning sub-module."""
KMA_API_BASE = "http://apis.data.go.kr/1360000/WthrWrnInfoService/getPwnCd"
WARNING_SCAN_SEC = 900  # Renamed to avoid HA platform SCAN_INTERVAL conflict

WARNING_TYPES: dict[int, tuple[str, str, str]] = {
    1: ("wind", "강풍", "mdi:weather-windy"),
    2: ("rain", "호우", "mdi:weather-pouring"),
    3: ("cold", "한파", "mdi:snowflake-alert"),
    4: ("drought", "건조", "mdi:weather-sunny-alert"),
    5: ("storm_surge", "폭풍해일", "mdi:waves"),
    6: ("wind_wave", "풍랑", "mdi:sail-boat"),
    7: ("tsunami", "쓰나미", "mdi:tsunami"),
    8: ("heavy_snow", "대설", "mdi:weather-snowy-heavy"),
    9: ("yellow_dust", "황사", "mdi:blur"),
    12: ("heat", "폭염", "mdi:thermometer-alert"),
}

# Also define the list of all area codes
AREA_CODES = {
    "L1100100": "서울특별시", "L2600100": "부산광역시", "L2700100": "대구광역시",
    "L2800100": "인천광역시", "L2900100": "광주광역시", "L3000100": "대전광역시",
    "L3100100": "울산광역시", "L3600100": "세종특별자치시",
    "L4100100": "경기도", "L5100100": "강원도",
    "L4300100": "충청북도", "L4400100": "충청남도",
    "L4500100": "전라북도", "L4600100": "전라남도",
    "L4700100": "경상북도", "L4800100": "경상남도",
    "L5000100": "제주특별자치도",
}

# Event type constants for weather warnings
EVENT_TYPE_NONE = "none"
EVENT_TYPE_ADVISORY = "advisory"
EVENT_TYPE_WARNING = "warning"
EVENT_TYPE_PRE_ADVISORY = "pre_advisory"
EVENT_TYPE_PRE_WARNING = "pre_warning"
EVENT_TYPE_CANCELLED = "cancelled"
EVENT_TYPES = [EVENT_TYPE_ADVISORY, EVENT_TYPE_WARNING, EVENT_TYPE_PRE_ADVISORY,
               EVENT_TYPE_PRE_WARNING, EVENT_TYPE_CANCELLED, EVENT_TYPE_NONE]

# Korean labels for event types (used in calendar)
EVENT_TYPE_KO = {
    "advisory": "주의보",
    "warning": "경보",
    "pre_advisory": "예비 주의보",
    "pre_warning": "예비 경보",
    "cancelled": "해제",
    "none": "없음",
}

# ===== Weather Platform handler (for KMA Weather Forecast) =====
async def async_setup_entry(hass, entry, async_add_entities):
    """Set up weather platform entities for KMA Weather Forecast."""
    from ..const import DOMAIN, CONF_ENTRY_TYPE, ENTRY_KMA_WEATHER
    if entry.data.get(CONF_ENTRY_TYPE) != ENTRY_KMA_WEATHER:
        return
    store = hass.data[DOMAIN][entry.entry_id]
    from ..kma_weather.weather import KMAWeather
    c = store["coordinator"]
    async_add_entities([KMAWeather(c, r["name"]) for r in store.get("regions", [])])
