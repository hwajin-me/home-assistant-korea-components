"""Real config entries and registry boundaries for reconfiguration."""

from types import MappingProxyType, SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntry, ConfigEntries
from homeassistant.core import HomeAssistant

from custom_components.korea_incubator.config_flow import KoreaConfigFlow
from custom_components.korea_incubator.const import DOMAIN
from custom_components.korea_incubator.entity_reconfigure import reconcile_entities
from .test_reconfigure import make_flow


async def test_real_config_entry_updates_atomically_without_duplicate(tmp_path):
    hass = HomeAssistant(str(tmp_path))
    hass.config_entries = ConfigEntries(hass, {})
    entry = ConfigEntry(
        domain=DOMAIN,
        version=1,
        minor_version=1,
        source="user",
        data={"service": "earthquake", "api_key": "old", "home_latitude": 35.1},
        options={},
        title="My custom title",
        unique_id=None,
        discovery_keys=MappingProxyType({}),
        subentries_data=None,
    )
    hass.config_entries._entries[entry.entry_id] = entry
    flow = KoreaConfigFlow()
    flow.hass, flow.handler = hass, DOMAIN
    flow.context = {"source": "reconfigure", "entry_id": entry.entry_id}
    try:
        form = await flow.async_step_reconfigure()
        edited = {**form["data_schema"]({}), "api_key": "new"}
        with (
            patch("homeassistant.helpers.aiohttp_client.async_get_clientsession"),
            patch(
                "custom_components.korea_incubator.config_validation.validate_service",
                AsyncMock(),
            ),
            patch.object(hass.config_entries, "_async_schedule_save"),
            patch.object(hass.config_entries, "async_schedule_reload") as reload,
        ):
            result = await flow.async_step_earthquake(edited)
        assert result["reason"] == "reconfigure_successful"
        assert entry.data["api_key"] == "new"
        assert entry.data["home_latitude"] == 35.1
        assert entry.title == "My custom title"
        assert hass.config_entries.async_entries(DOMAIN) == [entry]
        reload.assert_called_once_with(entry.entry_id)
    finally:
        await hass.async_stop()


async def test_static_entity_cleanup_is_platform_scoped_and_keeps_disabled():
    entry = SimpleNamespace(entry_id="entry", data={"service": "airkorea"})
    entities = [
        SimpleNamespace(
            entity_id="sensor.keep",
            unique_id="keep",
            platform=DOMAIN,
            domain="sensor",
            device_id="keep-device",
            disabled_by="user",
        ),
        SimpleNamespace(
            entity_id="sensor.remove",
            unique_id="removed",
            platform=DOMAIN,
            domain="sensor",
            device_id="old-device",
        ),
        SimpleNamespace(
            entity_id="calendar.other",
            unique_id="other",
            platform=DOMAIN,
            domain="calendar",
            device_id="shared-device",
        ),
        SimpleNamespace(
            entity_id="sensor.foreign",
            unique_id="foreign",
            platform="other",
            domain="sensor",
            device_id=None,
        ),
    ]
    registry, devices = MagicMock(), MagicMock()
    devices.async_get.return_value = SimpleNamespace(
        config_entries={"entry", "another"}
    )

    @reconcile_entities("sensor")
    async def setup(hass, entry, add):
        add([SimpleNamespace(unique_id="keep")])
        add([SimpleNamespace(unique_id="new")])

    with (
        patch(
            "custom_components.korea_incubator.entity_reconfigure.er.async_get",
            return_value=registry,
        ),
        patch(
            "custom_components.korea_incubator.entity_reconfigure.er.async_entries_for_config_entry",
            return_value=entities,
        ),
        patch(
            "custom_components.korea_incubator.entity_reconfigure.er.async_entries_for_device",
            return_value=[SimpleNamespace(config_entry_id="another")],
        ),
        patch(
            "custom_components.korea_incubator.entity_reconfigure.dr.async_get",
            return_value=devices,
        ),
    ):
        add = MagicMock()
        await setup(MagicMock(), entry, add)
    registry.async_remove.assert_called_once_with("sensor.remove")
    devices.async_update_device.assert_called_once_with(
        "old-device", remove_config_entry_id="entry"
    )
    assert add.call_count == 2


async def test_failed_setup_keeps_entity_registry_untouched():
    @reconcile_entities("sensor")
    async def setup(hass, entry, add):
        raise ConnectionError("offline")

    with patch(
        "custom_components.korea_incubator.entity_reconfigure.er.async_get"
    ) as get:
        with pytest.raises(ConnectionError):
            await setup(
                MagicMock(), SimpleNamespace(data={"service": "airkorea"}), MagicMock()
            )
    get.assert_not_called()


