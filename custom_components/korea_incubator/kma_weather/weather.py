"""KMA Weather entity - full attributes."""
from __future__ import annotations
from typing import Any
from homeassistant.components.weather import (
    WeatherEntity, WeatherEntityFeature, Forecast,
)
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from ..const import DOMAIN

CONDITION_MAP = {
    "sunny": "sunny", "partlycloudy": "partlycloudy", "cloudy": "cloudy",
    "rainy": "rainy", "snowy": "snowy", "pouring": "pouring",
}


class KMAWeather(CoordinatorEntity, WeatherEntity):
    _attr_has_entity_name = True
    _attr_native_temperature_unit = "°C"
    _attr_native_wind_speed_unit = "m/s"
    _attr_native_precipitation_unit = "mm"
    _attr_native_pressure_unit = "hPa"
    _attr_supported_features = (
        WeatherEntityFeature.FORECAST_HOURLY | WeatherEntityFeature.FORECAST_DAILY
    )

    def __init__(self, coordinator, region_name):
        super().__init__(coordinator)
        self._region = region_name
        self._attr_unique_id = f"{DOMAIN}_weather_{region_name}"
        self._attr_name = None
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"weather_{region_name}")},
            name=f"기상청 날씨예보 - {region_name}",
            manufacturer="기상청", model="동네예보",
            entry_type=DeviceEntryType.SERVICE)

    def _data(self) -> dict[str, Any]:
        return (self.coordinator.data or {}).get(self._region, {})

    @property
    def condition(self):
        return CONDITION_MAP.get(self._data().get("condition"))

    @property
    def native_temperature(self):
        return self._data().get("temperature")

    @property
    def native_apparent_temperature(self) -> float | None:
        return self._data().get("apparent_temperature")

    @property
    def native_dew_point(self) -> float | None:
        return self._data().get("dew_point")

    @property
    def humidity(self):
        return self._data().get("humidity")

    @property
    def native_wind_speed(self):
        return self._data().get("wind_speed")

    @property
    def wind_bearing(self):
        return self._data().get("wind_bearing")

    @property
    def native_precipitation(self):
        return self._data().get("precipitation")

    @property
    def cloud_coverage(self) -> int | None:
        return self._data().get("cloud_coverage")

    @property
    def ozone(self) -> float | None:
        return self._data().get("ozone")

    @property
    def uv_index(self) -> float | None:
        return self._data().get("uv_index")

    async def async_forecast_hourly(self) -> list[Forecast]:
        return [Forecast(
            datetime=f["datetime"],
            condition=CONDITION_MAP.get(f.get("condition")),
            native_temperature=f.get("temperature"),
            native_apparent_temperature=f.get("apparent_temperature"),
            precipitation_probability=f.get("precipitation_probability"),
            native_precipitation=f.get("precipitation"),
            humidity=f.get("humidity"),
            native_wind_speed=f.get("wind_speed"),
            wind_bearing=f.get("wind_bearing"),
            cloud_coverage=f.get("cloud_coverage"),
            native_dew_point=f.get("dew_point"),
            uv_index=f.get("uv_index"),
        ) for f in self._data().get("hourly_forecasts", [])]

    async def async_forecast_daily(self) -> list[Forecast]:
        return [Forecast(
            datetime=f["datetime"],
            condition=CONDITION_MAP.get(f.get("condition")),
            native_temperature=f.get("temphigh"),
            native_templow=f.get("templow"),
            precipitation_probability=f.get("precipitation_probability"),
            humidity=f.get("humidity"),
            native_wind_speed=f.get("wind_speed"),
        ) for f in self._data().get("daily_forecasts", [])]
