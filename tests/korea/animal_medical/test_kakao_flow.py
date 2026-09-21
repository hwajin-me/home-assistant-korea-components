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


async def test_reconfigure_link_and_preserve_entry(flow, entry_data, record):
    entry = MagicMock(data=entry_data)
    flow.context["source"] = "reconfigure"
    with (
        patch.object(flow, "_get_reconfigure_entry", return_value=entry),
        patch.object(
            flow, "async_update_reload_and_abort", return_value={"type": "abort"}
        ) as update,
        patch(
            "custom_components.korea_incubator.animal_medical.coordinator.AnimalMedicalCoordinator._find",
            new_callable=AsyncMock,
            side_effect=[None, record],
        ),
    ):
        assert (await flow.async_step_reconfigure())["type"] == "abort"
        assert update.call_args.kwargs["data_updates"]["kakao_place_id"] == "123"
        assert update.call_args.kwargs["data_updates"]["api_key"] == "key"


@pytest.mark.parametrize("records", [[None, None], [AnimalMedicalApiError("offline")]])
async def test_reconfigure_errors(flow, entry_data, records):
    with (
        patch.object(
            flow, "_get_reconfigure_entry", return_value=MagicMock(data=entry_data)
        ),
        patch(
            "custom_components.korea_incubator.animal_medical.coordinator.AnimalMedicalCoordinator._find",
            new_callable=AsyncMock,
            side_effect=records,
        ),
    ):
        assert (await flow.async_step_reconfigure())["errors"][
            "base"
        ] == "animal_cannot_connect"


async def test_reconfigure_success_and_other_service(flow, entry_data, record):
    with (
        patch.object(
            flow, "_get_reconfigure_entry", return_value=MagicMock(data=entry_data)
        ),
        patch(
            "custom_components.korea_incubator.animal_medical.coordinator.AnimalMedicalCoordinator._find",
            new_callable=AsyncMock,
            return_value=record,
        ),
    ):
        assert (await flow.async_step_reconfigure())["data"]["kakao_place_id"] == "123"
    with patch.object(
        flow,
        "_get_reconfigure_entry",
        return_value=MagicMock(data={"service": "other"}),
    ):
        assert (await flow.async_step_reconfigure())["type"] == "abort"
