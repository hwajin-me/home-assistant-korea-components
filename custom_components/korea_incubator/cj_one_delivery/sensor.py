"""CJ O-NE delivery sensors."""

from __future__ import annotations

import re
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import DeliveryStatus
from .const import (
    COMPLETED_COUNT_RETENTION_DAYS,
    COMPLETED_SENSOR_RETENTION_DAYS,
    DOMAIN,
)
from .coordinator import CJOneDeliveryCoordinator, DeliveryEvent

_LEGACY_SLOT_UNIQUE_ID = re.compile(r"_(?:active|completed)_\d+_")
_EVENT_TYPES = ["none", "new_delivery", "status_changed", "tracking_updated"]
_EVENT_LABELS = {
    "none": "이벤트 없음",
    "new_delivery": "새 배송",
    "status_changed": "배송 상태 변경",
    "tracking_updated": "배송 정보 갱신",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[CJOneDeliveryCoordinator],
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up one sensor per active or recently completed parcel."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    _remove_legacy_slot_entries(hass, entry)

    initial_statuses = _parcel_statuses(coordinator)
    desired_tracking_numbers = {status.tracking_number for status in initial_statuses}
    _remove_stale_parcel_entries(hass, entry, desired_tracking_numbers)
    parcel_entities = {
        status.tracking_number: CJOneDeliveryParcelSensor(coordinator, status)
        for status in initial_statuses
    }
    async_add_entities(
        [
            CJOneDeliverySummarySensor(coordinator),
            CJOneDeliveryDeliveryListSensor(coordinator),
            CJOneDeliveryCompletedCounterSensor(coordinator),
            *parcel_entities.values(),
            CJOneDeliveryLastEventSensor(coordinator),
        ]
    )

    def _sync_parcel_sensors() -> None:
        desired_statuses = {
            status.tracking_number: status for status in _parcel_statuses(coordinator)
        }
        for tracking_number in parcel_entities.keys() - desired_statuses.keys():
            entity = parcel_entities.pop(tracking_number)
            hass.async_create_task(
                _async_remove_parcel_entity(hass, entity),
                f"Remove expired CJ parcel sensor {tracking_number}",
            )

        new_statuses = [
            status
            for tracking_number, status in desired_statuses.items()
            if tracking_number not in parcel_entities
        ]
        if not new_statuses:
            return
        new_entities = [
            CJOneDeliveryParcelSensor(coordinator, status) for status in new_statuses
        ]
        parcel_entities.update(
            {entity.tracking_number: entity for entity in new_entities}
        )
        async_add_entities(new_entities)

    entry.async_on_unload(coordinator.async_add_listener(_sync_parcel_sensors))


class CJOneDeliverySummarySensor(
    CoordinatorEntity[CJOneDeliveryCoordinator], SensorEntity
):
    """Overall delivery summary."""

    _attr_has_entity_name = True
    _attr_name = "배송 요약"

    def __init__(self, coordinator: CJOneDeliveryCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_summary"
        self._attr_device_info = _device_info(coordinator)

    @property
    def native_value(self) -> str:
        return f"배송대기/배송중 {len(self.coordinator.active_statuses)}건"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        last_event = self.coordinator.last_event
        return {
            "active_count": len(self.coordinator.active_statuses),
            "completed_2day_sensor_count": len(
                self.coordinator.completed_sensor_statuses
            ),
            "completed_5day_count": len(self.coordinator.completed_statuses),
            "completed_sensor_retention_days": COMPLETED_SENSOR_RETENTION_DAYS,
            "completed_count_retention_days": COMPLETED_COUNT_RETENTION_DAYS,
            "last_changed_summary": last_event.announcement if last_event else "",
            "last_error": self.coordinator.last_error or "",
        }


class CJOneDeliveryDeliveryListSensor(
    CoordinatorEntity[CJOneDeliveryCoordinator], SensorEntity
):
    """Aggregate list of every scheduled or in-transit parcel."""

    _attr_has_entity_name = True
    _attr_name = "배송대기/배송중 목록"

    def __init__(self, coordinator: CJOneDeliveryCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_active"
        self._attr_device_info = _device_info(coordinator)

    @property
    def native_value(self) -> int:
        return len(self.coordinator.active_statuses)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "deliveries": [
                _delivery_summary_payload(status)
                for status in self.coordinator.active_statuses
            ],
            "last_error": self.coordinator.last_error or "",
        }


class CJOneDeliveryCompletedCounterSensor(
    CoordinatorEntity[CJOneDeliveryCoordinator], SensorEntity
):
    """Count deliveries completed during the rolling five-day window."""

    _attr_has_entity_name = True
    _attr_name = "최근 5일 배송완료"
    _attr_icon = "mdi:package-variant-closed-check"
    _attr_native_unit_of_measurement = "건"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: CJOneDeliveryCoordinator) -> None:
        super().__init__(coordinator)
        # Preserve the former unique ID so existing dashboards keep the same entity.
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_completed_2day"
        self._attr_device_info = _device_info(coordinator)

    @property
    def native_value(self) -> int:
        return len(self.coordinator.completed_statuses)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "retention_days": COMPLETED_COUNT_RETENTION_DAYS,
            "deliveries": [
                _delivery_summary_payload(status)
                for status in self.coordinator.completed_statuses
            ],
            "last_error": self.coordinator.last_error or "",
        }


