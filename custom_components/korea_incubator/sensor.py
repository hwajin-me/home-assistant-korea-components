from __future__ import annotations

from typing import Dict, Any, Optional, Union
from datetime import datetime
import re

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .arisu.device import ArisuDevice
from .const import DOMAIN, ENERGY_KILO_WATT_HOUR, CURRENCY_KRW
from .gasapp.device import GasAppDevice
from .goodsflow.device import GoodsFlowDevice
from .kakaomap.device import KakaoMapDevice
from .kepco.device import KepcoDevice
from .safety_alert.device import SafetyAlertDevice

# Device type union for type hints
DeviceType = Union[
    KepcoDevice,
    GasAppDevice,
    SafetyAlertDevice,
    GoodsFlowDevice,
    ArisuDevice,
    KakaoMapDevice
]


def get_value_from_path(data: Dict[str, Any], path: str) -> Any:
    """Get a value from a nested dictionary using a dot-separated path.

    Supports array indexing with square brackets, similar to jq:
    - "items.0" or "items[0]" for first element
    - "items[-1]" for last element
    - "data.history[2].value" for nested array access
    - "data.history[-2].value" for second to last element
    """
    keys = path.split('.')
    value = data

    for key in keys:
        if value is None:
            return None

        # Handle array indexing with square brackets: items[0] or items[-1]
        if '[' in key and key.endswith(']'):
            array_key, index_part = key.split('[', 1)
            index_str = index_part.rstrip(']')

            try:
                index = int(index_str)
            except ValueError:
                return None

            # Get the array first
            if isinstance(value, dict):
                value = value.get(array_key)
            else:
                return None

            # Then access the index (supports negative indexing)
            if isinstance(value, (list, tuple)):
                try:
                    value = value[index]
                except IndexError:
                    return None
            else:
                return None

        # Handle numeric string as array index: items.0 or items.-1
        elif key.lstrip('-').isdigit():
            index = int(key)
            if isinstance(value, (list, tuple)):
                try:
                    value = value[index]
                except IndexError:
                    return None
            else:
                return None

        # Handle regular dictionary key access
        else:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return None

    return value


