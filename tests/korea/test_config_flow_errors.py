"""Regression tests for config-flow API error details."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.korea_incubator.config_flow import KoreaConfigFlow
from custom_components.korea_incubator.gasapp.api import GasAppApiClient
from custom_components.korea_incubator.gasapp.exceptions import GasAppAuthError
from custom_components.korea_incubator.goodsflow.api import GoodsFlowApiClient
from custom_components.korea_incubator.goodsflow.exceptions import GoodsFlowAuthError


@pytest.mark.asyncio
async def test_weather_warning_shows_api_error_detail() -> None:
    """An API validation message must be available to the translation placeholder."""
    flow = KoreaConfigFlow()

    with patch(
        "custom_components.korea_incubator.weather.api.validate_kma_api",
        AsyncMock(side_effect=ValueError("KMA API 30: SERVICE KEY IS NOT REGISTERED")),
    ):
        result = await flow.async_step_weather_warning(
            {"api_key": "bad-key", "area_codes": ["L1010100"]}
        )

    assert result["type"] == "form"
    assert result["errors"] == {"base": "invalid_api_key"}
    assert result["description_placeholders"] == {
        "error": "KMA API 30: SERVICE KEY IS NOT REGISTERED"
    }


@pytest.mark.asyncio
async def test_disaster_shows_expired_key_detail() -> None:
    """An expired disaster key must be reported as an API-key error."""
    flow = KoreaConfigFlow()

    with patch(
        "custom_components.korea_incubator.disaster.api.validate_disaster_api",
        AsyncMock(side_effect=ValueError("기한만료된 서비스키 (code 31)")),
    ):
        result = await flow.async_step_disaster(
            {
                "api_key": "expired-key",
                "region_filter": "서울",
                "sub_region": "서울 용산구",
            }
        )

    assert result["type"] == "form"
    assert result["errors"] == {"base": "invalid_api_key"}
    assert result["description_placeholders"] == {
        "error": "기한만료된 서비스키 (code 31)"
    }


@pytest.mark.asyncio
async def test_goodsflow_auth_error_shows_api_error_detail() -> None:
    """GoodsFlow setup must preserve the API authentication response."""
    flow = KoreaConfigFlow()
    session_context = MagicMock()
    session_context.__aenter__ = AsyncMock(return_value=MagicMock())
    session_context.__aexit__ = AsyncMock(return_value=None)
    client = MagicMock()
    client.async_get_tracking_list = AsyncMock(
        side_effect=GoodsFlowAuthError("Authentication failed: expired token")
    )

    with (
        patch(
            "custom_components.korea_incubator.config_flow.aiohttp.ClientSession",
            return_value=session_context,
        ),
        patch(
            "custom_components.korea_incubator.config_flow.GoodsFlowApiClient",
            return_value=client,
        ),
    ):
        result = await flow.async_step_goodsflow({"token": "expired"})

    assert result["type"] == "form"
    assert result["errors"] == {"base": "invalid_auth"}
    assert result["description_placeholders"] == {
        "error": "Authentication failed: expired token"
    }


@pytest.mark.asyncio
async def test_gasapp_config_forwards_company_id() -> None:
    """GasApp setup must use the configured X-Company value."""
    flow = KoreaConfigFlow()
    session_context = MagicMock()
    session_context.__aenter__ = AsyncMock(return_value=MagicMock())
    session_context.__aexit__ = AsyncMock(return_value=None)
    client = MagicMock()
    client.async_get_home_data = AsyncMock(
        side_effect=GasAppAuthError("Authentication failed")
    )

    with (
        patch(
            "custom_components.korea_incubator.config_flow.aiohttp.ClientSession",
            return_value=session_context,
        ),
        patch(
            "custom_components.korea_incubator.config_flow.GasAppApiClient",
            return_value=client,
        ),
    ):
        await flow.async_step_gasapp(
            {
                "token": "token",
                "member_id": "member",
                "company_id": "6",
                "use_contract_num": "contract",
            }
        )

    client.set_credentials.assert_called_once_with(
        "token", "member", "contract", company_id="6"
    )


def test_config_flow_error_is_limited_for_ui() -> None:
    """Unexpectedly large API bodies must not flood the config-flow UI."""
    from custom_components.korea_incubator.config_flow import _flow_error_message

    assert len(_flow_error_message("x" * 1000, "fallback")) == 500
    assert _flow_error_message("  ", "fallback") == "fallback"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("client_factory", "configure", "request_call", "error_type"),
    [
        (
            GasAppApiClient,
            lambda client: client.set_credentials("token", "member", "contract"),
            lambda client: client.async_get_home_data(),
            GasAppAuthError,
        ),
        (
            GoodsFlowApiClient,
            lambda client: client.set_token("token"),
            lambda client: client.async_get_tracking_list(),
            GoodsFlowAuthError,
        ),
    ],
)
async def test_api_client_preserves_http_error_body(
    client_factory, configure, request_call, error_type
) -> None:
    """Authentication exceptions must contain the API response body."""
    response = MagicMock(status=401, reason="Unauthorized")
    response.text = AsyncMock(return_value='{"message":"expired token"}')
    request_context = MagicMock()
    request_context.__aenter__ = AsyncMock(return_value=response)
    request_context.__aexit__ = AsyncMock(return_value=None)
    session = MagicMock()
    session.request.return_value = request_context
    client = client_factory(session)
    configure(client)

    with pytest.raises(error_type, match="expired token"):
        await request_call(client)