async def test_cj_credentials_change_reloads_before_using_old_client(mock_hass):
    from custom_components.korea_incubator import _async_cj_options_updated

    entry = SimpleNamespace(
        entry_id="cj",
        data={"access_token": "new"},
        options={"scan_interval_minutes": 15},
    )
    coordinator = MagicMock(
        loaded_data={"access_token": "old"},
        loaded_options={"scan_interval_minutes": 30},
    )
    coordinator.async_request_refresh = AsyncMock()
    mock_hass.data[DOMAIN]["cj"] = {"coordinator": coordinator}
    mock_hass.config_entries.async_reload = AsyncMock()
    await _async_cj_options_updated(mock_hass, entry)
    mock_hass.config_entries.async_reload.assert_awaited_once_with("cj")
    coordinator.apply_options.assert_not_called()
    coordinator.async_request_refresh.assert_not_awaited()


async def test_school_reconfigure_validates_classes_and_time_before_commit():
    old = {
        "api_key": "key",
        "school_level": "elementary",
        "school_name": "School",
        "region_code": "B10",
        "school_code": "123",
        "grade_classes": ["1-1"],
        "grade": 1,
        "period_1": "08:30-09:20",
    }
    flow, _ = make_flow("school", old)
    await flow.async_step_reconfigure()
    await flow.async_step_school({"api_key": "new", "school_level": "elementary"})
    flow._data.update(region_code="B10", school_code="123", school_name="School")
    form = await flow.async_step_school_class()
    assert form["data_schema"]({})["grade_classes"] == ["1-1"]
    result = await flow.async_step_school_class({"grade_classes": []})
    assert result["errors"]["base"] == "no_selection"
    result = await flow.async_step_school_class({"grade_classes": ["2-3"]})
    assert result["data_schema"]({})["period_1"] == "08:30-09:20"
    result = await flow.async_step_school_periods({"period_1": "10:00-09:00"})
    assert result["errors"] == {"period_1": "invalid_time"}
    flow.hass.config_entries.async_update_entry.assert_not_called()
    result = await flow.async_step_school_periods({"period_1": "09:00-09:50"})
    assert result["reason"] == "reconfigure_successful"
    saved = flow.hass.config_entries.async_update_entry.call_args.kwargs["data"]
    assert saved["grade_classes"] == ["2-3"] and saved["grade"] == 2


async def test_kma_region_change_updates_air_station_and_area_code():
    flow, _ = make_flow("kma_weather", {"api_key": "key", "sido": "서울특별시"})
    await flow.async_step_reconfigure()
    with (
        patch("homeassistant.helpers.aiohttp_client.async_get_clientsession"),
        patch(
            "custom_components.korea_incubator.config_validation.validate_service",
            AsyncMock(),
        ),
    ):
        result = await flow.async_step_kma_weather(
            {"api_key": "key", "sido": "부산광역시"}
        )
    values = result["data_schema"]({"regions": ["중구"], "air_station": "중구"})
    result = await flow.async_step_kma_weather_sgg(values)
    assert result["reason"] == "reconfigure_successful"
    saved = flow.hass.config_entries.async_update_entry.call_args.kwargs["data"]
    assert saved["area_no"] == "2600000000"
    assert saved["regions"][0]["nx"] == 97


@pytest.mark.parametrize(
    "service,identity",
    [
        (
            "animal_medical",
            {
                "institution_type": "hospital",
                "municipality_code": "3000000",
                "management_number": "A1",
            },
        ),
        ("pharmacy", {"hpid": "C1"}),
    ],
)
async def test_changed_institution_preserves_ids_and_discards_old_naver(
    service, identity
):
    from custom_components.korea_incubator.animal_medical.sensor import (
        institution_identifier,
    )

    old = {
        **identity,
        "service": service,
        "api_key": "old",
        "business_name": "Old",
        "naver_place_url": "old-data",
        "kakao_place_id": "123",
    }
    flow, entry = make_flow(
        service, old, {"naver_place_url": "old-option", "scan_interval_minutes": 120}
    )
    await flow.async_step_reconfigure()
    new = {
        **old,
        "api_key": "new",
        "business_name": "New",
        "scan_interval_minutes": 15,
        "kakao_place_id": "456",
    }
    new.pop("naver_place_url")
    new["hpid" if service == "pharmacy" else "management_number"] = "other"
    flow._finish_service_entry(title="unused", data=new)
    saved = flow.hass.config_entries.async_update_entry.call_args.kwargs
    assert saved["data"]["device_unique_id"] == institution_identifier(entry.data)
    assert "naver_place_url" not in saved["data"]
    assert "naver_place_url" not in saved["options"]
    assert "scan_interval_minutes" not in saved["options"]


