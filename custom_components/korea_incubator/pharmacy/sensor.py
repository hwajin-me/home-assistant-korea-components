"""Current opening state and complete details of a selected pharmacy."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ..animal_medical.coordinates import point_wgs84
from ..animal_medical.hours import effective_schedule
from ..animal_medical.sensor import AnimalMedicalSensor, institution_identifier
from ..const import DOMAIN
from .api import weekly_hours


class PharmacySensor(AnimalMedicalSensor):
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry_data):
        CoordinatorEntity.__init__(self, coordinator)
        self._entry_data = dict(entry_data)
        identifier = institution_identifier(entry_data)
        self._attr_unique_id = f"{DOMAIN}_{identifier}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, identifier)},
            name=(coordinator.data or {}).get("dutyName")
            or entry_data["business_name"],
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
            "api_record": {
                k: v for k, v in data.items() if not k.startswith(("_kakao", "_naver"))
            },
            "hpid": data.get("hpid"),
            "business_name": data.get("dutyName"),
            "road_address": data.get("dutyAddr"),
            "phone": data.get("dutyTel1"),
            "public_notes": data.get("dutyEtc"),
            "opening_hours_source": "naver+kakao" if data.get("_naver") else "kakao",
            "weekly_hours": weekly_hours(data),
            **gps,
            "gps_coordinate_system": "EPSG:4326",
            "location_available": bool(gps),
            "opening_hours_available": state is not None,
            "open_now": None if state is None else state == "open",
            "kakao_place_id": place.get("place_id"),
            "kakao_details": place.get("summary"),
            "opening_hours": place.get("open_hours"),
            "opening_schedule": effective_schedule(data),
            "opening_hours_updated": data.get("_naver", {}).get("fetched_at")
            or place.get("fetched_at"),
            "opening_hours_error": data.get("_naver_error")
            or data.get("_naver", {}).get("hours_error")
            or data.get("_kakao_error"),
            "last_refresh": self.coordinator.last_refresh.isoformat()
            if self.coordinator.last_refresh
            else None,
            "next_refresh": self.coordinator.next_refresh.isoformat()
            if self.coordinator.next_refresh
            else None,
            "scan_interval_minutes": self.coordinator.interval_minutes,
        }
