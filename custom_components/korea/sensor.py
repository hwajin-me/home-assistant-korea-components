from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, CURRENCY_KRW, ENERGY_KILO_WATT_HOUR
from .kepco.device import KepcoDevice


async def async_setup_entry(hass, entry, async_add_entities):
    if entry.data.get("service") != "kepco":
        return

    coordinator = hass.data[DOMAIN][entry.entry_id]
    device: KepcoDevice = coordinator.device

    entities = [
        KepcoSensor(
            coordinator,
            device,
            "recent_usage",
            "F_AP_QT",
            "최근 사용량",
            SensorDeviceClass.ENERGY,
            ENERGY_KILO_WATT_HOUR,
            SensorStateClass.TOTAL_INCREASING,
        ),
        KepcoSensor(
            coordinator,
            device,
            "recent_usage",
            "KWH_BILL",
            "당월 예측 사용량",
            SensorDeviceClass.ENERGY,
            ENERGY_KILO_WATT_HOUR,
            SensorStateClass.TOTAL,
        ),
        KepcoSensor(
            coordinator,
            device,
            "usage_info",
            "BILL_LAST_MONTH",
            "전월 요금",
            SensorDeviceClass.MONETARY,
            CURRENCY_KRW,
            SensorStateClass.TOTAL,
        ),
        KepcoSensor(
            coordinator,
            device,
            "usage_info",
            "PREDICT_TOTAL_CHARGE_REV",
            "당월 예상 요금",
            SensorDeviceClass.MONETARY,
            CURRENCY_KRW,
            SensorStateClass.TOTAL,
        ),
    ]
    async_add_entities(entities)


class KepcoSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True

    def __init__(
            self,
            coordinator,
            device: KepcoDevice,
            data_key,
            value_key,
            name,
            device_class,
            unit,
            state_class,
    ):
        super().__init__(coordinator)
        self._device = device
        self._data_key = data_key
        self._value_key = value_key
        self._attr_name = f"한전 {name}"
        self._attr_unique_id = f"{device.unique_id}_{value_key}"
        self._attr_device_class = device_class
        self._attr_unit_of_measurement = unit
        self._attr_state_class = state_class
        self._update_state()

    @property
    def device_info(self) -> DeviceInfo:
        return self._device.device_info

    @property
    def available(self) -> bool:
        return (
                super().available
                and self.coordinator.data is not None
                and self._data_key in self.coordinator.data
                and self.coordinator.data[self._data_key] is not None
        )

    def _update_state(self):
        if self.available:
            value = self.coordinator.data[self._data_key]["result"].get(self._value_key)
            if isinstance(value, str):
                self._attr_native_value = value.replace(",", "")
            else:
                self._attr_native_value = value
        else:
            self._attr_native_value = None

    @callback
    def _handle_coordinator_update(self) -> None:
        self._update_state()
        self.async_write_ha_state()