@pytest.mark.parametrize(
    "service,values,factory,method,response",
    [
        (
            "gasapp",
            {
                "token": "new",
                "member_id": "member",
                "company_id": "6",
                "use_contract_num": "contract",
            },
            "GasAppApiClient",
            "async_get_home_data",
            {},
        ),
        (
            "arisu",
            {"customer_number": "123", "customer_name": "New Name"},
            "ArisuApiClient",
            "async_get_water_bill_data",
            {"success": True},
        ),
    ],
)
async def test_remaining_account_services_update_in_place(
    service, values, factory, method, response
):
    flow, entry = make_flow(service, values)
    await flow.async_step_reconfigure()
    client = MagicMock()
    setattr(client, method, AsyncMock(return_value=response))
    with patch(
        f"custom_components.korea_incubator.config_flow.{factory}", return_value=client
    ):
        result = await getattr(flow, f"async_step_{service}")(dict(values))
    assert result["reason"] == "reconfigure_successful"
    saved = flow.hass.config_entries.async_update_entry.call_args.kwargs
    assert saved["entry"] is entry
    for key, value in values.items():
        assert saved["data"][key] == value


@pytest.mark.parametrize(
    "service,values,validator",
    [
        (
            "fuel",
            {"api_key": "new", "sido_codes": ["01"], "fuel_codes": ["B027"]},
            "fuel.api.validate_opinet",
        ),
        (
            "disaster",
            {"api_key": "new", "region_filter": "부산", "sub_region": ""},
            "disaster.api.validate_disaster_api",
        ),
        (
            "weather_warning",
            {"api_key": "new", "area_codes": ["L1100100"]},
            "weather.api.validate_kma_api",
        ),
    ],
)
async def test_remaining_public_services_commit_after_validation(
    service, values, validator
):
    flow, entry = make_flow(service, {"api_key": "old"})
    await flow.async_step_reconfigure()
    with patch(
        f"custom_components.korea_incubator.{validator}", AsyncMock()
    ) as validate:
        result = await getattr(flow, f"async_step_{service}")(values)
    if service == "weather_warning":
        validate.assert_awaited_once_with("new", "L1100100")
    else:
        validate.assert_awaited_once_with("new")
    assert result["reason"] == "reconfigure_successful"
    assert (
        flow.hass.config_entries.async_update_entry.call_args.kwargs["entry"] is entry
    )


async def test_lottery_reconfiguration_closes_client_and_preserves_entry():
    flow, entry = make_flow(
        "dh_lottery",
        {"username": "account", "password": "old"},
        unique_id="dh_lottery_account",
    )
    await flow.async_step_reconfigure()
    client = MagicMock(login=AsyncMock(), balance=AsyncMock(), close=AsyncMock())
    with patch(
        "custom_components.korea_incubator.lottery.LotteryClient", return_value=client
    ):
        result = await flow.async_step_dh_lottery(
            {"username": "account", "password": "new"}
        )
    client.close.assert_awaited_once()
    assert result["reason"] == "reconfigure_successful"
    assert (
        flow.hass.config_entries.async_update_entry.call_args.kwargs["entry"] is entry
    )


async def test_readding_transit_item_edits_instead_of_duplicate():
    flow, _ = make_flow(
        "transit",
        {
            "subway_items": [{"station": "서울역", "direction": "상행", "line_id": ""}],
            "bus_stops": [{"stop_id": "1", "stop_name": "Stop", "buses": ["100"]}],
        },
    )
    await flow.async_step_reconfigure()
    await flow.async_step_transit({"seoul_api_key": "key"})
    await flow.async_step_transit_keep(
        {"keep_items": ["subway_items:0", "bus_stops:0"]}
    )
    await flow.async_step_transit_subway({"station": "서울역", "direction": "상행"})
    flow._bus_stop_id, flow._bus_stop_name = "1", "Stop"
    await flow.async_step_transit_bus_select({"buses": ["200"]})
    assert len(flow._data["subway_items"]) == 1
    assert flow._data["bus_stops"] == [
        {"stop_id": "1", "stop_name": "Stop", "buses": ["200"]}
    ]


async def test_kakaomap_legacy_coordinates_restore_normalized_values():
    flow, _ = make_flow(
        "kakaomap",
        {
            "name": "route",
            "api_key": "key",
            "original_coord_system": "WGS84",
            "start_coords": {"x": 500001, "y": 1100001},
            "end_coords": {"x": 500002, "y": 1100002},
        },
    )
    form = await flow.async_step_reconfigure()
    values = form["data_schema"]({})
    assert values["coord_system"] == "WCONGNAMUL"
    assert values["start_x"] == "500001"
    assert values["end_y"] == "1100002"


