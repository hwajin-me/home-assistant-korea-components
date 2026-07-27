from __future__ import annotations

from typing import Dict, Any, Optional, Union, Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .arisu.device import ArisuDevice
from .const import DOMAIN, ENERGY_KILO_WATT_HOUR, CURRENCY_KRW
from .gasapp.device import GasAppDevice
from .goodsflow.device import GoodsFlowDevice
from .kakaomap.device import KakaoMapDevice
from .kepco.device import KepcoDevice
from .safety_alert.device import SafetyAlertDevice
from .utils import get_value_from_path, parse_date_value

# Device type union for type hints
DeviceType = Union[
    KepcoDevice,
    GasAppDevice,
    SafetyAlertDevice,
    GoodsFlowDevice,
    ArisuDevice,
    KakaoMapDevice,
]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
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
                None,
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
                "metadata",
                "count",
                "총 안전알림 수",
                None,
                "건",
                SensorStateClass.MEASUREMENT,
            ),
            KoreaSensor(
                coordinator,
                device,
                "parsed_data",
                "data[0].EMRGNCY_STEP_NM",
                "최신 알림 유형",
                None,
                None,
                None,
            ),
            KoreaSensor(
                coordinator,
                device,
                "parsed_data",
                "data[0].DSSTR_SE_NM",
                "최신 재난 유형",
                None,
                None,
                None,
            ),
            KoreaSensor(
                coordinator,
                device,
                "parsed_data",
                "data[0].MSG_CN",
                "최신 알림 내용",
                None,
                None,
                None,
            ),
            KoreaSensor(
                coordinator,
                device,
                "parsed_data",
                "data[0].RCV_AREA_NM",
                "최신 알림 대상지",
                None,
                None,
                None,
                value_translation=lambda x: (
                    x["data"][0]["RCV_AREA_NM"]
                    if "data" in x and len(x["data"][0]["RCV_AREA_NM"]) < 250
                    else "전체"
                ),
            ),
            KoreaSensor(
                coordinator,
                device,
                "parsed_data",
                "data[0].REGIST_DT",
                "최신 알림일자",
                SensorDeviceClass.TIMESTAMP,
                None,
                None,
            ),
            KoreaSensor(
                coordinator,
                device,
                "parsed_data",
                "data[1].EMRGNCY_STEP_NM",
                "지난 알림 유형",
                None,
                None,
                None,
            ),
            KoreaSensor(
                coordinator,
                device,
                "parsed_data",
                "data[1].DSSTR_SE_NM",
                "지난 재난 유형",
                None,
                None,
                None,
            ),
            KoreaSensor(
                coordinator,
                device,
                "parsed_data",
                "data[1].MSG_CN",
                "지난 알림 내용",
                None,
                None,
                None,
            ),
            KoreaSensor(
                coordinator,
                device,
                "parsed_data",
                "data[1].RCV_AREA_NM",
                "지난 알림 대상지",
                None,
                None,
                None,
                value_translation=lambda x: (
                    x["data"][1]["RCV_AREA_NM"]
                    if "data" in x and len(x["data"][1]["RCV_AREA_NM"]) < 250
                    else "전체"
                ),
            ),
            KoreaSensor(
                coordinator,
                device,
                "parsed_data",
                "data[1].REGIST_DT",
                "지난 알림일자",
                SensorDeviceClass.TIMESTAMP,
                None,
                None,
            ),
            KoreaSensor(
                coordinator,
                device,
                "parsed_data",
                "data[2].EMRGNCY_STEP_NM",
                "지지난 알림 유형",
                None,
                None,
                None,
            ),
            KoreaSensor(
                coordinator,
                device,
                "parsed_data",
                "data[2].DSSTR_SE_NM",
                "지지난 재난 유형",
                None,
                None,
                None,
            ),
            KoreaSensor(
                coordinator,
                device,
                "parsed_data",
                "data[2].MSG_CN",
                "지지난 알림 내용",
                None,
                None,
                None,
            ),
            KoreaSensor(
                coordinator,
                device,
                "parsed_data",
                "data[2].RCV_AREA_NM",
                "지지난 알림 대상지",
                None,
                None,
                None,
                ## 너무 길면 에러나서 250자 이상이면 "전체" 로 표기
                value_translation=lambda x: (
                    x["data"][2]["RCV_AREA_NM"]
                    if "data" in x and len(x["data"][2]["RCV_AREA_NM"]) < 250
                    else "전체"
                ),
            ),
            KoreaSensor(
                coordinator,
                device,
                "parsed_data",
                "data[2].REGIST_DT",
                "지지난 알림일자",
                SensorDeviceClass.TIMESTAMP,
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
        data_key: Optional[str],
        value_key: Optional[str],
        name: str,
        device_class: Optional[SensorDeviceClass],
        unit: Optional[str],
        state_class: Optional[SensorStateClass],
        icon: Optional[str] = None,
        value_translation: Optional[Callable[[Any], Any]] = None,
    ) -> None:
        """Initialize the Korea sensor."""
        super().__init__(coordinator)
        self._device: DeviceType = device
        self._data_key: str = data_key
        self._value_key: str = value_key
        self._value_translation: Optional[Callable[[Any], Any]] = value_translation
        self._attr_name: str = name
        self._attr_device_class: Optional[SensorDeviceClass] = device_class
        self._attr_native_unit_of_measurement: Optional[str] = unit
        self._attr_state_class: Optional[SensorStateClass] = state_class
        self._attr_icon: Optional[str] = icon
        self._attr_unique_id: str = (
            f"korea_{device.unique_id}_{data_key}_{value_key.replace('.', '_')}"
        )

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

        if self.coordinator.data is not None and self._value_translation:
            # Apply custom value translation if provided
            return self._value_translation(self.coordinator.data)

        data_source: Optional[Dict[str, Any]] = self.coordinator.data.get(
            self._data_key
        )
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

            elif (
                self._attr_device_class == SensorDeviceClass.MONETARY
                or self._attr_device_class == SensorDeviceClass.DISTANCE
                or self._attr_device_class == SensorDeviceClass.GAS
                or self._attr_device_class == SensorDeviceClass.WATER
            ):
                # Extract numeric value from strings like "1,550원"
                if isinstance(raw_value, str):
                    import re

                    numeric_match = re.search(r"[\d,]+", raw_value)
                    if numeric_match:
                        numeric_str = numeric_match.group().replace(",", "")
                        try:
                            return int(numeric_str)
                        except ValueError:
                            return None
            elif self._attr_device_class == SensorDeviceClass.DURATION:
                # Extract numeric value from strings like "28분"
                if isinstance(raw_value, str):
                    import re

                    numeric_match = re.search(r"\d+", raw_value)
                    if numeric_match:
                        try:
                            return int(numeric_match.group())
                        except ValueError:
                            return None

        return raw_value