def parse_date_value(raw_value: str, current_year: int = None) -> Optional[datetime]:
    """Parse various date formats into datetime object with timezone information.

    Supported formats:
    - 2025-01-01
    - 20250101
    - 2025/01/01
    - 2025.01.01
    - 2025-01, 2025.01, 202501 (month only, defaults to 1st day)
    - 08/01 10 (assumes current year and hour, minute as 00)
    - 2025년 1월 11일 (Korean date format)
    - 2025년 1월 (Korean year-month format, defaults to 1st day)
    - 01/11/2025 (US format MM/DD/YYYY)
    - 1/11/2025 (US format M/D/YYYY)
    """
    if not isinstance(raw_value, str):
        return None

    if current_year is None:
        current_year = datetime.now().year

    # Remove extra whitespace
    value = raw_value.strip()

    parsed_dt = None

    # Pattern 1: YYYY-MM-DD
    pattern1 = re.match(r'^(\d{4})-(\d{1,2})-(\d{1,2})$', value)
    if pattern1:
        try:
            year, month, day = map(int, pattern1.groups())
            parsed_dt = datetime(year, month, day)
        except ValueError:
            return None

    # Pattern 2: YYYYMMDD
    if not parsed_dt:
        pattern2 = re.match(r'^(\d{4})(\d{2})(\d{2})$', value)
        if pattern2:
            try:
                year = int(pattern2.group(1))
                month = int(pattern2.group(2))
                day = int(pattern2.group(3))
                parsed_dt = datetime(year, month, day)
            except ValueError:
                return None

    # Pattern 3: YYYY/MM/DD
    if not parsed_dt:
        pattern3 = re.match(r'^(\d{4})/(\d{1,2})/(\d{1,2})$', value)
        if pattern3:
            try:
                year, month, day = map(int, pattern3.groups())
                parsed_dt = datetime(year, month, day)
            except ValueError:
                return None

    # Pattern 4: YYYY.MM.DD (dot separator)
    if not parsed_dt:
        pattern4 = re.match(r'^(\d{4})\.(\d{1,2})\.(\d{1,2})$', value)
        if pattern4:
            try:
                year, month, day = map(int, pattern4.groups())
                parsed_dt = datetime(year, month, day)
            except ValueError:
                return None

    # Pattern 5: YYYY-MM (year-month with dash, defaults to 1st day)
    if not parsed_dt:
        pattern5 = re.match(r'^(\d{4})-(\d{1,2})$', value)
        if pattern5:
            try:
                year, month = map(int, pattern5.groups())
                parsed_dt = datetime(year, month, 1)
            except ValueError:
                return None

    # Pattern 6: YYYY.MM (year-month with dot, defaults to 1st day)
    if not parsed_dt:
        pattern6 = re.match(r'^(\d{4})\.(\d{1,2})$', value)
        if pattern6:
            try:
                year, month = map(int, pattern6.groups())
                parsed_dt = datetime(year, month, 1)
            except ValueError:
                return None

    # Pattern 7: YYYYMM (year-month without separator, defaults to 1st day)
    if not parsed_dt:
        pattern7 = re.match(r'^(\d{4})(\d{2})$', value)
        if pattern7:
            try:
                year = int(pattern7.group(1))
                month = int(pattern7.group(2))
                parsed_dt = datetime(year, month, 1)
            except ValueError:
                return None

    # Pattern 8: MM/DD HH (e.g., "08/01 10" -> 2025-08-01 10:00:00)
    if not parsed_dt:
        pattern8 = re.match(r'^(\d{1,2})/(\d{1,2})\s+(\d{1,2})$', value)
        if pattern8:
            try:
                month, day, hour = map(int, pattern8.groups())
                parsed_dt = datetime(current_year, month, day, hour, 0, 0)
            except ValueError:
                return None

    # Pattern 9: Korean date format (e.g., "2025년 1월 11일")
    if not parsed_dt:
        pattern9 = re.match(r'^(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일$', value)
        if pattern9:
            try:
                year, month, day = map(int, pattern9.groups())
                parsed_dt = datetime(year, month, day)
            except ValueError:
                return None

    # Pattern 10: Korean year-month format (e.g., "2025년 1월", defaults to 1st day)
    if not parsed_dt:
        pattern10 = re.match(r'^(\d{4})년\s*(\d{1,2})월$', value)
        if pattern10:
            try:
                year, month = map(int, pattern10.groups())
                parsed_dt = datetime(year, month, 1)
            except ValueError:
                return None

    # Pattern 11: US date format MM/DD/YYYY (e.g., "01/11/2025" or "1/11/2025")
    if not parsed_dt:
        pattern11 = re.match(r'^(\d{1,2})/(\d{1,2})/(\d{4})$', value)
        if pattern11:
            try:
                month, day, year = map(int, pattern11.groups())
                parsed_dt = datetime(year, month, day)
            except ValueError:
                return None

    # Pattern 12: US date format with dots MM.DD.YYYY
    if not parsed_dt:
        pattern12 = re.match(r'^(\d{1,2})\.(\d{1,2})\.(\d{4})$', value)
        if pattern12:
            try:
                month, day, year = map(int, pattern12.groups())
                parsed_dt = datetime(year, month, day)
            except ValueError:
                return None

    # Add timezone information using Home Assistant's default timezone
    if parsed_dt:
        return dt_util.as_local(parsed_dt)

    return None