class CJOneDeliveryParcelSensor(
    CoordinatorEntity[CJOneDeliveryCoordinator], SensorEntity
):
    """A single parcel whose attributes contain every available detail."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:package-variant"

    def __init__(
        self, coordinator: CJOneDeliveryCoordinator, initial_status: DeliveryStatus
    ) -> None:
        super().__init__(coordinator)
        self._tracking_number = initial_status.tracking_number
        tracking_display = _format_tracking_number(self._tracking_number)
        self._attr_name = initial_status.status_detail or tracking_display or "택배"
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_parcel_{self._tracking_number}"
        )
        self._attr_device_info = _device_info(coordinator)

    @property
    def available(self) -> bool:
        status = self._status
        return (
            super().available
            and status is not None
            and (
                status.display_group == "진행중"
                or any(
                    completed.tracking_number == self._tracking_number
                    for completed in self.coordinator.completed_sensor_statuses
                )
            )
        )

    @property
    def native_value(self) -> str | None:
        status = self._status
        return status.status if status is not None else None

    @property
    def tracking_number(self) -> str:
        """Return the parcel tracking number used by the lifecycle manager."""
        return self._tracking_number

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        status = self._status
        if status is None:
            return {"tracking_number": self._tracking_number}
        return _delivery_payload(status)

    @property
    def _status(self) -> DeliveryStatus | None:
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get(self._tracking_number)


class CJOneDeliveryLastEventSensor(
    CoordinatorEntity[CJOneDeliveryCoordinator], SensorEntity
):
    """Latest delivery change event for automations and announcements."""

    _attr_has_entity_name = True
    _attr_name = "최근 배송 이벤트"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = _EVENT_TYPES

    def __init__(self, coordinator: CJOneDeliveryCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_last_event"
        self._attr_device_info = _device_info(coordinator)

    @property
    def native_value(self) -> str:
        event = self.coordinator.last_event
        return event.event_type if event else "none"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        event = self.coordinator.last_event
        if event is None:
            return {
                "event_type": "none",
                "event_label": _EVENT_LABELS["none"],
                "tracking_number": "",
                "tracking_number_display": "",
                "product_name": "",
                "status": "",
                "status_key": "unknown",
                "status_label": "",
                "status_code": "",
                "previous_status": "",
                "previous_status_key": "",
                "previous_status_label": "",
                "previous_status_code": "",
                "status_message": "",
                "display_group": "",
                "location": "",
                "event_time": "",
                "courier_name": "",
                "estimated_delivery_time": "",
                "is_return": False,
                "announcement": "",
            }
        return _event_payload(event)


def _delivery_payload(status: DeliveryStatus) -> dict[str, Any]:
    basic_info = status.basic_info or {}
    return {
        "tracking_number": status.tracking_number,
        "tracking_number_display": _format_tracking_number(status.tracking_number),
        "status": status.status,
        "status_code": status.status_code or "",
        "status_message": status.status_message or "",
        "display_group": status.display_group,
        "product_name": status.status_detail or "",
        "sender": status.sender or basic_info.get("보내는 분", ""),
        "sender_phone": status.sender_phone or "",
        "receiver": status.receiver or basic_info.get("받는 분", ""),
        "receiver_phone": status.receiver_phone or "",
        "receiver_area": status.receiver_area or "",
        "registered_at": status.registered_at or "",
        "last_location": status.last_location or "",
        "last_event_time": status.last_event_time or "",
        "courier": basic_info.get("배송기사", ""),
        "courier_name": status.courier_name or "",
        "courier_phone": status.courier_phone or "",
        "delivery_branch": status.delivery_branch or "",
        "delivery_branch_phone": status.delivery_branch_phone or "",
        "upstream_branch": status.upstream_branch or "",
        "estimated_delivery_time": status.estimated_delivery_time or "",
        "fare_type": status.fare_type or "",
        "fare_amount": status.fare_amount or "",
        "is_return": status.is_return,
        "original_tracking_number": status.original_tracking_number or "",
        "delivery_type_code": status.delivery_type_code or "",
        "parcel_type_code": status.parcel_type_code or "",
        "recipient_relation": status.recipient_relation or "",
        "completion_message": status.completion_message or "",
        "delivery_proof_path": status.delivery_proof_path or "",
        "payment_required": status.payment_required,
        "is_reaccepted": status.is_reaccepted,
        "tracking_url": (
            "https://trace.cjlogistics.com/next/tracking.html?wblNo="
            f"{status.tracking_number}"
        ),
        "basic_info": basic_info,
        "tracking_history": status.tracking_history or [],
        "raw_data": status.raw or {},
    }


def _parcel_statuses(
    coordinator: CJOneDeliveryCoordinator,
) -> list[DeliveryStatus]:
    """Return active and recently completed parcels that need entities."""
    return [*coordinator.active_statuses, *coordinator.completed_sensor_statuses]


def _delivery_summary_payload(status: DeliveryStatus) -> dict[str, Any]:
    return {
        "tracking_number": status.tracking_number,
        "tracking_number_display": _format_tracking_number(status.tracking_number),
        "status": status.status,
        "status_code": status.status_code or "",
        "status_message": status.status_message or "",
        "product_name": status.status_detail or "",
        "sender": status.sender or "",
        "receiver": status.receiver or "",
        "last_location": status.last_location or "",
        "last_event_time": status.last_event_time or "",
        "courier": (status.basic_info or {}).get("배송기사", ""),
        "estimated_delivery_time": status.estimated_delivery_time or "",
        "is_return": status.is_return,
        "recipient_relation": status.recipient_relation or "",
        "completion_message": status.completion_message or "",
        "delivery_proof_path": status.delivery_proof_path or "",
    }


def _event_payload(event: DeliveryEvent) -> dict[str, Any]:
    return {
        "event_type": event.event_type,
        "event_label": _EVENT_LABELS[event.event_type],
        "tracking_number": event.tracking_number,
        "tracking_number_display": _format_tracking_number(event.tracking_number),
        "product_name": event.product_name or "",
        "status": event.status,
        "status_key": event.status_key,
        "status_label": event.status_label,
        "status_code": event.status_code or "",
        "previous_status": event.previous_status or "",
        "previous_status_key": event.previous_status_key or "",
        "previous_status_label": event.previous_status_label or "",
        "previous_status_code": event.previous_status_code or "",
        "status_message": event.status_message or "",
        "display_group": event.display_group,
        "location": event.location or "",
        "event_time": event.event_time or "",
        "courier_name": event.courier_name or "",
        "estimated_delivery_time": event.estimated_delivery_time or "",
        "is_return": event.is_return,
        "announcement": event.announcement,
    }


def _format_tracking_number(tracking_number: str) -> str:
    digits = "".join(char for char in tracking_number if char.isdigit())
    return "-".join(digits[index : index + 4] for index in range(0, len(digits), 4))


def _remove_legacy_slot_entries(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove entities and devices created by the former slot model."""
    entity_registry = er.async_get(hass)
    for entity_entry in er.async_entries_for_config_entry(
        entity_registry, entry.entry_id
    ):
        if (
            entity_entry.domain == "sensor"
            and entity_entry.platform == DOMAIN
            and _LEGACY_SLOT_UNIQUE_ID.search(entity_entry.unique_id)
        ):
            entity_registry.async_remove(entity_entry.entity_id)

    device_registry = dr.async_get(hass)
    for device_entry in dr.async_entries_for_config_entry(
        device_registry, entry.entry_id
    ):
        if any(
            identifier_domain == DOMAIN
            and re.fullmatch(
                rf"{re.escape(entry.entry_id)}_(?:active|completed)_\d+",
                identifier,
            )
            for identifier_domain, identifier in device_entry.identifiers
        ):
            device_registry.async_remove_device(device_entry.id)


