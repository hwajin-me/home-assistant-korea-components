"""AirKorea sensors + binary_sensor + event + calendar."""
from __future__ import annotations
from datetime import datetime, date, timedelta
from typing import Any
from zoneinfo import ZoneInfo
from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
from homeassistant.components.event import EventEntity
from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.core import callback
from ..const import DOMAIN

KST = ZoneInfo("Asia/Seoul")

def air_device(station_name):
    return DeviceInfo(identifiers={(DOMAIN, f"air_{station_name}")},
                      name=f"에어코리아 - {station_name}",
                      manufacturer="한국환경공단", model="에어코리아",
                      entry_type=DeviceEntryType.SERVICE)

POLLUTANTS = [
    ("pm10Value", "PM10 미세먼지", "㎍/㎥"),
    ("pm25Value", "PM2.5 초미세먼지", "㎍/㎥"),
    ("so2Value", "SO₂ 아황산가스", "ppm"),
    ("coValue", "CO 일산화탄소", "ppm"),
    ("o3Value", "O₃ 오존", "ppm"),
    ("no2Value", "NO₂ 이산화질소", "ppm"),
    ("khaiValue", "통합대기질지수", None),
]
# 참고: CO(일산화탄소)는 CO₂(이산화탄소)와 다릅니다.
# CO 0.3~0.5ppm, SO₂ 0.001~0.02ppm, O₃ 0.02~0.05ppm, NO₂ 0.01~0.04ppm이 정상 범위입니다.

# Grade mapping
GRADE_MAP = {"1": "좋음", "2": "보통", "3": "나쁨", "4": "매우나쁨"}


def _parse_forecast_alerts(forecasts: list[dict], sido_filter: str = "") -> list[dict]:
    """Parse forecast items, optionally filtered by sido region."""
    alerts = []
    for fc in forecasts:
        inform_data = fc.get("informData", "")
        inform_cause = fc.get("informCause", "")
        inform_grade = fc.get("informGrade", "")
        inform_code = fc.get("informCode", "")
        if not inform_grade:
            continue
        pairs = [p.strip() for p in inform_grade.split(",")]
        for pair in pairs:
            if " : " not in pair:
                continue
            region, grade = pair.split(" : ", 1)
            region = region.strip()
            grade = grade.strip()
            # Filter by sido if specified
            if sido_filter and sido_filter not in region:
                continue
            if grade in ("나쁨", "매우나쁨", "매우 나쁨"):
                alerts.append({
                    "pollutant": inform_code,
                    "region": region,
                    "grade": grade,
                    "date": inform_data,
                    "cause": inform_cause,
                })
    return alerts


class AirQualitySensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT
    def __init__(self, coordinator, station_name, field, name, unit):
        super().__init__(coordinator)
        self._station = station_name
        self._field = field
        self._attr_unique_id = f"{DOMAIN}_air_{station_name}_{field}"
        self._attr_name = name
        self._attr_native_unit_of_measurement = unit
        self._attr_icon = "mdi:air-filter"
        self._attr_device_info = air_device(station_name)
    @property
    def native_value(self):
        data = (self.coordinator.data or {}).get("stations", {}).get(self._station, {})
        val = data.get(self._field, "")
        if val == "-" or val == "":
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None
    @property
    def extra_state_attributes(self):
        data = (self.coordinator.data or {}).get("stations", {}).get(self._station, {})
        grade_field = self._field.replace("Value", "Grade")
        grade = data.get(grade_field, "")
        attrs = {}
        if grade:
            attrs["grade"] = GRADE_MAP.get(str(grade), str(grade))
        attrs["data_time"] = data.get("dataTime", "")
        return attrs