async def async_setup_entry(
        hass: HomeAssistant,
        entry: ConfigEntry,
        async_add_entities
) -> None:
    """Set up Korea sensors from a config entry."""
    data: Dict[str, Any] = hass.data[DOMAIN][entry.entry_id]
    coordinator: DataUpdateCoordinator = data["coordinator"]
    device: DeviceType = data["device"]
    service: str = entry.data.get("service")

    if service == "kepco":
        entities = [
            KoreaSensor(
                coordinator,
                device,
                "usage_info",
                "SESS_CUSTNO",
                "고객번호",
                None,
                None,
                None,
            ),
            KoreaSensor(
                coordinator,
                device,
                "usage_info",
                "SESS_CNTR_KND_NM",
                "전력구분",
                None,
                None,
                None,
            ),
            KoreaSensor(
                coordinator,
                device,
                "usage_info",
                "SESS_MR_ST_DT",
                "검침시작일",
                SensorDeviceClass.DATE,
                None,
                None,
            ),
            KoreaSensor(
                coordinator,
                device,
                "usage_info",
                "SESS_MR_END_DT",
                "검침종료일",
                SensorDeviceClass.DATE,
                None,
                None,
            ),
            KoreaSensor(
                coordinator,
                device,
                "usage_info",
                "result.BILL_LAST_MONTH",
                "전월 요금",
                SensorDeviceClass.MONETARY,
                CURRENCY_KRW,
                SensorStateClass.TOTAL,
            ),
            KoreaSensor(
                coordinator,
                device,
                "usage_info",
                "result.PREDICT_TOTAL_CHARGE_REV",
                "당월 예상 요금",
                SensorDeviceClass.MONETARY,
                CURRENCY_KRW,
                SensorStateClass.TOTAL,
            ),
            KoreaSensor(
                coordinator,
                device,
                "usage_info",
                "result.BILL_LEVEL",
                "누진단계",
                None,
                "level",
                None
            ),
            KoreaSensor(
                coordinator,
                device,
                "usage_info",
                "result.TOTAL_CHARGE",
                "현재 요금",
                SensorDeviceClass.MONETARY,
                CURRENCY_KRW,
                SensorStateClass.TOTAL,
            ),
            KoreaSensor(
                coordinator,
                device,
                "usage_info",
                "result.PREDICT_KWH",
                "당월 예측 사용량",
                SensorDeviceClass.ENERGY,
                ENERGY_KILO_WATT_HOUR,
                SensorStateClass.TOTAL,
            ),
            KoreaSensor(
                coordinator,
                device,
                "recent_usage",
                "result.F_AP_QT",
                "현재 사용량",
                SensorDeviceClass.ENERGY,
                ENERGY_KILO_WATT_HOUR,
                SensorStateClass.TOTAL,
            ),
            KoreaSensor(
                coordinator,
                device,
                "usage_info",
                "result.F_AP_QT",
                "최근 사용량",
                SensorDeviceClass.ENERGY,
                ENERGY_KILO_WATT_HOUR,
                SensorStateClass.TOTAL_INCREASING,
            ),
            KoreaSensor(
                coordinator,
                device,
                "recent_usage",
                "result.ST_TIME",
                "최근 사용량 집계 일/시",
                SensorDeviceClass.TIMESTAMP,
                None,
                None,
            ),
            KoreaSensor(
                coordinator,
                device,
                "usage_info",
                "result.KWH_LAST_MONTH",
                "지난달 사용량",
                SensorDeviceClass.ENERGY,
                ENERGY_KILO_WATT_HOUR,
                SensorStateClass.TOTAL,
            ),
        ]
        async_add_entities(entities)

    elif service == "gasapp":
        entities = [
            KoreaSensor(
                coordinator,
                device,
                "current_bill",
                "history[-1].requestYm",
                "당월 검침일",
                SensorDeviceClass.DATE,
                None,
                None,
            ),
            KoreaSensor(
                coordinator,
                device,
                "current_bill",
                "history[-1].usageQty",
                "당월 가스 사용량",
                SensorDeviceClass.GAS,
                "m³",
                SensorStateClass.TOTAL,
            ),
            KoreaSensor(
                coordinator,
                device,
                "current_bill",
                "history[-1].chargeAmtQty",
                "당월 가스 요금",
                SensorDeviceClass.MONETARY,
                CURRENCY_KRW,
                SensorStateClass.TOTAL,
            ),
            KoreaSensor(
                coordinator,
                device,
                "current_bill",
                "history[-2].requestYm",
                "지난달 검침일",
                SensorDeviceClass.DATE,
                None,
                None,
            ),
            KoreaSensor(
                coordinator,
                device,
                "current_bill",
                "history[-2].usageQty",
                "지난달 가스 사용량",
                SensorDeviceClass.GAS,
                "m³",
                SensorStateClass.TOTAL,
            ),
            KoreaSensor(
                coordinator,
                device,
                "current_bill",
                "history[-2].chargeAmtQty",
                "지난달 가스 요금",
                SensorDeviceClass.MONETARY,
                CURRENCY_KRW,
                SensorStateClass.TOTAL,
            ),
            KoreaSensor(
                coordinator,
                device,
                "current_bill",
                "history[-3].requestYm",
                "지지난달 검침일",
                SensorDeviceClass.DATE,
                None,
                None,
            ),
            KoreaSensor(
                coordinator,
                device,
                "current_bill",
                "history[-3].usageQty",
                "지지난달 가스 사용량",
                SensorDeviceClass.GAS,
                "m³",
                SensorStateClass.TOTAL,
            ),
            KoreaSensor(
                coordinator,
                device,
                "current_bill",
                "history[-3].chargeAmtQty",
                "지지난달 가스 요금",
                SensorDeviceClass.MONETARY,
                CURRENCY_KRW,
                SensorStateClass.TOTAL,
            ),
            KoreaSensor(
                coordinator,
                device,
                "current_bill",
                "title1",
                "청구서 제목",
                None,
                None,
                None,
            ),
        ]
        async_add_entities(entities)

    elif service == "safety_alert":
        entities = [
            KoreaSensor(
                coordinator,
                device,
                "parsed_data",
                "total_alerts",
                "총 안전알림 수",
                None,
                "건",
                SensorStateClass.MEASUREMENT,
            ),
            KoreaSensor(
                coordinator,
                device,
                "parsed_data",
                "latest_alert.type",
                "최신 알림 유형",
                None,
                None,
                None,
            ),
            KoreaSensor(
                coordinator,
                device,
                "parsed_data",
                "latest_alert.message",
                "최신 알림 내용",
                None,
                None,
                None,
            ),
            KoreaSensor(
                coordinator,
                device,
                "parsed_data",
                "alert_types_summary",
                "알림 유형 요약",
                None,
                None,
                None,
            ),
        ]
        async_add_entities(entities)

    elif service == "goodsflow":
        entities = [
            KoreaSensor(
                coordinator,
                device,
                "parsed_data",
                "total_packages",
                "총 택배 수",
                None,
                "개",
                SensorStateClass.MEASUREMENT,
            ),
            KoreaSensor(
                coordinator,
                device,
                "parsed_data",
                "active_packages",
                "배송중인 택배",
                None,
                "개",
                SensorStateClass.MEASUREMENT,
            ),
            KoreaSensor(
                coordinator,
                device,
                "parsed_data",
                "delivered_packages",
                "배송완료 택배",
                None,
                "개",
                SensorStateClass.MEASUREMENT,
            ),
        ]
        async_add_entities(entities)

    elif service == "arisu":
        entities = [
            KoreaSensor(
                coordinator,
                device,
                "bill_data",
                "total_amount",
                "총 요금",
                SensorDeviceClass.MONETARY,
                CURRENCY_KRW,
                SensorStateClass.TOTAL,
            ),
            KoreaSensor(
                coordinator,
                device,
                "bill_data",
                "usage_info.current_usage",
                "당월 사용량",
                SensorDeviceClass.WATER,
                "m³",
                SensorStateClass.TOTAL,
            ),
            KoreaSensor(
                coordinator,
                device,
                "bill_data",
                "customer_info.address",
                "고객 주소",
                None,
                None,
                None,
            ),
            KoreaSensor(
                coordinator,
                device,
                "bill_data",
                "customer_info.payment_method",
                "납부 방법",
                None,
                None,
                None,
            ),
            KoreaSensor(
                coordinator,
                device,
                "bill_data",
                "arrears_info.overdue_amount",
                "연체 금액",
                SensorDeviceClass.MONETARY,
                CURRENCY_KRW,
                SensorStateClass.TOTAL,
            ),
            KoreaSensor(
                coordinator,
                device,
                "bill_data",
                "billing_month",
                "청구 월",
                None,
                None,
                None,
            ),
        ]
        async_add_entities(entities)

    elif service == "kakaomap":
        entities = [
            # 기본 정보
            KoreaSensor(
                coordinator,
                device,
                "start_address",
                "address",
                "출발지 주소",
                None,
                None,
                None,
            ),
            KoreaSensor(
                coordinator,
                device,
                "end_address",
                "address",
                "도착지 주소",
                None,
                None,
                None,
            ),

            # 추천 경로 정보
            KoreaSensor(
                coordinator,
                device,
                "transport_route",
                "summary.recommended_route.time",
                "추천 경로 소요시간",
                SensorDeviceClass.DURATION,
                "min",
                None,
            ),
            KoreaSensor(
                coordinator,
                device,
                "transport_route",
                "summary.recommended_route.fare",
                "추천 경로 요금",
                SensorDeviceClass.MONETARY,
                CURRENCY_KRW,
                None,
            ),
            KoreaSensor(
                coordinator,
                device,
                "transport_route",
                "summary.recommended_route.type",
                "추천 경로 교통수단",
                None,
                None,
                None,
            ),
            KoreaSensor(
                coordinator,
                device,
                "transport_route",
                "summary.recommended_route.transfers",
                "추천 경로 환승횟수",
                None,
                "회",
                SensorStateClass.MEASUREMENT,
            ),
            KoreaSensor(
                coordinator,
                device,
                "transport_route",
                "summary.recommended_route.walking_distance",
                "추천 경로 도보거리",
                SensorDeviceClass.DISTANCE,
                "m",
                None,
            ),
            KoreaSensor(
                coordinator,
                device,
                "transport_route",
                "summary.recommended_route.walking_time",
                "추천 경로 도보시간",
                SensorDeviceClass.DURATION,
                "min",
                None,
            ),

            # 최단시간 경로
            KoreaSensor(
                coordinator,
                device,
                "transport_route",
                "summary.fastest_route.time",
                "최단시간 경로 소요시간",
                SensorDeviceClass.DURATION,
                "min",
                None,
            ),
            KoreaSensor(
                coordinator,
                device,
                "transport_route",
                "summary.fastest_route.fare",
                "최단시간 경로 요금",
                SensorDeviceClass.MONETARY,
                CURRENCY_KRW,
                None,
            ),
            KoreaSensor(
                coordinator,
                device,
                "transport_route",
                "summary.fastest_route.type",
                "최단시간 경로 교통수단",
                None,
                None,
                None,
            ),
            KoreaSensor(
                coordinator,
                device,
                "transport_route",
                "summary.fastest_route.transfers",
                "최단시간 경로 환승횟수",
                None,
                "회",
                SensorStateClass.MEASUREMENT,
            ),

            # 최소환승 경로
            KoreaSensor(
                coordinator,
                device,
                "transport_route",
                "summary.least_transfer_route.time",
                "최소환승 경로 소요시간",
                SensorDeviceClass.DURATION,
                "min",
                None,
            ),
            KoreaSensor(
                coordinator,
                device,
                "transport_route",
                "summary.least_transfer_route.fare",
                "최소환승 경로 요금",
                SensorDeviceClass.MONETARY,
                CURRENCY_KRW,
                None,
            ),
            KoreaSensor(
                coordinator,
                device,
                "transport_route",
                "summary.least_transfer_route.type",
                "최소환승 경로 교통수단",
                None,
                None,
                None,
            ),
            KoreaSensor(
                coordinator,
                device,
                "transport_route",
                "summary.least_transfer_route.transfers",
                "최소환승 경로 환승횟수",
                None,
                "회",
                SensorStateClass.MEASUREMENT,
            ),

            # 첫 번째 경로 상세 정보
            KoreaSensor(
                coordinator,
                device,
                "transport_route",
                "routes[0].time",
                "첫번째 경로 소요시간",
                SensorDeviceClass.DURATION,
                "min",
                None,
            ),
            KoreaSensor(
                coordinator,
                device,
                "transport_route",
                "routes[0].fare",
                "첫번째 경로 요금",
                SensorDeviceClass.MONETARY,
                CURRENCY_KRW,
                None,
            ),
            KoreaSensor(
                coordinator,
                device,
                "transport_route",
                "routes[0].distance",
                "첫번째 경로 거리",
                SensorDeviceClass.DISTANCE,
                "km",
                None,
            ),
            KoreaSensor(
                coordinator,
                device,
                "transport_route",
                "routes[0].type",
                "첫번째 경로 교통수단",
                None,
                None,
                None,
            ),
            KoreaSensor(
                coordinator,
                device,
                "transport_route",
                "routes[0].first_departure_info",
                "첫번째 경로 첫차 정보",
                None,
                None,
                None,
            ),
            KoreaSensor(
                coordinator,
                device,
                "transport_route",
                "routes[0].next_departure_info",
                "첫번째 경로 다음차 정보",
                None,
                None,
                None,
            ),

            # 첫 번째 경로 상세 단계 정보 (steps)
            KoreaSensor(
                coordinator,
                device,
                "transport_route",
                "routes[0].steps[0].information",
                "첫번째 경로 1단계 정보",
                None,
                None,
                None,
            ),
            KoreaSensor(
                coordinator,
                device,
                "transport_route",
                "routes[0].steps[0].action",
                "첫번째 경로 1단계 행동",
                None,
                None,
                None,
            ),
            KoreaSensor(
                coordinator,
                device,
                "transport_route",
                "routes[0].steps[1].information",
                "첫번째 경로 2단계 정보",
                None,
                None,
                None,
            ),
            KoreaSensor(
                coordinator,
                device,
                "transport_route",
                "routes[0].steps[1].type",
                "첫번째 경로 2단계 유형",
                None,
                None,
                None,
            ),
            KoreaSensor(
                coordinator,
                device,
                "transport_route",
                "routes[0].steps[1].distance.value",
                "첫번째 경로 2단계 거리",
                SensorDeviceClass.DISTANCE,
                "m",
                None,
            ),
            KoreaSensor(
                coordinator,
                device,
                "transport_route",
                "routes[0].steps[1].time.value",
                "첫번째 경로 2단계 소요시간",
                SensorDeviceClass.DURATION,
                "s",
                None,
            ),
            KoreaSensor(
                coordinator,
                device,
                "transport_route",
                "routes[0].steps[2].information",
                "첫번째 경로 3단계 정보",
                None,
                None,
                None,
            ),
            KoreaSensor(
                coordinator,
                device,
                "transport_route",
                "routes[0].steps[2].type",
                "첫번째 경로 3단계 유형",
                None,
                None,
                None,
            ),
            KoreaSensor(
                coordinator,
                device,
                "transport_route",
                "routes[0].steps[2].distance.value",
                "첫번째 경로 3단계 거리",
                SensorDeviceClass.DISTANCE,
                "m",
                None,
            ),
            KoreaSensor(
                coordinator,
                device,
                "transport_route",
                "routes[0].steps[2].time.value",
                "첫번째 경로 3단계 소요시간",
                SensorDeviceClass.DURATION,
                "s",
                None,
            ),
            KoreaSensor(
                coordinator,
                device,
                "transport_route",
                "routes[0].steps[3].information",
                "첫번째 경로 4단계 정보",
                None,
                None,
                None,
            ),
            KoreaSensor(
                coordinator,
                device,
                "transport_route",
                "routes[0].steps[3].type",
                "첫번째 경로 4단계 유형",
                None,
                None,
                None,
            ),
            KoreaSensor(
                coordinator,
                device,
                "transport_route",
                "routes[0].steps[3].distance.value",
                "첫번째 경로 4단계 거리",
                SensorDeviceClass.DISTANCE,
                "m",
                None,
            ),
            KoreaSensor(
                coordinator,
                device,
                "transport_route",
                "routes[0].steps[3].time.value",
                "첫번째 경로 4단계 소요시간",
                SensorDeviceClass.DURATION,
                "s",
                None,
            ),
            KoreaSensor(
                coordinator,
                device,
                "transport_route",
                "routes[0].steps[4].information",
                "첫번째 경로 5단계 정보",
                None,
                None,
                None,
            ),
            KoreaSensor(
                coordinator,
                device,
                "transport_route",
                "routes[0].steps[4].type",
                "첫번째 경로 5단계 유형",
                None,
                None,
                None,
            ),
            KoreaSensor(
                coordinator,
                device,
                "transport_route",
                "routes[0].steps[-2].information",
                "첫번째 경로 끝에서2단계 정보",
                None,
                None,
                None,
            ),
            KoreaSensor(
                coordinator,
                device,
                "transport_route",
                "routes[0].steps[-1].information",
                "첫번째 경로 마지막단계 정보",
                None,
                None,
                None,
            ),
            KoreaSensor(
                coordinator,
                device,
                "transport_route",
                "routes[0].steps[-1].action",
                "첫번째 경로 마지막단계 행동",
                None,
                None,
                None,
            ),

            # 첫 번째 경로의 총 단계 수
            KoreaSensor(
                coordinator,
                device,
                "transport_route",
                "routes[0].steps",
                "첫번째 경로 총 단계수",
                None,
                "단계",
                SensorStateClass.MEASUREMENT,
            ),

            # 전체 경로 통계
            KoreaSensor(
                coordinator,
                device,
                "transport_route",
                "summary.route_summary",
                "경로 요약",
                None,
                None,
                None,
            ),
            KoreaSensor(
                coordinator,
                device,
                "transport_route",
                "summary.total_routes",
                "총 경로 수",
                None,
                "개",
                SensorStateClass.MEASUREMENT,
            ),
            KoreaSensor(
                coordinator,
                device,
                "transport_route",
                "summary.average_time",
                "평균 소요시간",
                SensorDeviceClass.DURATION,
                "min",
                None,
            ),
            KoreaSensor(
                coordinator,
                device,
                "transport_route",
                "summary.average_fare",
                "평균 요금",
                SensorDeviceClass.MONETARY,
                CURRENCY_KRW,
                None,
            ),

            # 실시간 교통 정보
            KoreaSensor(
                coordinator,
                device,
                "transport_route",
                "real_time_info.subway_delay",
                "지하철 지연 정보",
                None,
                None,
                None,
            ),
            KoreaSensor(
                coordinator,
                device,
                "transport_route",
                "real_time_info.bus_arrival_time",
                "버스 도착 예정시간",
                SensorDeviceClass.DURATION,
                "min",
                None,
            ),
            KoreaSensor(
                coordinator,
                device,
                "transport_route",
                "last_updated",
                "마지막 업데이트",
                SensorDeviceClass.TIMESTAMP,
                None,
                None,
            ),
        ]
        async_add_entities(entities)