async def test_kakaomap_validated_route_changes_keep_entry_and_clear_stale_options():
    flow, entry = make_flow(
        "kakaomap",
        {
            "name": "old",
            "api_key": "old",
            "original_coord_system": "WGS84",
            "start_x": "127.0",
            "start_y": "37.5",
            "end_x": "127.1",
            "end_y": "37.6",
        },
        {"api_key": "stale", "web_cookie": "stale"},
        unique_id="kakaomap_old",
    )
    form = await flow.async_step_reconfigure()
    data = {
        **form["data_schema"]({}),
        "name": "new",
        "api_key": "new",
        "web_cookie": "",
    }
    client = MagicMock(
        async_coordinate_to_address=AsyncMock(return_value={"success": True}),
        async_get_public_transport_route=AsyncMock(return_value={}),
    )
    with patch(
        "custom_components.korea_incubator.config_flow.KakaoMapApiClient",
        return_value=client,
    ):
        result = await flow.async_step_kakaomap(data)
    assert result["reason"] == "reconfigure_successful"
    saved = flow.hass.config_entries.async_update_entry.call_args
    assert saved.args == (entry,)
    assert saved.kwargs["data"]["api_key"] == "new"
    assert saved.kwargs["data"]["original_coord_system"] == "WGS84"
    assert saved.kwargs["options"] == {}
    assert saved.kwargs["unique_id"] == "kakaomap_new"


@pytest.mark.parametrize(
    "step,api_method",
    [
        ("safety_alert_sgg", "async_get_sgg_list"),
        ("safety_alert_emd", "async_get_emd_list"),
    ],
)
async def test_safety_region_lookup_failure_is_retryable(step, api_method):
    import aiohttp

    flow, _ = make_flow(
        "safety_alert",
        {
            "grouped": True,
            "regions": {"one": {"area_code": "11", "area_name": "Seoul"}},
        },
    )
    await flow.async_step_reconfigure()
    flow._safety_alert_data = {
        "sido_code": "11",
        "sido_name": "Seoul",
        "sgg_code": "111",
        "sgg_name": "Jongno",
    }
    with patch(
        "custom_components.korea_incubator.config_flow.SafetyAlertRegionApiClient"
    ) as factory:
        setattr(
            factory.return_value,
            api_method,
            AsyncMock(side_effect=aiohttp.ClientError("offline")),
        )
        result = await getattr(flow, f"async_step_{step}")()
    assert result["step_id"] == step
    assert result["errors"]["base"] == "cannot_connect"
    flow.hass.config_entries.async_update_entry.assert_not_called()


async def test_device_needed_by_pending_entities_is_not_detached():
    entry = SimpleNamespace(entry_id="entry", data={"service": "school"})
    registry, devices = MagicMock(), MagicMock()
    device = SimpleNamespace(
        config_entries={"entry"}, identifiers={(DOMAIN, "same-school")}
    )
    devices.async_get.return_value = device
    stale = SimpleNamespace(
        entity_id="calendar.old",
        unique_id="old",
        platform=DOMAIN,
        domain="calendar",
        device_id="device",
    )

    @reconcile_entities("calendar")
    async def setup(hass, entry, add):
        add(
            [
                SimpleNamespace(
                    unique_id="new",
                    device_info={"identifiers": {(DOMAIN, "same-school")}},
                )
            ]
        )

    with (
        patch(
            "custom_components.korea_incubator.entity_reconfigure.er.async_get",
            return_value=registry,
        ),
        patch(
            "custom_components.korea_incubator.entity_reconfigure.er.async_entries_for_config_entry",
            return_value=[stale],
        ),
        patch(
            "custom_components.korea_incubator.entity_reconfigure.er.async_entries_for_device",
            return_value=[],
        ),
        patch(
            "custom_components.korea_incubator.entity_reconfigure.dr.async_get",
            return_value=devices,
        ),
    ):
        await setup(MagicMock(), entry, MagicMock())
    registry.async_remove.assert_called_once_with("calendar.old")
    devices.async_update_device.assert_not_called()


@pytest.mark.parametrize(
    "data,identity",
    [
        ({"service": "goodsflow", "token": "original-token"}, "goodsflow_original"),
        ({"service": "pharmacy", "hpid": "C1"}, "pharmacy_C1"),
        (
            {
                "service": "animal_medical",
                "institution_type": "hospital",
                "municipality_code": "3000000",
                "management_number": "A1",
            },
            "animal_hospital_3000000_A1",
        ),
    ],
)
async def test_readding_original_institution_cannot_steal_retained_entities(
    data, identity
):
    flow = KoreaConfigFlow()
    flow.context = {"source": "user"}
    flow._async_current_entries = MagicMock(
        return_value=[SimpleNamespace(data={"device_unique_id": identity})]
    )
    flow.async_create_entry = MagicMock(return_value={"type": "create_entry"})
    flow._finish_service_entry(title="new", data=data)
    saved = flow.async_create_entry.call_args.kwargs["data"]
    assert saved["device_unique_id"].startswith(identity + "_")
    assert saved["device_unique_id"] != identity
    assert "device_unique_id" not in data
