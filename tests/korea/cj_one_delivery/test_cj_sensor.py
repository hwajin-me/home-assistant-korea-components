"""Tests for CJ O-NE per-parcel sensors and completed counter."""

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.korea_incubator.cj_one_delivery.sensor import (
    CJOneDeliveryCompletedCounterSensor,
    CJOneDeliveryLastEventSensor,
    CJOneDeliveryParcelSensor,
    _async_remove_parcel_entity,
    _remove_stale_parcel_entries,
    async_setup_entry,
)
from custom_components.korea_incubator.cj_one_delivery.coordinator import (
    _event_from_status_change,
)


@dataclass
class _Status:
    tracking_number: str
    status: str = "상품이동중"
    status_detail: str | None = "테스트 상품"
    sender: str | None = "보내는 분"
    receiver: str | None = "받는 분"
    last_location: str | None = "대전Hub"
    last_event_time: str | None = "2026-08-06 12:00:00"
    status_code: str | None = "82"
    status_message: str | None = "배송 출발하였습니다."
    sender_phone: str | None = "02-1234-****"
    receiver_phone: str | None = "010-1234-****"
    receiver_area: str | None = "이태원동"
    registered_at: str | None = "2026-08-06 09:00:00.0"
    courier_name: str | None = "홍길동"
    courier_phone: str | None = "010-0000-0000"
    delivery_branch: str | None = "서울용산랜드마크"
    delivery_branch_phone: str | None = "02-000-0000"
    upstream_branch: str | None = "용산지사"
    estimated_delivery_time: str | None = "20~22시"
    fare_type: str | None = "선불"
    fare_amount: str | None = "1750"
    is_return: bool = False
    original_tracking_number: str | None = "123456789012"
    delivery_type_code: str | None = "02"
    parcel_type_code: str | None = "01"
    recipient_relation: str | None = "본인"
    completion_message: str | None = "배송완료 되었습니다."
    delivery_proof_path: str | None = "/service/delivery-proof.jpg"
    payment_required: bool = True
    is_reaccepted: bool = False
    display_group: str = "진행중"
    basic_info: dict | None = None
    tracking_history: list | None = None
    raw: dict | None = None


@pytest.mark.asyncio
async def test_one_sensor_per_active_parcel_and_dynamic_growth() -> None:
    statuses = [_Status(str(index)) for index in range(4)]
    coordinator = MagicMock()
    coordinator.active_statuses = statuses
    coordinator.completed_sensor_statuses = [
        _Status("completed", status="배송완료", display_group="배송완료")
    ]
    coordinator.completed_statuses = []
    coordinator.data = {
        status.tracking_number: status
        for status in [*statuses, *coordinator.completed_sensor_statuses]
    }
    coordinator.last_event = None
    coordinator.last_error = None
    coordinator.config_entry.entry_id = "entry"
    listeners = []
    coordinator.async_add_listener.side_effect = lambda listener: (
        listeners.append(listener) or MagicMock()
    )

    entry = MagicMock()
    entry.entry_id = "entry"
    entry.options = {"scan_interval_minutes": 30}
    hass = MagicMock()
    hass.data = {"korea_incubator": {"entry": {"coordinator": coordinator}}}
    batches = []

    with (
        patch("custom_components.korea_incubator.cj_one_delivery.sensor.er.async_get"),
        patch(
            "custom_components.korea_incubator.cj_one_delivery.sensor.er.async_entries_for_config_entry",
            return_value=[],
        ),
        patch("custom_components.korea_incubator.cj_one_delivery.sensor.dr.async_get"),
        patch(
            "custom_components.korea_incubator.cj_one_delivery.sensor.dr.async_entries_for_config_entry",
            return_value=[],
        ),
    ):
        await async_setup_entry(hass, entry, batches.append)

    parcel_sensors = [
        entity for entity in batches[0] if isinstance(entity, CJOneDeliveryParcelSensor)
    ]
    assert len(parcel_sensors) == 5

    new_status = _Status("5")
    coordinator.active_statuses.append(new_status)
    coordinator.data[new_status.tracking_number] = new_status
    listeners[0]()

    assert len(batches[1]) == 1
    assert isinstance(batches[1][0], CJOneDeliveryParcelSensor)