class KoreaSensor(CoordinatorEntity, SensorEntity):
    """Generic Korea sensor using unified data access pattern."""

    _attr_has_entity_name = True

    def __init__(
            self,
            coordinator: DataUpdateCoordinator,
            device: DeviceType,
            data_key: str,
            value_key: str,
            name: str,
            device_class: Optional[SensorDeviceClass],
            unit: Optional[str],
            state_class: Optional[SensorStateClass],
    ) -> None:
        """Initialize the Korea sensor."""
        super().__init__(coordinator)
        self._device: DeviceType = device
        self._data_key: str = data_key
        self._value_key: str = value_key
        self._attr_name: str = name
        self._attr_device_class: Optional[SensorDeviceClass] = device_class
        self._attr_native_unit_of_measurement: Optional[str] = unit
        self._attr_state_class: Optional[SensorStateClass] = state_class
        self._attr_unique_id: str = f"{device.unique_id}_{data_key}_{value_key.replace('.', '_')}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return self._device.device_info

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self._device.available and self.coordinator.last_update_success

    @property
    def native_value(self) -> Any:
        """Return the native value of the sensor."""
        if not self.coordinator.data:
            return None

        data_source: Optional[Dict[str, Any]] = self.coordinator.data.get(self._data_key)
        if not data_source:
            return None

        raw_value = get_value_from_path(data_source, self._value_key)

        # Convert string values to appropriate types for specific device classes
        if raw_value is not None and self._attr_device_class:
            if self._attr_device_class == SensorDeviceClass.DATE:
                # Parse date values
                if isinstance(raw_value, str):
                    parsed_date = parse_date_value(raw_value)
                    if parsed_date:
                        return parsed_date.date()
                    return None

            elif self._attr_device_class == SensorDeviceClass.TIMESTAMP:
                # Parse datetime values
                if isinstance(raw_value, str):
                    parsed_datetime = parse_date_value(raw_value)
                    if parsed_datetime:
                        return parsed_datetime
                    return None

            elif self._attr_device_class == SensorDeviceClass.MONETARY \
                    or self._attr_device_class == SensorDeviceClass.DISTANCE \
                    or self._attr_device_class == SensorDeviceClass.GAS \
                    or self._attr_device_class == SensorDeviceClass.WATER \
                    :
                # Extract numeric value from strings like "1,550원"
                if isinstance(raw_value, str):
                    import re
                    numeric_match = re.search(r'[\d,]+', raw_value)
                    if numeric_match:
                        numeric_str = numeric_match.group().replace(',', '')
                        try:
                            return int(numeric_str)
                        except ValueError:
                            return None
            elif self._attr_device_class == SensorDeviceClass.DURATION:
                # Extract numeric value from strings like "28분"
                if isinstance(raw_value, str):
                    import re
                    numeric_match = re.search(r'\d+', raw_value)
                    if numeric_match:
                        try:
                            return int(numeric_match.group())
                        except ValueError:
                            return None

        return raw_value
