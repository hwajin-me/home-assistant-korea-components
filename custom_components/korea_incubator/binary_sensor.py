from __future__ import annotations

import datetime
from typing import Dict, Any, Optional, Union, Mapping

import pytz
from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .arisu.device import ArisuDevice
from .const import DOMAIN
from .gasapp.device import GasAppDevice
from .goodsflow.device import GoodsFlowDevice
from .kakaomap.device import KakaoMapDevice
from .kepco.device import KepcoDevice
from .safety_alert.device import SafetyAlertDevice
from .utils import parse_date_value

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
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Korea binary sensors from a config entry."""
    data: Dict[str, Any] = hass.data[DOMAIN][entry.entry_id]
    service: str = entry.data.get("service")

    entities = []

    if service == "safety_alert":
        coordinator: DataUpdateCoordinator = data["coordinator"]
        device: DeviceType = data["device"]
        entities.append(
            SafetyAlertSensor(
                coordinator=coordinator,
                device=device,
                name="안전 알림",
                id="safety_alert",
                device_class=BinarySensorDeviceClass.SAFETY,
            )
        )
    elif service == "weather_warning":
        from .weather.sensor import WeatherWarningBinarySensor
        store = hass.data[DOMAIN][entry.entry_id]
        async_add_entities([WeatherWarningBinarySensor(store["coordinator"], ac)
                            for ac in store["area_codes"]])
        return

    elif service == "airkorea":
        from .airkorea.sensor import AirAlertBinarySensor
        store = hass.data[DOMAIN][entry.entry_id]
        c = store["coordinator"]
        for st in store.get("stations", []):
            entities.append(
                AirAlertBinarySensor(c, st["stationName"], entry.data.get("sido", ""))
            )

    if entities:
        async_add_entities(entities)


class SafetyAlertSensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor for safety alert data."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        device: SafetyAlertDevice,
        name: str,
        id: str,
        device_class: Optional[BinarySensorDeviceClass] = None,
        icon: Optional[str] = None,
    ) -> None:
        """Initialize the safety alert sensor."""
        super().__init__(coordinator)
        self._device: SafetyAlertDevice = device
        self._attr_name: str = name
        self._attr_device_class: Optional[BinarySensorDeviceClass] = device_class
        self._attr_is_on: bool = False
        self._attr_icon: Optional[str] = icon
        self._attr_unique_id: str = f"korea_{device.unique_id}_{id}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return self._device.device_info

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self._device.available and self.coordinator.last_update_success

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return the state attributes of the sensor."""
        if not self.coordinator.data:
            return None

        raw_alerts = self.coordinator.data.get("parsed_data", {}).get("data", [])
        if not raw_alerts:
            return {"latest": None, "alerts": []}

        alerts = [
            {
                "emergency_step": a.get("EMRGNCY_STEP_NM"),
                "disaster_type": a.get("DSSTR_SE_NM"),
                "message": a.get("MSG_CN"),
                "reception_area": a.get("RCV_AREA_NM"),
                "registration_date": parse_date_value(a.get("REGIST_DT")),
            }
            for a in raw_alerts
        ]
        alerts.sort(
            key=lambda x: x["registration_date"] or datetime.datetime.min.replace(
                tzinfo=pytz.timezone("Asia/Seoul")
            ),
            reverse=True,
        )

        return {
            "latest": alerts[0],
            "alerts": alerts,
        }

    @property
    def is_on(self) -> bool | None:
        """Return True if the safety alert sensor is on."""
        if not self.coordinator.data:
            return None

        raw_alerts = self.coordinator.data.get("parsed_data", {}).get("data", [])
        if not raw_alerts:
            return False

        latest = raw_alerts[0]
        if not latest.get("EMRGNCY_STEP_NM"):
            return False

        regist_dt = parse_date_value(latest.get("REGIST_DT"))
        if regist_dt is None:
            return False

        # 현재 시간으로부터 10분 이내 발송된 알림이면 ON
        threshold = datetime.datetime.now(tz=pytz.timezone("Asia/Seoul")) - datetime.timedelta(minutes=10)
        return regist_dt >= threshold
