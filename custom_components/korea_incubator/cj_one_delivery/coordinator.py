"""CJ O-NE 배송조회 데이터 코디네이터."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import CJOneDeliveryClient, DeliveryStatus
from .const import (
    COMPLETED_SENSOR_RETENTION_DAYS,
    CONF_SCAN_INTERVAL_MINUTES,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
    MAX_SCAN_INTERVAL_MINUTES,
    MIN_SCAN_INTERVAL_MINUTES,
)
from ..const import TZ_ASIA_SEOUL
from .exceptions import CJOneDeliveryError, InvalidAuth

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class DeliveryEvent:
    """배송 상태 변경 자동화에 사용할 최근 이벤트."""

    event_type: str
    tracking_number: str
    status: str
    status_key: str
    status_label: str
    status_code: str | None
    previous_status: str | None
    previous_status_key: str | None
    previous_status_label: str | None
    previous_status_code: str | None
    status_message: str | None
    display_group: str
    location: str | None
    event_time: str | None
    product_name: str | None
    courier_name: str | None
    estimated_delivery_time: str | None
    is_return: bool
    announcement: str


class CJOneDeliveryCoordinator(DataUpdateCoordinator[dict[str, DeliveryStatus]]):
    """배송상태를 가져와 캐시에 보관합니다."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: CJOneDeliveryClient,
    ) -> None:
        """코디네이터를 초기화합니다."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=_scan_interval(entry),
        )
        self.client = client
        self.last_error: str | None = None
        self.last_event: DeliveryEvent | None = None
        self.active_statuses: list[DeliveryStatus] = []
        self.completed_sensor_statuses: list[DeliveryStatus] = []
        self.completed_statuses: list[DeliveryStatus] = []
        self.loaded_options = dict(entry.options)

    async def _async_update_data(self) -> dict[str, DeliveryStatus]:
        """앱 API에서 최신 데이터를 가져옵니다."""
        try:
            data = await self.client.async_get_delivery_statuses()
        except InvalidAuth as err:
            self.last_error = str(err)
            raise ConfigEntryAuthFailed(str(err)) from err
        except CJOneDeliveryError as err:
            self.last_error = str(err)
            raise UpdateFailed(f"CJ O-NE 배송 목록 조회 실패: {err}") from err

        self.last_error = None
        self._update_last_event(data)
        self.active_statuses = _active_statuses(data.values())
        self.completed_sensor_statuses = _completed_sensor_statuses(data.values())
        self.completed_statuses = _completed_statuses(data.values())
        return data

    def apply_options(self) -> None:
        """옵션 변경사항을 코디네이터에 반영합니다."""
        self.loaded_options = dict(self.config_entry.options)
        self.update_interval = _scan_interval(self.config_entry)

    def _update_last_event(self, data: dict[str, DeliveryStatus]) -> None:
        """이전 조회 데이터와 비교해 최근 배송 변경 이벤트를 갱신합니다."""
        if self.data is None:
            return

        events: list[DeliveryEvent] = []
        for tracking_number, status in data.items():
            event = _event_from_status_change(
                tracking_number,
                previous=self.data.get(tracking_number),
                current=status,
            )
            if event is not None:
                events.append(event)
        if not events:
            return

        self.last_event = sorted(
            events,
            key=lambda event: event.event_time or "",
            reverse=True,
        )[0]


def _event_from_status_change(
    tracking_number: str,
    *,
    previous: DeliveryStatus | None,
    current: DeliveryStatus,
) -> DeliveryEvent | None:
    """배송 상태 변경 여부를 판단하고 자동화용 이벤트를 만듭니다."""
    status_key, status_label = _normalized_status(current)
    if previous is None:
        return DeliveryEvent(
            event_type="new_delivery",
            tracking_number=tracking_number,
            status=current.status,
            status_key=status_key,
            status_label=status_label,
            status_code=current.status_code,
            previous_status=None,
            previous_status_key=None,
            previous_status_label=None,
            previous_status_code=None,
            status_message=current.status_message,
            display_group=current.display_group,
            location=current.last_location,
            event_time=current.last_event_time,
            product_name=current.status_detail,
            courier_name=current.courier_name,
            estimated_delivery_time=current.estimated_delivery_time,
            is_return=current.is_return,
            announcement=_announcement("new_delivery", current),
        )

    if _status_signature(previous) == _status_signature(current):
        return None

    previous_status_key, previous_status_label = _normalized_status(previous)
    event_type = (
        "status_changed"
        if previous.status != current.status
        or previous.status_code != current.status_code
        else "tracking_updated"
    )
    return DeliveryEvent(
        event_type=event_type,
        tracking_number=tracking_number,
        status=current.status,
        status_key=status_key,
        status_label=status_label,
        status_code=current.status_code,
        previous_status=previous.status,
        previous_status_key=previous_status_key,
        previous_status_label=previous_status_label,
        previous_status_code=previous.status_code,
        status_message=current.status_message,
        display_group=current.display_group,
        location=current.last_location,
        event_time=current.last_event_time,
        product_name=current.status_detail,
        courier_name=current.courier_name,
        estimated_delivery_time=current.estimated_delivery_time,
        is_return=current.is_return,
        announcement=_announcement(event_type, current),
    )


def _status_signature(
    status: DeliveryStatus,
) -> tuple[str, str | None, str | None, str | None]:
    """배송 변경 감지에 사용할 안정적인 비교값을 반환합니다."""
    return (
        status.status,
        status.status_code,
        status.last_location,
        status.last_event_time,
    )


def _normalized_status(status: DeliveryStatus) -> tuple[str, str]:
    """Convert CJ status codes and labels to stable automation values."""
    code = status.status_code or ""
    if code in {"01", "12", "13"}:
        return "scheduled", "배송대기"
    if code in {
        "11",
        "30",
        "41",
        "42",
        "43",
        "9927",
        "9928",
        "9929",
        "9933",
        "9936",
    }:
        return "in_transit", "배송중"
    if code in {"82", "83", "84"}:
        return "out_for_delivery", "배송출발"
    if code == "91":
        return "delivered", "배송완료"

    raw_status = status.status.replace(" ", "")
    if raw_status in {"상품준비", "배송예약", "배송대기"}:
        return "scheduled", "배송대기"
    if raw_status in {
        "집화출발",
        "집화처리",
        "간선상차",
        "간선하차",
        "상품이동중",
        "배송중",
        "국제택배항공",
        "국제택배세관",
    }:
        return "in_transit", "배송중"
    if raw_status in {"배달출발", "배송출발"}:
        return "out_for_delivery", "배송출발"
    if raw_status in {"배달완료", "배송완료"}:
        return "delivered", "배송완료"
    return "unknown", status.status or "상태 확인"


def _announcement(event_type: str, status: DeliveryStatus) -> str:
    """구글 스피커 방송에 사용할 기본 문장을 만듭니다."""
    product_name = status.status_detail or "택배"
    location = f"{status.last_location}에서 " if status.last_location else ""
    if event_type == "new_delivery":
        return f"{product_name} 배송이 새로 확인되었습니다. 현재 {location}{status.status} 상태입니다."
    return f"{product_name} 배송이 {location}{status.status} 상태로 변경되었습니다."


def _active_statuses(statuses: Iterable[DeliveryStatus]) -> list[DeliveryStatus]:
    """진행중 배송 목록을 최근 일시순으로 반환합니다."""
    active = [status for status in statuses if status.display_group == "진행중"]
    return sorted(active, key=lambda status: status.last_event_time or "", reverse=True)


def _completed_statuses(
    statuses: Iterable[DeliveryStatus],
) -> list[DeliveryStatus]:
    """Return all completed deliveries retained by the API client."""
    completed = [status for status in statuses if status.display_group == "배송완료"]
    return sorted(
        completed,
        key=lambda status: status.last_event_time or "",
        reverse=True,
    )


def _completed_sensor_statuses(
    statuses: Iterable[DeliveryStatus],
    *,
    now: datetime | None = None,
) -> list[DeliveryStatus]:
    """Return completed deliveries that should retain an individual sensor."""
    current_time = now or datetime.now(TZ_ASIA_SEOUL)
    if current_time.tzinfo is None:
        current_time = TZ_ASIA_SEOUL.localize(current_time)
    cutoff = current_time - timedelta(days=COMPLETED_SENSOR_RETENTION_DAYS)

    completed: list[DeliveryStatus] = []
    for status in statuses:
        if status.display_group != "배송완료" or not status.last_event_time:
            continue
        try:
            completed_at = datetime.fromisoformat(status.last_event_time)
        except ValueError:
            continue
        if completed_at.tzinfo is None:
            completed_at = TZ_ASIA_SEOUL.localize(completed_at)
        if cutoff <= completed_at <= current_time:
            completed.append(status)

    return sorted(
        completed,
        key=lambda status: status.last_event_time or "",
        reverse=True,
    )


def _scan_interval(entry: ConfigEntry) -> timedelta:
    """설정된 조회 주기를 반환합니다."""
    configured_minutes = int(
        entry.options.get(CONF_SCAN_INTERVAL_MINUTES, DEFAULT_SCAN_INTERVAL_MINUTES)
    )
    minutes = min(
        MAX_SCAN_INTERVAL_MINUTES,
        max(MIN_SCAN_INTERVAL_MINUTES, configured_minutes),
    )
    return timedelta(minutes=minutes)
