"""Tests for the CJ O-NE steps in the monolithic config flow."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.korea_incubator.cj_one_delivery.api import AuthSession
from custom_components.korea_incubator.cj_one_delivery.exceptions import InvalidAuth
from custom_components.korea_incubator.config_flow import (
    KoreaConfigFlow,
    _cj_one_delivery_options_schema,
)


@pytest.mark.asyncio
async def test_invalid_phone_number_is_rejected_before_sms_request() -> None:
    flow = KoreaConfigFlow()

    result = await flow.async_step_cj_one_delivery({"phone_number": "010-123"})

    assert result["type"] == "form"
    assert result["errors"] == {"phone_number": "invalid_phone_number"}


@pytest.mark.asyncio
async def test_sms_success_moves_to_code_step() -> None:
    flow = KoreaConfigFlow()
    flow.hass = MagicMock()
    client = MagicMock()
    client.async_send_verification_code = AsyncMock()

    with (
        patch("custom_components.korea_incubator.config_flow.async_get_clientsession"),
        patch(
            "custom_components.korea_incubator.config_flow.CJOneDeliveryClient",
            return_value=client,
        ),
    ):
        result = await flow.async_step_cj_one_delivery(
            {"phone_number": "010-1234-5678"}
        )

    assert result["type"] == "form"
    assert result["step_id"] == "cj_one_delivery_code"
    client.async_send_verification_code.assert_awaited_once()


@pytest.mark.asyncio
async def test_verification_success_moves_to_options_step() -> None:
    flow = KoreaConfigFlow()
    flow.hass = MagicMock()
    flow._cj_phone_number = "010-1234-5678"
    flow.async_set_unique_id = AsyncMock()
    flow._abort_if_unique_id_configured = MagicMock()
    client = MagicMock()
    client.async_verify_code = AsyncMock(
        return_value=AuthSession("user", "access", "refresh")
    )

    with (
        patch("custom_components.korea_incubator.config_flow.async_get_clientsession"),
        patch(
            "custom_components.korea_incubator.config_flow.CJOneDeliveryClient",
            return_value=client,
        ),
    ):
        result = await flow.async_step_cj_one_delivery_code({"auth_code": "123456"})

    assert result["type"] == "form"
    assert result["step_id"] == "cj_one_delivery_options"
    flow.async_set_unique_id.assert_awaited_once_with("cj_one_delivery_01012345678")


@pytest.mark.asyncio
async def test_invalid_verification_code_stays_on_code_step() -> None:
    flow = KoreaConfigFlow()
    flow.hass = MagicMock()
    flow._cj_phone_number = "010-1234-5678"
    client = MagicMock()
    client.async_verify_code = AsyncMock(side_effect=InvalidAuth("bad code"))

    with (
        patch("custom_components.korea_incubator.config_flow.async_get_clientsession"),
        patch(
            "custom_components.korea_incubator.config_flow.CJOneDeliveryClient",
            return_value=client,
        ),
    ):
        result = await flow.async_step_cj_one_delivery_code({"auth_code": "000000"})

    assert result["type"] == "form"
    assert result["step_id"] == "cj_one_delivery_code"
    assert result["errors"] == {"base": "invalid_verification_code"}


def test_options_schema_bounds() -> None:
    schema = _cj_one_delivery_options_schema()

    assert schema({"scan_interval_minutes": 3}) == {"scan_interval_minutes": 3}
    assert schema({"scan_interval_minutes": 30}) == {"scan_interval_minutes": 30}

    with pytest.raises(Exception):
        schema({"scan_interval_minutes": 2})

    with pytest.raises(Exception):
        schema({"scan_interval_minutes": 31})

    migrated_schema = _cj_one_delivery_options_schema({"scan_interval_minutes": 180})
    assert migrated_schema({}) == {"scan_interval_minutes": 30}


@pytest.mark.asyncio
async def test_options_step_creates_cj_service_entry() -> None:
    flow = KoreaConfigFlow()
    flow._cj_phone_number = "010-1234-5678"
    flow._cj_auth_session = AuthSession("user", "access", "refresh")

    result = await flow.async_step_cj_one_delivery_options(
        {"scan_interval_minutes": 20}
    )

    assert result["type"] == "create_entry"
    assert result["data"]["service"] == "cj_one_delivery"
    assert result["data"]["access_token"] == "access"
    assert result["options"]["scan_interval_minutes"] == 20
