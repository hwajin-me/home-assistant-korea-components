"""Current opening state and complete details of a selected pharmacy."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ..animal_medical.coordinates import point_wgs84
from ..animal_medical.sensor import AnimalMedicalSensor
from ..const import DOMAIN
from .api import weekly_hours


class PharmacySensor(AnimalMedicalSensor):
    _attr_has_entity_name = True
    _attr_icon = "mdi:pharmacy"

    def __init__(self, coordinator, entry_data):
        CoordinatorEntity.__init__(self, coordinator)
        self._entry_data = dict(entry_data)
        identifier = f"pharmacy_{entry_data['hpid']}"
        self._attr_unique_id = f"{DOMAIN}_{identifier}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, identifier)},
            name="약국",
            manufacturer="국립중앙의료원",
            model="약국 운영정보",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data or {}
        place = data.get("_kakao", {})
        gps = point_wgs84({"lat": data.get("wgs84Lat"), "lon": data.get("wgs84Lon")})
        gps = gps or point_wgs84(place.get("summary", {}).get("point"))
        state = self.native_value
        return {
            "api_record": {k: v for k, v in data.items() if not k.startswith("_kakao")},
            "hpid": data.get("hpid"),
            "business_name": data.get("dutyName"),
            "road_address": data.get("dutyAddr"),
            "phone": data.get("dutyTel1"),
            "public_notes": data.get("dutyEtc"),
            "opening_hours_source": "kakao",
            "weekly_hours": weekly_hours(data),
            **gps,
            "gps_coordinate_system": "EPSG:4326",
            "location_available": bool(gps),
            "opening_hours_available": state is not None,
            "open_now": None if state is None else state == "open",
            "kakao_place_id": place.get("place_id"),
            "kakao_details": place.get("summary"),
            "opening_hours": place.get("open_hours"),
            "opening_schedule": place.get("schedule"),
            "opening_hours_updated": place.get("fetched_at"),
            "opening_hours_error": data.get("_kakao_error"),
            "last_refresh": self.coordinator.last_refresh.isoformat()
            if self.coordinator.last_refresh
            else None,
            "next_refresh": self.coordinator.next_refresh.isoformat()
            if self.coordinator.next_refresh
            else None,
            "scan_interval_minutes": self.coordinator.interval_minutes,
        }
