"""Error headers and draft retry values must never corrupt a working entry."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from custom_components.korea_incubator.config_validation import (
    PublicDataAuthError,
    validate_response,
    validate_service,
)
from custom_components.korea_incubator.config_flow import KoreaOptionsFlow
from .test_reconfigure import make_flow


def response_session(body, status=200):
    response = MagicMock(status=status)
    response.text = AsyncMock(return_value=body)
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=response)
    context.__aexit__ = AsyncMock(return_value=None)
    session = MagicMock()
    session.get.return_value = context
    return session, response


@pytest.mark.parametrize(
    "body",
    [
        json.dumps(
            {"response": {"header": {"resultCode": "00"}, "body": {"items": []}}}
        ),
        json.dumps(
            {"response": {"header": {"resultCode": "03", "resultMsg": "NO_DATA"}}}
        ),
        "<response><header><resultCode>00</resultCode></header></response>",
    ],
)
async def test_public_data_valid_empty_responses(body):
    session, _ = response_session(body)
    await validate_response(session, "http://unused", {})


@pytest.mark.parametrize(
    "body,status,error",
    [
        (
            json.dumps(
                {
                    "response": {
                        "header": {"resultCode": "30", "resultMsg": "UNREGISTERED"}
                    }
                }
            ),
            200,
            PublicDataAuthError,
        ),
        (
            "<OpenAPI_ServiceResponse><cmmMsgHeader><returnReasonCode>31</returnReasonCode><returnAuthMsg>EXPIRED</returnAuthMsg></cmmMsgHeader></OpenAPI_ServiceResponse>",
            200,
            PublicDataAuthError,
        ),
        ("forbidden", 403, PublicDataAuthError),
        ("<html>gateway</html>", 200, ConnectionError),
        ("not xml or json", 200, ConnectionError),
        (
            '{"response":{"header":{"resultCode":"22","resultMsg":"QUOTA"}}}',
            200,
            ConnectionError,
        ),
    ],
)
async def test_public_data_rejects_errors_without_discarding_message(
    body, status, error
):
    session, _ = response_session(body, status)
    with pytest.raises(error):
        await validate_response(session, "http://unused", {})


@pytest.mark.parametrize("service", ["airkorea", "kma_weather", "earthquake"])
async def test_each_public_service_uses_its_own_endpoint(service):
    session, _ = response_session('{"response":{"header":{"resultCode":"00"}}}')
    await validate_service(
        session,
        service,
        {
            "api_key": "a%2Bb",
            "sido": "서울특별시" if service == "kma_weather" else "서울",
        },
    )
    assert session.get.call_args.kwargs["params"]["serviceKey"] == "a+b"
    expected = {
        "airkorea": "getMsrstnAcctoRltmMesureDnsty",
        "kma_weather": "getVilageFcst",
        "earthquake": "getEqkMsg",
    }
    assert session.get.call_args.args[0].endswith(expected[service])


async def test_airkorea_validates_explicit_living_key():
    session, _ = response_session('{"response":{"header":{"resultCode":"00"}}}')
    await validate_service(
        session,
        "airkorea",
        {"api_key": "air", "living_api_key": "living", "sido": "서울"},
    )
    assert session.get.call_count == 2
    assert session.get.call_args.kwargs["params"]["serviceKey"] == "living"


@pytest.mark.parametrize("service", ["airkorea", "kma_weather", "earthquake"])
@pytest.mark.parametrize(
    "error,reason",
    [
        (PublicDataAuthError("expired"), "invalid_api_key"),
        (aiohttp.ClientError("offline"), "cannot_connect"),
    ],
)
async def test_public_service_failure_keeps_old_entry_and_new_draft(
    service, error, reason
):
    flow, entry = make_flow(
        service,
        {
            "api_key": "old",
            "sido": "서울특별시" if service == "kma_weather" else "서울",
        },
    )
    await flow.async_step_reconfigure()
    with (
        patch("homeassistant.helpers.aiohttp_client.async_get_clientsession"),
        patch(
            "custom_components.korea_incubator.config_validation.validate_service",
            AsyncMock(side_effect=error),
        ),
    ):
        result = await getattr(flow, f"async_step_{service}")(
            {
                "api_key": "edited",
                "sido": "서울특별시" if service == "kma_weather" else "서울",
            }
            if service != "earthquake"
            else {"api_key": "edited"}
        )
    assert result["errors"] == {"base": reason}
    assert result["data_schema"]({})["api_key"] == "edited"
    assert entry.data["api_key"] == "old"
    flow.hass.config_entries.async_update_entry.assert_not_called()


@pytest.mark.parametrize("service", ["airkorea", "kma_weather"])
async def test_region_change_does_not_reuse_same_named_child(service):
    old = {
        "api_key": "key",
        "sido": "서울특별시" if service == "kma_weather" else "서울",
        "stations": [{"stationName": "중구"}],
        "regions": [{"name": "중구", "nx": 60, "ny": 127}],
        "air_station": "중구",
    }
    flow, _ = make_flow(service, old)
    await flow.async_step_reconfigure()
    with (
        patch("homeassistant.helpers.aiohttp_client.async_get_clientsession"),
        patch(
            "custom_components.korea_incubator.config_validation.validate_service",
            AsyncMock(),
        ),
    ):
        result = await getattr(flow, f"async_step_{service}")(
            {
                "api_key": "key",
                "sido": "부산광역시" if service == "kma_weather" else "부산",
            }
        )
    if service == "kma_weather":
        assert result["data_schema"]({"regions": ["중구"]})["air_station"] == ""
        result = await flow.async_step_kma_weather_sgg({"regions": []})
    else:
        result = await flow.async_step_airkorea_select({"stations": []})
    assert result["errors"]["base"] == "no_selection"
    flow.hass.config_entries.async_update_entry.assert_not_called()


async def test_kakaomap_options_submission_is_connected_and_validated():
    _, entry = make_flow(
        "kakaomap",
        {"start_coords": {"x": 1, "y": 2}, "end_coords": {"x": 3, "y": 4}},
        {"web_cookie": "old", "other": 1},
    )
    flow = KoreaOptionsFlow(entry)
    flow.hass = MagicMock()
    flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})
    assert (await flow.async_step_init())["step_id"] == "kakaomap"
    with (
        patch("custom_components.korea_incubator.config_flow.async_get_clientsession"),
        patch(
            "custom_components.korea_incubator.config_flow.KakaoMapApiClient"
        ) as factory,
    ):
        factory.return_value.async_get_public_transport_route = AsyncMock()
        result = await flow.async_step_kakaomap({"api_key": "new"})
    assert result["type"] == "create_entry"
    assert flow.async_create_entry.call_args.kwargs["data"] == {
        "api_key": "new",
        "web_cookie": "",
        "other": 1,
    }


async def test_weather_options_reject_bad_key_without_update():
    _, entry = make_flow(
        "weather_warning", {"api_key": "old", "area_codes": ["L1100100"]}
    )
    flow = KoreaOptionsFlow(entry)
    flow.hass = MagicMock()
    with patch(
        "custom_components.korea_incubator.weather.api.validate_kma_api",
        AsyncMock(side_effect=ValueError("expired")),
    ):
        result = await flow.async_step_init(
            {"api_key": "edited", "area_codes": ["L1100100"]}
        )
    assert result["errors"]["base"] == "invalid_api_key"
    assert result["data_schema"]({})["api_key"] == "edited"
    flow.hass.config_entries.async_update_entry.assert_not_called()


async def test_legacy_account_without_unique_id_cannot_change_identity():
    from homeassistant.data_entry_flow import AbortFlow

    flow, _ = make_flow("arisu", {"customer_number": "123"})
    await flow.async_step_reconfigure()
    await flow.async_set_unique_id("arisu_456")
    with pytest.raises(AbortFlow, match="reconfigure_account_mismatch"):
        flow._check_service_unique_id()


async def test_reauth_reuses_credential_form_and_returns_correct_reason():
    flow, entry = make_flow("goodsflow", {"token": "old-token"})
    flow.context["source"] = "reauth"
    form = await flow.async_step_reauth(entry.data)
    assert form["step_id"] == "goodsflow"
    assert form["data_schema"]({})["token"] == "old-token"
    with patch(
        "custom_components.korea_incubator.config_flow.GoodsFlowApiClient"
    ) as factory:
        factory.return_value.async_get_tracking_list = AsyncMock(
            return_value={"success": True}
        )
        result = await flow.async_step_goodsflow({"token": "new-token"})
    assert result["reason"] == "reauth_successful"