def test_parcel_sensor_contains_all_delivery_attributes() -> None:
    status = _Status(
        "123456789012",
        basic_info={"배송기사": "홍길동(010-0000-0000)", "운임구분": "선불"},
        tracking_history=[{"상태": "집화처리", "위치": "서울"}],
        raw={"TRSPBILLNUM": "123456789012", "SCNDIVCD": "30"},
    )
    coordinator = MagicMock()
    coordinator.config_entry.entry_id = "entry"
    coordinator.data = {status.tracking_number: status}
    coordinator.last_update_success = True

    sensor = CJOneDeliveryParcelSensor(coordinator, status)
    attributes = sensor.extra_state_attributes

    assert sensor.native_value == "상품이동중"
    assert attributes["tracking_number"] == "123456789012"
    assert attributes["sender"] == "보내는 분"
    assert attributes["receiver"] == "받는 분"
    assert attributes["courier"] == "홍길동(010-0000-0000)"
    assert attributes["status_code"] == "82"
    assert attributes["status_message"] == "배송 출발하였습니다."
    assert attributes["receiver_area"] == "이태원동"
    assert attributes["courier_name"] == "홍길동"
    assert attributes["estimated_delivery_time"] == "20~22시"
    assert attributes["fare_amount"] == "1750"
    assert attributes["tracking_url"].endswith("123456789012")
    assert attributes["recipient_relation"] == "본인"
    assert attributes["delivery_proof_path"] == "/service/delivery-proof.jpg"
    assert attributes["payment_required"] is True
    assert attributes["tracking_history"][0]["상태"] == "집화처리"
    assert attributes["raw_data"]["SCNDIVCD"] == "30"


def test_completed_counter_uses_recent_completed_statuses() -> None:
    coordinator = MagicMock()
    coordinator.config_entry.entry_id = "entry"
    coordinator.completed_statuses = [
        _Status("1", status="배송완료", display_group="배송완료"),
        _Status("2", status="배송완료", display_group="배송완료"),
    ]
    coordinator.last_error = None

    sensor = CJOneDeliveryCompletedCounterSensor(coordinator)

    assert sensor.native_value == 2
    assert sensor.extra_state_attributes["retention_days"] == 5
    assert len(sensor.extra_state_attributes["deliveries"]) == 2


def test_recent_completed_parcel_sensor_remains_available() -> None:
    status = _Status("completed", status="배송완료", display_group="배송완료")
    coordinator = MagicMock()
    coordinator.config_entry.entry_id = "entry"
    coordinator.data = {status.tracking_number: status}
    coordinator.completed_sensor_statuses = [status]
    coordinator.last_update_success = True

    sensor = CJOneDeliveryParcelSensor(coordinator, status)

    assert sensor.available is True
    assert sensor.native_value == "배송완료"

    coordinator.completed_sensor_statuses = []
    assert sensor.available is False


@pytest.mark.asyncio
async def test_expired_parcel_entity_is_removed_instead_of_unavailable() -> None:
    hass = MagicMock()
    entity = MagicMock(spec=CJOneDeliveryParcelSensor)
    entity.entity_id = "sensor.expired_parcel"
    entity.async_remove = AsyncMock()
    registry = MagicMock()

    with patch(
        "custom_components.korea_incubator.cj_one_delivery.sensor.er.async_get",
        return_value=registry,
    ):
        await _async_remove_parcel_entity(hass, entity)

    entity.async_remove.assert_awaited_once_with(force_remove=True)
    registry.async_remove.assert_called_once_with("sensor.expired_parcel")


def test_stale_parcel_registry_entry_is_removed_during_setup() -> None:
    hass = MagicMock()
    entry = MagicMock(entry_id="entry")
    registry = MagicMock()
    current = MagicMock(
        domain="sensor",
        platform="korea_incubator",
        unique_id="entry_parcel_current",
        entity_id="sensor.current_parcel",
    )
    expired = MagicMock(
        domain="sensor",
        platform="korea_incubator",
        unique_id="entry_parcel_expired",
        entity_id="sensor.expired_parcel",
    )

    with (
        patch(
            "custom_components.korea_incubator.cj_one_delivery.sensor.er.async_get",
            return_value=registry,
        ),
        patch(
            "custom_components.korea_incubator.cj_one_delivery.sensor.er.async_entries_for_config_entry",
            return_value=[current, expired],
        ),
    ):
        _remove_stale_parcel_entries(hass, entry, {"current"})

    hass.states.async_remove.assert_called_once_with("sensor.expired_parcel")
    registry.async_remove.assert_called_once_with("sensor.expired_parcel")


def test_last_event_sensor_uses_normalized_enum_state_and_attributes() -> None:
    previous = _Status(
        "123456789012",
        status="상품이동중",
        status_code="42",
        last_location="곤지암Hub",
        last_event_time="2026-08-07 10:00:00",
    )
    current = _Status(
        "123456789012",
        status="배달출발",
        status_code="82",
        status_message="배송 출발하였습니다.",
        last_location="서울용산랜드마크",
        last_event_time="2026-08-07 12:00:00",
    )
    event = _event_from_status_change(
        current.tracking_number,
        previous=previous,
        current=current,
    )
    coordinator = MagicMock()
    coordinator.config_entry.entry_id = "entry"
    coordinator.last_event = event

    sensor = CJOneDeliveryLastEventSensor(coordinator)
    attributes = sensor.extra_state_attributes

    assert sensor.native_value == "status_changed"
    assert attributes["event_label"] == "배송 상태 변경"
    assert attributes["status_key"] == "out_for_delivery"
    assert attributes["status_label"] == "배송출발"
    assert attributes["status_code"] == "82"
    assert attributes["previous_status_key"] == "in_transit"
    assert attributes["tracking_number_display"] == "1234-5678-9012"
    assert attributes["announcement"]
