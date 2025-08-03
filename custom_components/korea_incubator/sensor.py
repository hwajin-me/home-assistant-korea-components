from __future__ import annotations

from typing import Dict, Any, Optional, Union

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator

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
    """Get a value from a nested dictionary using a dot-separated path."""
    keys = path.split('.')
    value = data
    for key in keys:
        if isinstance(value, dict):
            value = value.get(key)
        else:
            return None
        if value is None:
            return None
    return value


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
                "recent_usage",
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
                "result.KWH_BILL",
                "당월 예측 사용량",
                SensorDeviceClass.ENERGY,
                ENERGY_KILO_WATT_HOUR,
                SensorStateClass.TOTAL,
            ),
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
        ]
        async_add_entities(entities)

    elif service == "gasapp":
        entities = [
            KoreaSensor(
                coordinator,
                device,
                "current_bill",
                "history.0.usageQty",
                "당월 가스 사용량",
                SensorDeviceClass.GAS,
                "m³",
                SensorStateClass.TOTAL,
            ),
            KoreaSensor(
                coordinator,
                device,
                "current_bill",
                "history.0.chargeAmtQty",
                "당월 가스 요금",
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
            KoreaSensor(
                coordinator,
                device,
                "current_bill",
                "title2",
                "총 청구 요금",
                SensorDeviceClass.MONETARY,
                CURRENCY_KRW,
                SensorStateClass.TOTAL,
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
            KoreaSensor(
                coordinator,
                device,
                "transport_route",
                "summary.recommended_route.time",
                "추천 경로 소요시간",
                SensorDeviceClass.DURATION,
                "min",  # Changed from "분" to "min" for Home Assistant standard
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

        # Convert string values to numeric for specific device classes
        if raw_value is not None and self._attr_device_class:
            if self._attr_device_class == SensorDeviceClass.MONETARY \
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
