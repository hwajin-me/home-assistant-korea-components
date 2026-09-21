"""Exercise the HTTP view's schema serializer, not only Python form creation."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.helpers.data_entry_flow import FlowManagerIndexView

from custom_components.korea_incubator.config_flow import KoreaOptionsFlow


def serialize(result):
    return FlowManagerIndexView(MagicMock())._prepare_result_json(result)


@pytest.mark.asyncio
@pytest.mark.parametrize("service", ["animal_medical", "pharmacy"])
async def test_medical_options_http_form_serialization(animal_hass, service):
    entry = MagicMock(data={"service": service}, options={})
    flow = KoreaOptionsFlow(entry)
    flow.hass = animal_hass
    result = await flow.async_step_init()
    payload = serialize(result)
    json.dumps(payload)
    fields = {field["name"]: field for field in payload["data_schema"]}
    assert fields["naver_place_url"]["type"] == "string"
    assert fields["naver_query"]["type"] == "string"
    assert result["errors"] == {}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "value,expected",
    [
        (" 18199503 ", "https://map.naver.com/p/entry/place/18199503"),
        (
            "https://map.naver.com/p/entry/place/18199503?c=15",
            "https://map.naver.com/p/entry/place/18199503",
        ),
        ("   ", ""),
    ],
)
async def test_url_validation_runs_after_submit(animal_hass, value, expected):
    flow = KoreaOptionsFlow(MagicMock(data={"service": "animal_medical"}, options={}))
    flow.hass = animal_hass
    result = await flow.async_step_init(
        {"scan_interval_minutes": 60, "naver_place_url": value}
    )
    assert result["type"] == "create_entry"
    assert result["data"]["naver_place_url"] == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "value",
    [
        "not-a-url",
        "https://evil.test/place/1",
        "https://map.naver.com:invalid/p/entry/place/1",
    ],
)
async def test_invalid_url_redisplays_serializable_form(animal_hass, value):
    flow = KoreaOptionsFlow(MagicMock(data={"service": "pharmacy"}, options={}))
    flow.hass = animal_hass
    result = await flow.async_step_init(
        {
            "scan_interval_minutes": 90,
            "naver_place_url": value,
            "naver_query": "서울 병원",
        }
    )
    payload = serialize(result)
    json.dumps(payload)
    assert payload["errors"] == {"naver_place_url": "invalid_naver_url"}
    fields = {field["name"]: field for field in payload["data_schema"]}
    assert fields["naver_place_url"]["default"] == value
    assert fields["scan_interval_minutes"]["default"] == 90
    assert fields["naver_query"]["default"] == "서울 병원"
    animal_hass.config_entries.async_schedule_reload.assert_not_called()


@pytest.mark.asyncio
async def test_naver_selection_http_serialization(animal_hass):
    flow = KoreaOptionsFlow(MagicMock(data={"service": "animal_medical"}, options={}))
    flow.hass = animal_hass
    with (
        patch(
            "custom_components.korea_incubator.animal_medical.naver_options.async_get_clientsession"
        ),
        patch(
            "custom_components.korea_incubator.animal_medical.naver_options.async_search",
            new_callable=AsyncMock,
            return_value=[{"id": "18199503", "name": "라온", "address": "서울"}],
        ),
    ):
        result = await flow.async_step_init(
            {"scan_interval_minutes": 60, "naver_query": "라온", "naver_place_url": ""}
        )
    payload = serialize(result)
    json.dumps(payload)
    assert payload["step_id"] == "medical_naver"
    assert len(payload["data_schema"]) == 2
