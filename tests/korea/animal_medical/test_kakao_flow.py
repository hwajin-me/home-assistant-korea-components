"""Kakao matching, retry, navigation, validation and existing-entry linking."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.korea_incubator.animal_medical.api import AnimalMedicalApiError
from custom_components.korea_incubator.animal_medical.kakao import KakaoError

pytestmark = pytest.mark.asyncio


async def test_auto_match_and_no_session_persistence(
    flow, record, entry_data, kakao_network
):
    result = await flow._async_link_kakao(record, entry_data)
    assert result["data"]["kakao_place_id"] == "123"
    assert "token" not in str(result["data"]) and "cookie" not in str(result["data"])
    assert kakao_network[0].call_args.args[1:] == ("서울특별시 종로구 동물병원", 1)


@pytest.mark.parametrize("lang", ["ko", "en"])
async def test_paging_and_manual_selection(
    flow, record, entry_data, kakao_network, lang
):
    flow.hass.config.language = lang
    search, place, _ = kakao_network
    first = search.return_value[0]
    second = [{**first[0], "id": "456"}]
    search.side_effect = [(first, 2), (second, 2), (first, 2), (second, 2)]
    result = await flow._async_link_kakao(record, entry_data)
    assert result["step_id"] == "animal_kakao"  # Don't auto-match a partial set.
    result = await flow.async_step_animal_kakao({"selection": "__next__"})
    assert result["description_placeholders"]["page"] == "2"
    result = await flow.async_step_animal_kakao({"selection": "123"})
    assert result["errors"] == {"base": "animal_invalid_selection"}
    result = await flow.async_step_animal_kakao({"selection": "__previous__"})
    assert result["description_placeholders"]["page"] == "1"
    await flow.async_step_animal_kakao({"selection": "__next__"})
    result = await flow.async_step_animal_kakao({"selection": "456"})
    assert result["data"]["kakao_place_id"] == "456"
    place.assert_awaited_once()


async def test_retry_failures_and_repeated_page(
    flow, record, entry_data, kakao_network
):
    search, place, _ = kakao_network
    first = search.return_value[0]
    search.side_effect = [
        KakaoError("HTTP 429"),
        (first, 2),
        (first, 2),
        KakaoError("HTTP 503"),
    ]
    result = await flow._async_link_kakao(record, entry_data)
    assert result["errors"]["base"] == "animal_kakao_error"
    assert "429" in result["description_placeholders"]["error"]
    assert (await flow.async_step_animal_kakao())["step_id"] == "animal_kakao"
    await flow.async_step_animal_kakao({"selection": "__retry__"})
    result = await flow.async_step_animal_kakao({"selection": "__next__"})
    assert "repeated" in result["description_placeholders"]["error"]
    assert flow._kakao_page == 1
    result = await flow.async_step_animal_kakao({"selection": "__next__"})
    assert flow._kakao_items == first
    place.side_effect = KakaoError("missing identity")
    result = await flow.async_step_animal_kakao({"selection": "123"})
    assert result["errors"]["base"] == "animal_kakao_error"


async def test_no_results_edit_query_and_auto_detail_failure(
    flow, record, entry_data, kakao_network
):
    search, place, _ = kakao_network
    original = search.return_value
    search.return_value = ([], 1)
    result = await flow._async_link_kakao(record, entry_data)
    assert result["errors"]["base"] == "animal_kakao_no_results"
    result = await flow.async_step_animal_kakao({"query": "  "})
    assert result["errors"]["base"] == "required_search_value"
    search.return_value = original
    place.side_effect = KakaoError("HTTP 503")
    result = await flow.async_step_animal_kakao(
        {"query": "새 검색어", "selection": "__retry__"}
    )
    assert search.call_args.args[1:] == ("새 검색어", 1)
    assert result["errors"]["base"] == "animal_kakao_error"
    place.side_effect = None
    assert (await flow.async_step_animal_kakao({}))["data"]["kakao_place_id"] == "123"


async def test_ambiguous_and_navigation_boundaries(
    flow, record, entry_data, kakao_network
):
    search, _, _ = kakao_network
    items = search.return_value[0]
    search.return_value = (items + [{**items[0], "id": "456"}], 1)
    assert (await flow._async_link_kakao(record, entry_data))[
        "step_id"
    ] == "animal_kakao"
    for choice in ("__previous__", "__next__", "invalid"):
        assert (await flow.async_step_animal_kakao({"selection": choice}))["errors"]


async def test_reconfigure_opens_editable_form_without_network(flow, entry_data):
    entry = MagicMock(data=entry_data, options={})
    flow.context["source"] = "reconfigure"
    with (
        patch.object(flow, "_get_reconfigure_entry", return_value=entry),
        patch(
            "custom_components.korea_incubator.animal_medical.coordinator.AnimalMedicalCoordinator._find",
            new_callable=AsyncMock,
        ) as find,
    ):
        result = await flow.async_step_reconfigure()
    assert result["step_id"] == "animal_medical"
    values = result["data_schema"]({})
    assert values["api_key"] == "key"
    assert values["road_address"] == "서울"
    find.assert_not_awaited()
    flow.hass.config_entries.async_update_entry.assert_not_called()


@pytest.mark.parametrize("error", [AnimalMedicalApiError("offline")])
async def test_reconfigure_errors_retain_edited_key(flow, entry_data, error):
    entry = MagicMock(data=entry_data, options={})
    flow.context["source"] = "reconfigure"
    flow._get_reconfigure_entry = MagicMock(return_value=entry)
    result = await flow.async_step_reconfigure()
    values = result["data_schema"]({})
    with (
        patch(
            "custom_components.korea_incubator.animal_medical.config_flow.async_get_clientsession"
        ),
        patch(
            "custom_components.korea_incubator.animal_medical.config_flow.async_fetch_institutions",
            new_callable=AsyncMock,
            side_effect=error,
        ),
    ):
        result = await flow.async_step_animal_medical({**values, "api_key": "edited"})
    assert result["errors"]["base"] == "animal_cannot_connect"
    assert result["data_schema"]({})["api_key"] == "edited"
    flow.hass.config_entries.async_update_entry.assert_not_called()


async def test_reconfigure_complete_and_preserve_identity(flow, entry_data, record):
    entry = MagicMock(
        data=entry_data,
        options={"scan_interval_minutes": 90, "naver_place_url": "1234"},
        entry_id="existing",
        unique_id="animal_hospital_3000000_A1",
    )
    flow.context["source"] = "reconfigure"
    flow._get_reconfigure_entry = MagicMock(return_value=entry)
    result = await flow.async_step_reconfigure()
    values = result["data_schema"]({})
    with (
        patch(
            "custom_components.korea_incubator.animal_medical.config_flow.async_get_clientsession"
        ),
        patch(
            "custom_components.korea_incubator.animal_medical.config_flow.async_fetch_institutions",
            new_callable=AsyncMock,
            return_value=([record], 1),
        ),
    ):
        await flow.async_step_animal_medical(
            {**values, "api_key": "new", "scan_interval_minutes": 15}
        )
        flow.hass.config_entries.async_entry_for_domain_unique_id.return_value = entry
        result = await flow.async_step_animal_medical_select(
            {"selection": "3000000:A1"}
        )
    assert result["step_id"] == "medical_links"
    flow.hass.config_entries.async_update_entry.assert_not_called()
    result = await flow.async_step_medical_links(
        {"kakao_place_id": "123", "naver_place_url": "18199503"}
    )
    assert result["reason"] == "reconfigure_successful"
    updates = flow.hass.config_entries.async_update_entry.call_args.kwargs
    assert updates["data"]["api_key"] == "new"
    assert updates["data"]["scan_interval_minutes"] == 15
    assert updates["data"]["kakao_place_id"] == "123"
    assert (
        updates["data"]["naver_place_url"]
        == "https://map.naver.com/p/entry/place/18199503"
    )
    assert "naver_place_url" not in updates["options"]
    assert updates["data"]["device_unique_id"] == "animal_hospital_3000000_A1"


async def test_reconfigure_other_service_aborts(flow):
    with patch.object(
        flow,
        "_get_reconfigure_entry",
        return_value=MagicMock(data={"service": "other"}),
    ):
        assert (await flow.async_step_reconfigure())[
            "reason"
        ] == "reconfigure_unsupported"
