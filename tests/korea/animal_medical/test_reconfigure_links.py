"""Transactional map editing and HTTP form serialization regressions."""

from unittest.mock import MagicMock

import pytest
from homeassistant.helpers.data_entry_flow import FlowManagerIndexView

from custom_components.korea_incubator.animal_medical.kakao import KakaoError

pytestmark = pytest.mark.asyncio


async def prepare(flow, entry_data, changed=False):
    entry = MagicMock(data=entry_data, options={"naver_place_url": "18199503"})
    flow.context["source"] = "reconfigure"
    flow._get_reconfigure_entry = MagicMock(return_value=entry)
    flow._kakao_entry = {**entry_data}
    if changed:
        flow._kakao_entry["management_number"] = "OTHER"
    flow._finish_service_entry = MagicMock(return_value={"type": "abort"})
    return await flow._async_kakao_finish("123")


@pytest.mark.parametrize("changed", [False, True])
async def test_links_prefill_and_no_early_save(flow, entry_data, changed):
    form = await prepare(flow, entry_data, changed)
    payload = FlowManagerIndexView(MagicMock())._prepare_result_json(form)
    assert {field["name"] for field in payload["data_schema"]} == {
        "kakao_place_id",
        "naver_place_url",
    }
    assert form["data_schema"]({})["naver_place_url"] == ("" if changed else "18199503")
    flow._finish_service_entry.assert_not_called()


@pytest.mark.parametrize(
    "kakao,naver,field",
    [
        ("bad", "", "kakao_place_id"),
        ("１２３", "", "kakao_place_id"),
        ("123", "https://evil.test/1", "naver_place_url"),
    ],
)
async def test_links_invalid_inputs_do_not_save(flow, entry_data, kakao, naver, field):
    await prepare(flow, entry_data)
    result = await flow.async_step_medical_links(
        {"kakao_place_id": kakao, "naver_place_url": naver}
    )
    assert field in result["errors"]
    FlowManagerIndexView(MagicMock())._prepare_result_json(result)
    flow._finish_service_entry.assert_not_called()


async def test_links_api_error_retry_and_clear(flow, entry_data, kakao_network):
    await prepare(flow, entry_data)
    kakao_network[1].side_effect = KakaoError("offline")
    result = await flow.async_step_medical_links(
        {"kakao_place_id": "456", "naver_place_url": ""}
    )
    assert result["errors"] == {"kakao_place_id": "animal_kakao_error"}
    assert result["description_placeholders"]["error"] == "offline"
    flow._finish_service_entry.assert_not_called()
    kakao_network[1].side_effect = None
    await flow.async_step_medical_links(
        {"kakao_place_id": "456", "naver_place_url": ""}
    )
    data = flow._finish_service_entry.call_args.kwargs["data"]
    assert data["kakao_place_id"] == "456"
    assert data["naver_place_url"] == ""


async def test_medical_reauth_dispatcher_rejects_unrelated_service(flow):
    from custom_components.korea_incubator.animal_medical.config_flow import (
        AnimalMedicalFlow,
    )

    result = await AnimalMedicalFlow.async_step_reauth(flow, {"service": "other"})
    assert result["reason"] == "animal_reauth_unsupported"


async def test_medical_entity_identity_survives_reselection():
    from custom_components.korea_incubator.animal_medical.sensor import (
        institution_identifier,
    )

    assert (
        institution_identifier(
            {
                "service": "pharmacy",
                "hpid": "new",
                "device_unique_id": "pharmacy_original",
            }
        )
        == "pharmacy_original"
    )
