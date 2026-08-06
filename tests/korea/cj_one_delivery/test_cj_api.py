"""Tests for CJ O-NE API list handling and normalization."""

from datetime import datetime
from unittest.mock import AsyncMock

import pytest
import pytz

from custom_components.korea_incubator.cj_one_delivery.api import (
    CJOneDeliveryClient,
    _delivery_status_from_row,
    _filter_display_rows,
    _kisa_decrypt,
    _kisa_encrypt,
)


def test_live_response_fields_are_normalized_into_attributes() -> None:
    row = {
        "TRSPBILLNUM": "522447137781",
        "OGNTRSPBILLNUM": "522447137781",
        "SCNDIVNM": "배달출발",
        "SCNDIVCD": "82",
        "SKUNM": "테스트 상품",
        "SNDPRSNNM": "보*",
        "RCVRNM": "받*",
        "DONG": "이태원동",
        "REGDT": "2026-08-06 00:20:44.0",
        "RETURNYN": "Y",
        "DLV_DIV_CD": "02",
        "PRNGDIVCD": "01",
        "PAYREQDVYN": "Y",
    }
    detail = {
        "TRSPBILLNUM": "522447137781",
        "SNDPRSNTELNUM": "032-572-****",
        "RCVRTELNUM": "010-2367-****",
        "FAREDIV": "03",
        "TOT_FARE": "1750",
        "REACPTYN": "Y",
        "SAVEURL": "/service/delivery-proof.jpg",
        "TKVRUSRRLTN": "고객님의 상품이 배송완료 되었습니다.",
        "list": [
            {
                "SCNDIVNM": "배송출발",
                "SKUSTSCD": "82",
                "WRKDT": "20260806",
                "WRKHR": "124133",
                "BRANNM": "서울용산랜드마크",
                "UPBRANNM": "용산지사",
                "FCNGTELNUM": "02-749-4212",
                "DLVMSG": "\t 배송 출발하였습니다. ",
                "EMPNM": "홍길동",
                "CLPHNUM": "010-1234-5678",
                "EMPBRANCD": "9568",
                "MBAGTRSPBILLNUM": "20~22시",
                "TKVRUSRNM": "본인",
                "EMPNUM": "712234",
            },
            {
                "SCNDIVNM": "간선상차",
                "SKUSTSCD": "41",
                "WRKDT": "20260806",
                "WRKHR": "042848",
                "BRANNM": "안성MPHub",
                "VHCNUM": "서울88아8731",
                "MBAGTRSPBILLNUM": "795317331843",
            },
        ],
    }

    status = _delivery_status_from_row(row, detail)

    assert status.status_code == "82"
    assert status.status_message == "배송 출발하였습니다."
    assert status.sender_phone == "032-572-****"
    assert status.receiver_phone == "010-2367-****"
    assert status.receiver_area == "이태원동"
    assert status.registered_at == "2026-08-06 00:20:44.0"
    assert status.courier_name == "홍길동"
    assert status.courier_phone == "010-1234-5678"
    assert status.delivery_branch == "서울용산랜드마크"
    assert status.upstream_branch == "용산지사"
    assert status.estimated_delivery_time == "20~22시"
    assert status.fare_type == "신용"
    assert status.fare_amount == "1750"
    assert status.is_return is True
    assert status.delivery_type_code == "02"
    assert status.parcel_type_code == "01"
    assert status.recipient_relation == "본인"
    assert status.completion_message == "고객님의 상품이 배송완료 되었습니다."
    assert status.delivery_proof_path == "/service/delivery-proof.jpg"
    assert status.payment_required is True
    assert status.is_reaccepted is True
    assert status.basic_info["반품 여부"] == "예"
    assert status.tracking_history[0]["점소코드"] == "9568"
    assert status.tracking_history[0]["수령인 관계"] == "본인"
    assert status.tracking_history[0]["기사사번"] == "712234"
    assert status.tracking_history[1]["차량번호"] == "서울88아8731"
    assert status.tracking_history[1]["행낭운송장번호"] == "795317331843"


