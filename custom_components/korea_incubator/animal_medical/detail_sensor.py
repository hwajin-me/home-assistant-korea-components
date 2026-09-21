"""Korean-named entities for every public record and integration detail field."""

from __future__ import annotations

from datetime import date, datetime
from hashlib import sha256

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .hours import SEOUL

DATE_FIELDS = {
    ("public", key)
    for key in (
        "LCPMT_YMD",
        "LCPMT_RTRCN_YMD",
        "ROBIZ_YMD",
        "TCBIZ_BGNG_YMD",
        "TCBIZ_END_YMD",
        "CLSBIZ_YMD",
    )
}
TIMESTAMP_FIELDS = {
    ("public", "DAT_UPDT_PNT"),
    ("public", "LAST_MDFCN_PNT"),
    ("detail", "opening_hours_updated"),
    ("detail", "last_refresh"),
    ("detail", "next_refresh"),
}

PUBLIC_NAMES = {
    "BPLC_NM": "기관명",
    "MNG_NO": "관리번호",
    "OPN_ATMY_GRP_CD": "개방자치단체코드",
    "ROAD_NM_ADDR": "도로명주소",
    "LOTNO_ADDR": "지번주소",
    "TELNO": "전화번호",
    "SALS_STTS_NM": "인허가 영업상태",
    "SALS_STTS_CD": "영업상태 코드",
    "DTL_SALS_STTS_NM": "상세 영업상태",
    "DTL_SALS_STTS_CD": "상세 영업상태 코드",
    "LCPMT_YMD": "인허가일",
    "LCPMT_RTRCN_YMD": "인허가 취소일",
    "ROBIZ_YMD": "재개업일",
    "TCBIZ_BGNG_YMD": "휴업 시작일",
    "TCBIZ_END_YMD": "휴업 종료일",
    "CLSBIZ_YMD": "폐업일",
    "ROAD_NM_ZIP": "도로명 우편번호",
    "LCTN_ZIP": "지번 우편번호",
    "LCTN_AREA": "소재지 면적",
    "RGHT_MNBD_SN": "권리주체 일련번호",
    "DAT_UPDT_SE": "데이터 갱신 구분",
    "DAT_UPDT_PNT": "데이터 갱신 시각",
    "LAST_MDFCN_PNT": "최종 수정 시각",
    "CRD_INFO_X": "원본 좌표 가로",
    "CRD_INFO_Y": "원본 좌표 세로",
    "hpid": "기관 식별번호",
    "dutyName": "기관명",
    "dutyAddr": "도로명주소",
    "dutyTel1": "전화번호",
    "dutyTel3": "응급실 전화번호",
    "dutyEtc": "공공 안내사항",
    "dutyMapimg": "찾아오는 길",
    "dutyInf": "기관 안내",
    "dutyUrl": "홈페이지",
    "dutyImg": "기관 이미지",
    "postCdn1": "우편번호 앞자리",
    "postCdn2": "우편번호 뒷자리",
    "wgs84Lat": "공공 위도",
    "wgs84Lon": "공공 경도",
    "rnum": "검색 순번",
}
for _day, _label in enumerate(
    ("월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일", "공휴일"), 1
):
    PUBLIC_NAMES[f"dutyTime{_day}s"] = f"{_label} 개점 시각"
    PUBLIC_NAMES[f"dutyTime{_day}c"] = f"{_label} 마감 시각"

DETAIL_NAMES = {
    "latitude": "위도",
    "longitude": "경도",
    "gps_coordinate_system": "좌표계",
    "location_available": "위치정보 제공 여부",
    "opening_hours_available": "운영시간 확인 여부",
    "open_now": "현재 운영 여부",
    "kakao_place_id": "카카오 장소 번호",
    "kakao_details": "카카오 장소 상세정보",
    "opening_hours": "운영시간",
    "opening_schedule": "날짜별 운영시간",
    "opening_hours_updated": "운영시간 갱신 시각",
    "opening_hours_error": "운영시간 조회 오류",
    "opening_hours_source": "운영시간 출처",
    "last_refresh": "마지막 갱신 시각",
    "next_refresh": "다음 갱신 시각",
    "scan_interval_minutes": "갱신 간격",
    "weekly_hours": "요일별 공공 운영시간",
    "coordinate_system": "원본 좌표계",
}
KAKAO_NAMES = {
    "name": "카카오 기관명",
    "confirm_id": "카카오 장소 식별번호",
    "point": "카카오 위치",
    "address": "카카오 주소",
    "road_address": "카카오 도로명주소",
    "phone": "카카오 전화번호",
    "phone_number": "카카오 전화번호",
    "category": "카카오 업종",
    "homepage": "카카오 홈페이지",
}
MEDIA_NAMES = {
    "rating": "카카오 평점",
    "review_count": "카카오 리뷰 수",
    "photo_count": "카카오 사진 수",
    "reviews": "카카오 리뷰 미리보기",
    "photos": "카카오 사진 목록",
    "main_photo": "카카오 대표 사진",
    "place_url": "카카오 장소 링크",
    "reviews_has_more": "카카오 추가 리뷰 있음",
    "reviews_restricted": "카카오 리뷰 조회 제한",
    "photos_restricted": "카카오 사진 조회 제한",
}