def _remove_stale_parcel_entries(
    hass: HomeAssistant,
    entry: ConfigEntry,
    desired_tracking_numbers: set[str],
) -> None:
    """Remove parcel registry entries that are outside the two-day display window."""
    entity_registry = er.async_get(hass)
    unique_id_prefix = f"{entry.entry_id}_parcel_"
    for entity_entry in er.async_entries_for_config_entry(
        entity_registry, entry.entry_id
    ):
        if (
            entity_entry.domain != "sensor"
            or entity_entry.platform != DOMAIN
            or not entity_entry.unique_id.startswith(unique_id_prefix)
        ):
            continue
        tracking_number = entity_entry.unique_id.removeprefix(unique_id_prefix)
        if tracking_number in desired_tracking_numbers:
            continue
        hass.states.async_remove(entity_entry.entity_id)
        entity_registry.async_remove(entity_entry.entity_id)


async def _async_remove_parcel_entity(
    hass: HomeAssistant,
    entity: CJOneDeliveryParcelSensor,
) -> None:
    """Remove an expired parcel from both the state machine and entity registry."""
    entity_id = entity.entity_id
    await entity.async_remove(force_remove=True)
    if entity_id:
        er.async_get(hass).async_remove(entity_id)


def _device_info(coordinator: CJOneDeliveryCoordinator) -> dict[str, Any]:
    return {
        "identifiers": {(DOMAIN, coordinator.config_entry.entry_id)},
        "name": "CJ O-NE 배송조회",
        "manufacturer": "CJ Logistics",
        "model": "배송조회",
        "configuration_url": "https://www.cjlogistics.com/ko/tool/parcel/tracking",
    }