def _row(tracking_number: str, status_code: str, scan_time: str) -> dict:
    return {
        "TRSPBILLNUM": tracking_number,
        "SCNDIVCD": status_code,
        "SCNDT": scan_time[:8],
        "SCNHR": scan_time[8:],
    }


def test_filter_keeps_every_active_delivery() -> None:
    rows = [_row(str(index), "30", f"2026080{index}120000") for index in range(1, 7)]
    rows.extend(
        [
            _row("completed-1", "91", "20260807120000"),
            _row("completed-2", "91", "20260808120000"),
        ]
    )

    result = _filter_display_rows(
        rows,
        completed_retention_days=2,
        now=pytz.timezone("Asia/Seoul").localize(datetime(2026, 8, 8, 18)),
    )

    assert len([row for row in result if row["SCNDIVCD"] != "91"]) == 6
    assert len([row for row in result if row["SCNDIVCD"] == "91"]) == 2


def test_completed_deliveries_older_than_two_days_are_removed() -> None:
    timezone = pytz.timezone("Asia/Seoul")
    rows = [
        _row("within-window", "91", "20260806130000"),
        _row("expired", "91", "20260806110000"),
    ]

    result = _filter_display_rows(
        rows,
        completed_retention_days=2,
        now=timezone.localize(datetime(2026, 8, 8, 12)),
    )

    assert [row["TRSPBILLNUM"] for row in result] == ["within-window"]


def test_default_completed_counter_window_is_five_days() -> None:
    timezone = pytz.timezone("Asia/Seoul")
    rows = [
        _row("within-five-days", "91", "20260804120000"),
        _row("older-than-five-days", "91", "20260803115959"),
    ]

    result = _filter_display_rows(
        rows,
        now=timezone.localize(datetime(2026, 8, 8, 12)),
    )

    assert [row["TRSPBILLNUM"] for row in result] == ["within-five-days"]


@pytest.mark.asyncio
async def test_delivery_rows_fetches_all_pages_and_deduplicates() -> None:
    client = CJOneDeliveryClient(
        AsyncMock(),
        "010-1234-5678",
        user_id="user",
        access_token="access",
        refresh_token="refresh",
    )
    client._async_app_post = AsyncMock(
        side_effect=[
            {
                "list": [
                    {"TRSPBILLNUM": "1", "TOT_PAGE": "3"},
                    {"TRSPBILLNUM": "2", "TOT_PAGE": "3"},
                ]
            },
            {"list": [{"TRSPBILLNUM": "2"}, {"TRSPBILLNUM": "3"}]},
            {"list": [{"TRSPBILLNUM": "4"}]},
        ]
    )

    rows = await client._async_get_delivery_rows()

    assert [row["TRSPBILLNUM"] for row in rows] == ["1", "2", "3", "4"]
    assert client._async_app_post.await_count == 3


def test_kisa_encryption_round_trip() -> None:
    plain_text = "%7b%22PHONE%22%3a%2201012345678%22%7d"

    assert _kisa_decrypt(_kisa_encrypt(plain_text)) == plain_text


@pytest.mark.asyncio
async def test_expired_access_token_is_refreshed_and_retried() -> None:
    client = CJOneDeliveryClient(
        AsyncMock(),
        "010-1234-5678",
        user_id="user",
        access_token="expired",
        refresh_token="refresh",
    )
    client.async_refresh_token = AsyncMock()
    client._async_app_post = AsyncMock(return_value={"RES_CD": "S"})

    result = await client._async_handle_token_response(
        {"RES_CD": "TFE"},
        url="https://example.test/delivery",
        data={"page": "1"},
        screen_code=None,
        skip_token=False,
        allow_token_refresh=True,
    )

    assert result == {"RES_CD": "S"}
    client.async_refresh_token.assert_awaited_once()
    assert client._async_app_post.call_args.kwargs["allow_token_refresh"] is False