def fields(primary):
    """Include missing known fields and discover new response fields after updates."""
    attrs = primary.extra_state_attributes
    record = attrs["api_record"]
    pharmacy = primary.coordinator.service_name == "pharmacy"
    known = {key for key in PUBLIC_NAMES if key[0].islower() == pharmacy}
    result = {
        ("public", key): (
            PUBLIC_NAMES.get(key, f"추가 공공정보 ({key})"),
            record.get(key),
        )
        for key in sorted(known | record.keys())
    }
    for key, label in DETAIL_NAMES.items():
        if key in attrs or key in ("latitude", "longitude"):
            result[("detail", key)] = (label, attrs.get(key))
    for key, value in (attrs.get("kakao_details") or {}).items():
        result[("kakao", key)] = (
            KAKAO_NAMES.get(key, f"카카오 추가정보 ({key})"),
            value,
        )
    media = (primary.coordinator.data or {}).get("_kakao", {}).get("media", {})
    for key, label in MEDIA_NAMES.items():
        result[("media", key)] = (label, media.get(key))
    return result


class MedicalDetailSensor(CoordinatorEntity, SensorEntity):
    """Keep scalar states short while preserving complete structured/long values."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:information-outline"

    def __init__(self, primary, field, label):
        super().__init__(primary.coordinator)
        self.primary = primary
        self.field = field
        self._attr_name = label
        identity = sha256((field[0] + ":" + field[1]).encode()).hexdigest()[:16]
        self._attr_unique_id = f"{primary.unique_id}_detail_{identity}"
        self._attr_device_info = primary.device_info
        if field in DATE_FIELDS:
            self._attr_device_class = SensorDeviceClass.DATE
        if field in TIMESTAMP_FIELDS:
            self._attr_device_class = SensorDeviceClass.TIMESTAMP
        if field[1] in (
            "last_refresh",
            "next_refresh",
            "scan_interval_minutes",
            "opening_hours_error",
            "location_available",
            "opening_hours_available",
            "gps_coordinate_system",
            "coordinate_system",
            "MNG_NO",
            "OPN_ATMY_GRP_CD",
            "hpid",
            "rnum",
        ):
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        if field == ("detail", "scan_interval_minutes"):
            self._attr_native_unit_of_measurement = "min"
            self._attr_device_class = SensorDeviceClass.DURATION

    def _value(self):
        attrs = self.primary.extra_state_attributes
        source, key = self.field
        if source == "public":
            return attrs["api_record"].get(key)
        if source == "kakao":
            return (attrs.get("kakao_details") or {}).get(key)
        if source == "media":
            return (
                (self.coordinator.data or {})
                .get("_kakao", {})
                .get("media", {})
                .get(key)
            )
        return attrs.get(key)

    @property
    def native_value(self):
        value = self._value()
        if value is None or value == "":
            return None
        if self.field in DATE_FIELDS:
            try:
                return date.fromisoformat(str(value).strip())
            except ValueError:
                return None
        if self.field in TIMESTAMP_FIELDS:
            try:
                stamp = (
                    value
                    if isinstance(value, datetime)
                    else dt_util.parse_datetime(str(value))
                )
            except ValueError:
                return None
            if stamp is None:
                return None
            return stamp if stamp.tzinfo else stamp.replace(tzinfo=SEOUL)
        if isinstance(value, bool):
            return "예" if value else "아니요"
        if isinstance(value, (dict, list)):
            return "정보 있음" if value else None
        if self.field == ("detail", "opening_hours_source") and value == "kakao":
            return "카카오맵"
        if isinstance(value, str) and len(value) > 255:
            return value[:254] + "…"
        return value

    @property
    def extra_state_attributes(self):
        return {"source": self.field[0], "field": self.field[1], "value": self._value()}

    @property
    def entity_picture(self):
        if self.field == ("media", "main_photo"):
            from .media import photo_url

            return photo_url(self._value())
        return None

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        if self.field in (
            ("detail", "open_now"),
            ("detail", "opening_hours_available"),
        ):
            self.async_on_remove(
                async_track_time_change(self.hass, self._async_clock_tick, second=0)
            )

    @callback
    def _async_clock_tick(self, _now):
        self.async_write_ha_state()


def setup_medical_sensors(entry, async_add_entities, primary):
    """Add initial entities and discover new optional fields on future API updates."""
    from .schedule_sensor import MedicalTransitionSensor

    seen = set()

    @callback
    def discover(initial=False):
        new = (
            [
                primary,
                MedicalTransitionSensor(primary, "start"),
                MedicalTransitionSensor(primary, "end"),
            ]
            if initial
            else []
        )
        for field, (label, _) in fields(primary).items():
            if field not in seen:
                seen.add(field)
                new.append(MedicalDetailSensor(primary, field, label))
        if new:
            async_add_entities(new)

    discover(initial=True)
    entry.async_on_unload(primary.coordinator.async_add_listener(discover))
