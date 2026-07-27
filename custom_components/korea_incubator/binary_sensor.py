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
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    """Set up Korea binary sensors from a config entry."""
    data: Dict[str, Any] = hass.data[DOMAIN][entry.entry_id]
    coordinator: DataUpdateCoordinator = data["coordinator"]
    device: DeviceType = data["device"]
    service: str = entry.data.get("service")

    entities = []

    if service == "safety_alert":
        entities.append(
            SafetyAlertSensor(
                coordinator=coordinator,
                device=device,
                name="안전 알림",
                id="safety_alert",
                device_class=BinarySensorDeviceClass.SAFETY,
            )
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
    ):
        """Initialize the safety alert sensor."""
        super().__init__(coordinator)
        self._device: SafetyAlertDevice = device
        self._attr_name: str = name
        self._attr_device_class: Optional[BinarySensorDeviceClass] = device_class
        self._attr_is_on = False
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

        # Get the latest alert data
        latest_alert = self.coordinator.data.get("parsed_data", {}).get("data", [{}])[0]
        if not latest_alert:
            return None

        alerts = []
        for alert in self.coordinator.data.get("parsed_data", {}).get("data", []):
            alerts.append(
                {
                    "emergency_step": alert.get("EMRGNCY_STEP_NM"),
                    "disaster_type": alert.get("DSSTR_SE_NM"),
                    "message": alert.get("MSG_CN"),
                    "reception_area": alert.get("RCV_AREA_NM"),
                    "registration_date": parse_date_value(alert.get("REGIST_DT")),
                }
            )

        # Sort alerts by registration date in descending order
        alerts.sort(key=lambda x: x["registration_date"], reverse=True)

        return {
            "latest": {
                "emergency_step": latest_alert.get("EMRGNCY_STEP_NM"),
                "disaster_type": latest_alert.get("DSSTR_SE_NM"),
                "message": latest_alert.get("MSG_CN"),
                "reception_area": latest_alert.get("RCV_AREA_NM"),
                "registration_date": parse_date_value(latest_alert.get("REGIST_DT")),
            },
            "alerts": alerts,
        }

    @property
    def is_on(self) -> bool | None:
        """Return True if the safety alert sensor is on."""
        if not self.coordinator.data:
            return None

        # Get the latest alert data
        latest_alert = self.coordinator.data.get("parsed_data", {}).get("data", [{}])
        if not latest_alert:
            return None

        # Check if there is an emergency step name
        # and regist date is greater or equal to the current date

        return bool(
            latest_alert[0].get("EMRGNCY_STEP_NM")
            and parse_date_value(latest_alert[0].get("REGIST_DT"))
            >= datetime.datetime.combine(
                datetime.date.today(),
                datetime.time(0, 0, 0),
                tzinfo=pytz.timezone("Asia/Seoul"),
            )
        )