class AirAlertBinarySensor(CoordinatorEntity, BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.SAFETY
    _attr_icon = "mdi:alert-decagram"
    def __init__(self, coordinator, station_name, sido=""):
        super().__init__(coordinator)
        self._station = station_name
        self._sido = sido
        self._attr_unique_id = f"{DOMAIN}_air_alert_{station_name}"
        self._attr_name = "대기질 경보"
        self._attr_device_info = air_device(station_name)
    @property
    def is_on(self):
        alerts = _parse_forecast_alerts(
            (self.coordinator.data or {}).get("forecast", []), self._sido)
        return len(alerts) > 0
    @property
    def extra_state_attributes(self):
        alerts = _parse_forecast_alerts(
            (self.coordinator.data or {}).get("forecast", []), self._sido)
        if not alerts:
            return {"active_alerts": [], "alert_count": 0}
        return {
            "active_alerts": alerts[:10],
            "alert_count": len(alerts),
        }


class AirAlertEvent(CoordinatorEntity, EventEntity):
    _attr_has_entity_name = True
    _attr_event_types = ["air_quality_alert"]
    _attr_icon = "mdi:smog"
    def __init__(self, coordinator, station_name, sido=""):
        super().__init__(coordinator)
        self._station = station_name
        self._sido = sido
        self._attr_unique_id = f"{DOMAIN}_air_event_{station_name}"
        self._attr_name = "대기질 경보 이벤트"
        self._attr_device_info = air_device(station_name)
        self._last_hash = None
    @callback
    def _handle_coordinator_update(self):
        alerts = _parse_forecast_alerts(
            (self.coordinator.data or {}).get("forecast", []), self._sido)
        cur_hash = str([(a["pollutant"], a["region"], a["grade"]) for a in alerts[:5]])
        if self._last_hash is not None and cur_hash != self._last_hash and alerts:
            self._trigger_event("air_quality_alert", {
                "alerts": alerts[:5],
                "count": len(alerts),
            })
        self._last_hash = cur_hash
        self.async_write_ha_state()


class AirForecastCalendar(CoordinatorEntity, CalendarEntity):
    """Calendar showing air quality forecast alerts filtered by region."""
    _attr_has_entity_name = True
    _attr_icon = "mdi:calendar-alert"

    def __init__(self, coordinator, station_name, sido=""):
        super().__init__(coordinator)
        self._station = station_name
        self._sido = sido
        self._attr_unique_id = f"{DOMAIN}_air_cal_{station_name}"
        self._attr_name = "대기질 예보"
        self._attr_device_info = air_device(station_name)

    @property
    def event(self) -> CalendarEvent | None:
        alerts = _parse_forecast_alerts(
            (self.coordinator.data or {}).get("forecast", []), self._sido)
        if not alerts:
            return None
        a = alerts[0]
        today = date.today()
        return CalendarEvent(
            start=today,
            end=today + timedelta(days=1),
            summary=f"[{a['pollutant']}] {a['region']}: {a['grade']}",
            description=a.get("cause", ""),
        )

    async def async_get_events(self, hass, start_date, end_date) -> list[CalendarEvent]:
        forecasts = (self.coordinator.data or {}).get("forecast", [])
        events = []
        for fc in forecasts:
            inform_data = fc.get("informData", "")
            inform_grade = fc.get("informGrade", "")
            inform_code = fc.get("informCode", "")
            inform_cause = fc.get("informCause", "")
            if not inform_data or not inform_grade:
                continue
            try:
                dt = datetime.strptime(inform_data, "%Y-%m-%d").date()
            except ValueError:
                continue
            if dt < start_date.date() or dt > end_date.date():
                continue
            # Parse all regions with bad grades
            pairs = [p.strip() for p in inform_grade.split(",")]
            bad_regions = []
            for pair in pairs:
                if " : " not in pair:
                    continue
                region, grade = pair.split(" : ", 1)
                region = region.strip()
                grade = grade.strip()
                if self._sido and self._sido not in region:
                    continue
                if grade in ("나쁨", "매우나쁨", "매우 나쁨"):
                    bad_regions.append(f"{region}({grade})")
            if bad_regions:
                events.append(CalendarEvent(
                    start=dt,
                    end=dt + timedelta(days=1),
                    summary=f"[{inform_code}] {', '.join(bad_regions)}",
                    description=inform_cause,
                ))
        return events


# ===== Living Weather Index Sensors =====

def _uv_grade(val):
    if val is None: return None
    from . import UV_GRADES
    for threshold, label in UV_GRADES:
        if val < threshold: return label
    return "위험"

def _stag_grade(val):
    if val is None: return None
    from . import STAG_GRADES
    for threshold, label in STAG_GRADES:
        if val <= threshold: return label
    return "매우높음"

def _get_current_index_value(data: dict) -> int | None:
    """Get current value from living index API response.
    The API returns h0~h24 (or h3,h6,...h78) fields for 3-hour forecasts."""
    if not data:
        return None
    now = datetime.now(KST)
    h = (now.hour // 3) * 3
    # Try multiple field name patterns
    for field in [f"h{h}", f"h{h:02d}", "h0", "today"]:
        val = data.get(field)
        if val is not None and str(val).strip() and str(val).strip() != "0":
            try:
                return int(val)
            except (ValueError, TypeError):
                continue
    # Try any h* field that has a value
    for key in sorted(data.keys()):
        if key.startswith("h") and key[1:].isdigit():
            val = data.get(key)
            if val is not None and str(val).strip():
                try:
                    return int(val)
                except (ValueError, TypeError):
                    continue
    return None


def _get_all_hourly_values(data: dict) -> dict:
    """Extract all hourly forecast values from the response."""
    attrs = {}
    for key in sorted(data.keys()):
        if key.startswith("h") and key[1:].isdigit():
            val = data.get(key)
            if val is not None and str(val).strip():
                hour = int(key[1:])
                attrs[f"+{hour}h"] = val
        elif key == "date":
            attrs["date"] = data[key]
    return attrs


class UVIndexSensor(CoordinatorEntity, SensorEntity):
    """UV Index sensor."""
    _attr_has_entity_name = True
    _attr_icon = "mdi:sun-wireless"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, station_name):
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_air_uv_{station_name}"
        self._attr_name = "자외선지수"
        self._attr_device_info = air_device(station_name)

    @property
    def native_value(self):
        uv = (self.coordinator.data or {}).get("uv", {})
        return _get_current_index_value(uv)

    @property
    def extra_state_attributes(self):
        uv = (self.coordinator.data or {}).get("uv", {})
        val = self.native_value
        attrs = {"grade": _uv_grade(val)}
        attrs.update(_get_all_hourly_values(uv))
        return attrs


class AirStagnationSensor(CoordinatorEntity, SensorEntity):
    """Air Stagnation Index sensor."""
    _attr_has_entity_name = True
    _attr_icon = "mdi:weather-hazy"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, station_name):
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_air_stag_{station_name}"
        self._attr_name = "대기정체지수"
        self._attr_device_info = air_device(station_name)

    @property
    def native_value(self):
        stag = (self.coordinator.data or {}).get("stagnation", {})
        return _get_current_index_value(stag)

    @property
    def extra_state_attributes(self):
        stag = (self.coordinator.data or {}).get("stagnation", {})
        val = self.native_value
        attrs = {"grade": _stag_grade(val)}
        attrs.update(_get_all_hourly_values(stag))
        return attrs
