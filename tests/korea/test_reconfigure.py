"""Reconfiguration must validate and update existing service entries in place."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.data_entry_flow import AbortFlow

from custom_components.korea_incubator.config_flow import KoreaConfigFlow


def make_flow(service, data=None, options=None, unique_id=None):
    entry = SimpleNamespace(
        entry_id="existing-entry",
        title="My custom title",
        data={"service": service, **(data or {})},
        options=options or {},
        unique_id=unique_id,
        subentries={},
        update_listeners=[MagicMock()]
        if service in {"kakaomap", "safety_alert"}
        else [],
    )
    flow = KoreaConfigFlow()
    flow.hass = MagicMock()
    flow.context = {"source": "reconfigure", "entry_id": entry.entry_id}
    flow.handler = "korea_incubator"
    flow.hass.config_entries.async_get_known_entry.return_value = entry
    flow.hass.config_entries.async_entry_for_domain_unique_id.return_value = None
    flow._async_in_progress = MagicMock(return_value=[])
    flow.async_create_entry = MagicMock(
        side_effect=AssertionError("Created a duplicate entry")
    )
    return flow, entry


@pytest.mark.parametrize(
    "service",
    [
        "kepco",
        "gasapp",
        "goodsflow",
        "cj_one_delivery",
        "arisu",
        "kakaomap",
        "weather_warning",
        "transit",
        "fuel",
        "school",
        "disaster",
        "airkorea",
        "kma_weather",
        "earthquake",
        "dh_lottery",
    ],
)
async def test_each_service_opens_its_own_form(service):
    flow, _ = make_flow(service)
    result = await flow.async_step_reconfigure()
    assert result["type"] == "form"
    assert result["step_id"] == service
    flow.hass.config_entries.async_update_entry.assert_not_called()


async def test_earthquake_prefill_and_save_preserve_entry():
    flow, entry = make_flow(
        "earthquake",
        {
            "api_key": "old",
            "home_latitude": 35.1,
            "home_longitude": 129.1,
            "radius_km": 80,
            "min_magnitude": 2.5,
        },
        {"unrelated": True},
    )
    result = await flow.async_step_reconfigure()
    values = result["data_schema"]({})
    assert values["latitude"] == 35.1
    assert values["longitude"] == 129.1
    result = await flow.async_step_earthquake({**values, "api_key": "new"})
    assert result["reason"] == "reconfigure_successful"
    call = flow.hass.config_entries.async_update_entry.call_args.kwargs
    assert call["entry"] is entry
    assert call["data"]["api_key"] == "new"
    assert call["options"] == {"unrelated": True}
    flow.hass.config_entries.async_schedule_reload.assert_called_once_with(
        entry.entry_id
    )


async def test_failed_validation_leaves_entry_untouched():
    flow, entry = make_flow(
        "weather_warning", {"api_key": "old", "area_codes": ["L1010100"]}
    )
    await flow.async_step_reconfigure()
    with patch(
        "custom_components.korea_incubator.weather.api.validate_kma_api",
        AsyncMock(side_effect=ValueError("expired")),
    ):
        result = await flow.async_step_weather_warning(
            {"api_key": "bad", "area_codes": ["L1010100"]}
        )
    assert result["errors"]["base"] == "invalid_api_key"
    assert entry.data["api_key"] == "old"
    flow.hass.config_entries.async_update_entry.assert_not_called()


async def test_same_account_is_allowed_but_other_account_is_not():
    flow, entry = make_flow(
        "kepco", {"username": "old", "password": "old"}, unique_id="kepco_old"
    )
    await flow.async_step_reconfigure()
    client = MagicMock(async_login=AsyncMock(return_value=True))
    with patch(
        "custom_components.korea_incubator.config_flow.KepcoApiClient",
        return_value=client,
    ):
        flow.hass.config_entries.async_entry_for_domain_unique_id.return_value = entry
        result = await flow.async_step_kepco({"username": "old", "password": "new"})
        assert result["reason"] == "reconfigure_successful"
        flow.hass.config_entries.async_update_entry.reset_mock()
        flow.hass.config_entries.async_entry_for_domain_unique_id.return_value = None
        with pytest.raises(AbortFlow, match="reconfigure_account_mismatch"):
            await flow.async_step_kepco({"username": "different", "password": "new"})
    flow.hass.config_entries.async_update_entry.assert_not_called()


async def test_rotated_goodsflow_token_does_not_create_duplicate():
    flow, entry = make_flow(
        "goodsflow", {"token": "old-token"}, unique_id="goodsflow_old-toke"
    )
    await flow.async_step_reconfigure()
    client = MagicMock(
        async_get_tracking_list=AsyncMock(return_value={"success": True})
    )
    with patch(
        "custom_components.korea_incubator.config_flow.GoodsFlowApiClient",
        return_value=client,
    ):
        result = await flow.async_step_goodsflow({"token": "new-token"})
        assert result["reason"] == "reconfigure_successful"
        assert (
            flow.hass.config_entries.async_update_entry.call_args.kwargs["unique_id"]
            == "goodsflow_new-toke"
        )
        flow.hass.config_entries.async_update_entry.reset_mock()
        flow.hass.config_entries.async_entry_for_domain_unique_id.return_value = (
            SimpleNamespace(entry_id="another")
        )
        with pytest.raises(AbortFlow, match="already_configured"):
            await flow.async_step_goodsflow({"token": "another-token"})
    flow.hass.config_entries.async_update_entry.assert_not_called()


async def test_airkorea_multistep_prefill_and_save():
    flow, _ = make_flow(
        "airkorea",
        {"api_key": "old", "sido": "서울", "stations": [{"stationName": "강남구"}]},
    )
    result = await flow.async_step_reconfigure()
    values = result["data_schema"]({})
    result = await flow.async_step_airkorea({**values, "api_key": "new"})
    assert result["data_schema"]({})["stations"] == ["강남구"]
    result = await flow.async_step_airkorea_select({"stations": ["강남구"]})
    assert result["reason"] == "reconfigure_successful"
    assert (
        flow.hass.config_entries.async_update_entry.call_args.kwargs["data"]["api_key"]
        == "new"
    )


async def test_transit_retains_selected_items_without_mutating_saved_lists():
    old_items = [{"station": "서울역", "direction": "상행", "line_id": "1001"}]
    flow, entry = make_flow(
        "transit", {"subway_items": old_items, "bus_stops": [{"stop_id": "123"}]}
    )
    await flow.async_step_reconfigure()
    result = await flow.async_step_transit({"seoul_api_key": "new"})
    assert result["step_id"] == "transit_keep"
    await flow.async_step_transit_keep({"keep_items": ["subway_items:0"]})
    await flow.async_step_transit_subway({"station": "시청", "direction": "하행"})
    result = await flow.async_step_transit_done()
    assert result["reason"] == "reconfigure_successful"
    data = flow.hass.config_entries.async_update_entry.call_args.kwargs["data"]
    assert len(data["subway_items"]) == 2
    assert data["bus_stops"] == []
    assert entry.data["subway_items"] == old_items
    assert len(old_items) == 1


async def test_safety_alert_updates_only_selected_region():
    old = {"service": "safety_alert", "area_code": "11", "area_name": "서울"}
    other = {"service": "safety_alert", "area_code": "26", "area_name": "부산"}
    flow, _ = make_flow(
        "safety_alert", {"grouped": True, "regions": {"first": old, "second": other}}
    )
    result = await flow.async_step_reconfigure()
    assert result["step_id"] == "safety_alert_region"
    with patch.object(flow, "async_step_safety_alert", AsyncMock()):
        await flow.async_step_safety_alert_region({"region": "first"})
    result = await flow._finish_safety_alert(
        {**old, "area_code": "28", "area_name": "인천"}
    )
    assert result["reason"] == "reconfigure_successful"
    data = flow.hass.config_entries.async_update_entry.call_args.kwargs["data"]
    assert data["regions"]["second"] == other
    assert data["regions"]["first"]["area_code"] == "28"
    flow.hass.config_entries.async_update_entry.reset_mock()
    result = await flow._finish_safety_alert(other)
    assert result["reason"] == "already_configured"
    flow.hass.config_entries.async_update_entry.assert_not_called()


async def test_kakaomap_replaces_stale_options_and_uses_listener_reload():
    flow, _ = make_flow(
        "kakaomap",
        {"api_key": "old"},
        {"api_key": "override", "web_cookie": "stale", "other": 1},
    )
    await flow.async_step_reconfigure()
    result = flow._finish_service_entry(
        title="unused", data={"service": "kakaomap", "api_key": "new", "web_cookie": ""}
    )
    assert result["reason"] == "reconfigure_successful"
    assert flow.hass.config_entries.async_update_entry.call_args.kwargs["options"] == {
        "other": 1
    }
    flow.hass.config_entries.async_schedule_reload.assert_not_called()


async def test_cj_reconfigure_verifies_sms_before_replacing_tokens():
    from custom_components.korea_incubator.cj_one_delivery.api import AuthSession

    flow, entry = make_flow(
        "cj_one_delivery",
        {"phone_number": "01012345678", "access_token": "old"},
        {"scan_interval_minutes": 12},
        unique_id="cj_one_delivery_01012345678",
    )
    entry.update_listeners = [MagicMock()]
    await flow.async_step_reconfigure()
    client = MagicMock(
        async_send_verification_code=AsyncMock(),
        async_verify_code=AsyncMock(return_value=AuthSession("user", "new", "refresh")),
    )
    with (
        patch("custom_components.korea_incubator.config_flow.async_get_clientsession"),
        patch(
            "custom_components.korea_incubator.config_flow.CJOneDeliveryClient",
            return_value=client,
        ),
    ):
        result = await flow.async_step_cj_one_delivery({"phone_number": "01012345678"})
        assert result["step_id"] == "cj_one_delivery_code"
        flow.hass.config_entries.async_update_entry.assert_not_called()
        result = await flow.async_step_cj_one_delivery_code({"auth_code": "123456"})
        assert result["data_schema"]({})["scan_interval_minutes"] == 12
        result = await flow.async_step_cj_one_delivery_options(
            {"scan_interval_minutes": 12}
        )
    assert result["reason"] == "reconfigure_successful"
    assert (
        flow.hass.config_entries.async_update_entry.call_args.kwargs["data"][
            "access_token"
        ]
        == "new"
    )
    flow.hass.config_entries.async_schedule_reload.assert_called_once_with(
        entry.entry_id
    )


async def test_goodsflow_device_keeps_identity_after_token_rotation():
    from custom_components.korea_incubator.goodsflow.device import GoodsFlowDevice

    flow, _ = make_flow("goodsflow", {"token": "original-token"})
    await flow.async_step_reconfigure()
    flow._finish_service_entry(
        title="unused", data={"service": "goodsflow", "token": "new-token"}
    )
    data = flow.hass.config_entries.async_update_entry.call_args.kwargs["data"]
    device = GoodsFlowDevice(
        flow.hass,
        "existing-entry",
        data["token"],
        MagicMock(),
        unique_id=data["device_unique_id"],
    )
    assert device.unique_id == "goodsflow_original"
    assert device.token == "new-token"


async def test_fuel_and_disaster_restore_transformed_values():
    flow, _ = make_flow(
        "fuel",
        {
            "api_key": "saved",
            "configs": [
                {"sido_code": "01", "fuel_code": "B027"},
                {"sido_code": "01", "fuel_code": "D047"},
            ],
        },
    )
    result = await flow.async_step_reconfigure()
    values = result["data_schema"]({})
    assert values["sido_codes"] == ["01"]
    assert values["fuel_codes"] == ["B027", "D047"]
    flow, _ = make_flow(
        "disaster", {"api_key": "saved", "region_filter": "서울 용산구"}
    )
    result = await flow.async_step_reconfigure()
    values = result["data_schema"]({})
    assert values["region_filter"] == ""
    assert values["sub_region"] == "서울 용산구"


async def test_weather_options_are_saved_and_reloaded():
    from custom_components.korea_incubator.config_flow import KoreaOptionsFlow

    _, entry = make_flow("weather_warning", {"api_key": "old", "area_codes": []})
    flow = KoreaOptionsFlow(entry)
    flow.hass = MagicMock()
    flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})
    result = await flow.async_step_init({"api_key": "new", "area_codes": ["L1010100"]})
    assert result["type"] == "create_entry"
    assert (
        flow.hass.config_entries.async_update_entry.call_args.kwargs["data"]["api_key"]
        == "new"
    )
    flow.hass.config_entries.async_schedule_reload.assert_called_once_with(
        entry.entry_id
    )
