"""Consolidated public/place information with stable, device-scoped identities."""

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from ..const import DOMAIN
from .closed_days import upcoming_closed_days
from .hours import SEOUL, valid_schedule
from .icons import institution_icon, operating_icon
from .media import photo_url
from .schedule_sensor import MedicalTransitionSensor

NAMES = {
    "name": "이름",
    "location": "위치",
    "contact": "연락처",
    "details": "상세정보",
    "hours": "운영시간",
    "reviews": "리뷰",
    "photos": "사진",
    "updated": "정보 갱신",
    "closed_day": "다음 휴무일",
}

ICONS = {
    "location": "mdi:map-marker",
    "contact": "mdi:phone",
    "details": "mdi:card-text-outline",
    "reviews": "mdi:star-outline",
    "photos": "mdi:image-multiple-outline",
    "updated": "mdi:update",
    "closed_day": "mdi:calendar-remove",
}


class MedicalInfoSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, primary, kind):
        super().__init__(primary.coordinator)
        self.primary, self.kind = primary, kind
        self._attr_name = NAMES[kind]
        self._attr_unique_id = f"{primary.unique_id}_info_{kind}"
        self._attr_device_info = primary.device_info
        if kind == "updated":
            self._attr_device_class = SensorDeviceClass.TIMESTAMP
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        if kind == "closed_day":
            self._attr_device_class = SensorDeviceClass.DATE

    def _parts(self):
        attrs = self.primary.extra_state_attributes
        place = (self.coordinator.data or {}).get("_kakao", {})
        return attrs, place.get("summary", {}), place.get("media", {})

    @property
    def icon(self):
        if self.kind == "name":
            return institution_icon(self.primary._entry_data)
        if self.kind == "hours":
            return operating_icon(self.primary.native_value)
        return ICONS[self.kind]

    def _closed_days(self):
        days = (self.coordinator.data or {}).get("_kakao", {}).get("schedule", {})
        return upcoming_closed_days(days, dt_util.now().astimezone(SEOUL).date())

    def _native_value(self):
        attrs, summary, media = self._parts()
        if self.kind == "name":
            return (
                attrs.get("business_name")
                or summary.get("name")
                or self.primary._entry_data["business_name"]
            )
        if self.kind == "location":
            lat, lon = attrs.get("latitude"), attrs.get("longitude")
            return f"{lat}, {lon}" if lat is not None and lon is not None else None
        if self.kind == "contact":
            return attrs.get("phone") or None
        if self.kind == "details":
            return attrs.get("operating_status") or summary.get("status") or "정보 있음"
        if self.kind == "hours":
            return {"open": "영업 중", "closed": "영업 종료", "break": "휴게 중"}.get(
                self.primary.native_value
            )
        if self.kind == "reviews":
            return media.get("rating")
        if self.kind == "photos":
            return media.get("photo_count")
        if self.kind == "updated":
            return self.coordinator.last_refresh
        return next(iter(self._closed_days()), None)

    @property
    def native_value(self):
        value = self._native_value()
        return (
            value[:254] + "…" if isinstance(value, str) and len(value) > 255 else value
        )

    @property
    def entity_picture(self):
        if self.kind != "name":
            return None
        _, summary, media = self._parts()
        return photo_url(media.get("main_photo") or summary.get("main_photo_url"))

    @property
    def extra_state_attributes(self):
        attrs, summary, media = self._parts()
        if self.kind == "name":
            return {
                "business_name": attrs.get("business_name")
                or summary.get("name")
                or self.primary._entry_data["business_name"],
                "place_url": media.get("place_url"),
                "institution_type": self.primary.device_info["model"],
            }
        if self.kind == "location":
            return {
                key: attrs.get(key)
                for key in (
                    "latitude",
                    "longitude",
                    "road_address",
                    "lot_number_address",
                    "gps_coordinate_system",
                    "location_available",
                )
            }
        if self.kind == "contact":
            return {
                "phone_numbers": summary.get("phone_numbers"),
                "homepage": attrs["api_record"].get("dutyUrl")
                or summary.get("homepage"),
                "place_url": media.get("place_url"),
            }
        if self.kind == "details":
            return {"public_record": attrs["api_record"], "place_record": summary}
        if self.kind == "hours":
            return {
                key: attrs.get(key)
                for key in (
                    "opening_hours",
                    "opening_schedule",
                    "weekly_hours",
                    "opening_hours_updated",
                    "opening_hours_error",
                    "public_notes",
                )
            }
        if self.kind == "reviews":
            return {
                key: media.get(key)
                for key in (
                    "review_count",
                    "reviews",
                    "reviews_has_more",
                    "reviews_restricted",
                    "place_url",
                )
            }
        if self.kind == "photos":
            return {
                key: media.get(key)
                for key in ("photos", "main_photo", "photos_restricted", "place_url")
            }
        if self.kind == "updated":
            return {
                key: attrs.get(key)
                for key in (
                    "next_refresh",
                    "scan_interval_minutes",
                    "opening_hours_error",
                )
            }
        days = (self.coordinator.data or {}).get("_kakao", {}).get("schedule", {})
        if not valid_schedule(days):
            days = {}
        return {
            "closed_dates": [day.isoformat() for day in self._closed_days()],
            "known_dates": sorted(
                day for day, value in days.items() if value is not None
            ),
            "unknown_dates": sorted(
                day for day, value in days.items() if value is None
            ),
            "source": "kakao",
            "full_day_only": True,
        }

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        if self.kind in ("hours", "closed_day"):
            self.async_on_remove(
                async_track_time_change(self.hass, self._clock_tick, second=0)
            )

    @callback
    def _clock_tick(self, _now):
        self.async_write_ha_state()


def remove_retired_entities(hass, entry, primary):
    """Only remove replaced entities of this entry; recorder history is untouched."""
    registry = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if entity.platform == DOMAIN and (
            entity.unique_id.startswith(f"{primary.unique_id}_detail_")
            or entity.unique_id
            in {
                f"{primary.unique_id}_binary_{key}"
                for key in ("break", "hours", "location")
            }
        ):
            registry.async_remove(entity.entity_id)


def setup_compact_sensors(hass, entry, add, primary):
    remove_retired_entities(hass, entry, primary)
    add(
        [
            primary,
            *(MedicalInfoSensor(primary, key) for key in NAMES),
            MedicalTransitionSensor(primary, "start"),
            MedicalTransitionSensor(primary, "end"),
        ]
    )
