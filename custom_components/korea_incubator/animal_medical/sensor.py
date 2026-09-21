"""Sensor exposing a selected animal hospital or animal pharmacy."""

from __future__ import annotations

from typing import Any, ClassVar

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ..const import DOMAIN
from . import ANIMAL_MEDICAL_TYPES
from .coordinates import point_wgs84, to_wgs84
from .hours import current_state


class AnimalMedicalSensor(CoordinatorEntity, SensorEntity):
    """Recalculate current opening state every minute without polling the API."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:paw"
    _attr_translation_key = "animal_medical_status"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options: ClassVar[list[str]] = ["open", "closed", "break"]

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self.async_on_remove(
            async_track_time_change(self.hass, self._async_clock_tick, second=0)
        )

    @callback
    def _async_clock_tick(self, _now):
        self.async_write_ha_state()

    def __init__(self, coordinator: Any, entry_data: dict[str, Any]) -> None:
        super().__init__(coordinator)
        kind = entry_data["institution_type"]
        name = entry_data["business_name"]
        identifier = (
            f"animal_{kind}_{entry_data['municipality_code']}_"
            f"{entry_data['management_number']}"
        )
        self._attr_unique_id = f"{DOMAIN}_{identifier}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, identifier)},
            name=name,
            manufacturer="행정안전부",
            model=ANIMAL_MEDICAL_TYPES[kind]["name"],
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def native_value(self) -> str | None:
        place = (self.coordinator.data or {}).get("_kakao", {})
        return current_state(place.get("schedule", {}))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        gps = to_wgs84(data.get("CRD_INFO_X"), data.get("CRD_INFO_Y"))
        place = data.get("_kakao", {})
        gps = gps or point_wgs84(place.get("summary", {}).get("point"))
        state = self.native_value
        return {
            **gps,
            "gps_coordinate_system": "EPSG:4326",
            "location_available": bool(gps),
            "operating_status": data.get("SALS_STTS_NM"),
            "opening_hours_available": state is not None,
            "open_now": None if state is None else state == "open",
            "kakao_place_id": place.get("place_id"),
            "kakao_details": place.get("summary"),
            "opening_hours": place.get("open_hours"),
            "opening_schedule": place.get("schedule"),
            "opening_hours_updated": place.get("fetched_at"),
            "opening_hours_error": data.get("_kakao_error"),
            "business_name": data.get("BPLC_NM"),
            "road_address": data.get("ROAD_NM_ADDR"),
            "lot_number_address": data.get("LOTNO_ADDR"),
            "phone": data.get("TELNO"),
            "municipality_code": data.get("OPN_ATMY_GRP_CD"),
            "management_number": data.get("MNG_NO"),
            "detailed_status": data.get("DTL_SALS_STTS_NM"),
            "license_date": data.get("LCPMT_YMD"),
            "license_cancelled_date": data.get("LCPMT_RTRCN_YMD"),
            "reopened_date": data.get("ROBIZ_YMD"),
            "suspension_start": data.get("TCBIZ_BGNG_YMD"),
            "suspension_end": data.get("TCBIZ_END_YMD"),
            "road_postcode": data.get("ROAD_NM_ZIP"),
            "lot_postcode": data.get("LCTN_ZIP"),
            "area": data.get("LCTN_AREA"),
            "status_code": data.get("SALS_STTS_CD"),
            "detailed_status_code": data.get("DTL_SALS_STTS_CD"),
            "rights_holder_number": data.get("RGHT_MNBD_SN"),
            "data_update_type": data.get("DAT_UPDT_SE"),
            "closed_date": data.get("CLSBIZ_YMD"),
            "last_modified": data.get("LAST_MDFCN_PNT"),
            "data_updated": data.get("DAT_UPDT_PNT"),
            "coordinate_x": data.get("CRD_INFO_X"),
            "coordinate_y": data.get("CRD_INFO_Y"),
            "coordinate_system": "EPSG:5174",
            "api_record": {
                key: value
                for key, value in data.items()
                if not key.startswith("_kakao")
            },
            "last_refresh": (
                self.coordinator.last_refresh.isoformat()
                if self.coordinator.last_refresh is not None
                else None
            ),
            "next_refresh": (
                self.coordinator.next_refresh.isoformat()
                if self.coordinator.next_refresh is not None
                else None
            ),
            "scan_interval_minutes": self.coordinator.interval_minutes,
        }
