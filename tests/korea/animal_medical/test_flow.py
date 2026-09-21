"""Exercise search, selection, paging boundaries, retries and reauthentication."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.asyncio
from homeassistant.data_entry_flow import AbortFlow

from custom_components.korea_incubator.animal_medical.api import (
    AnimalMedicalApiError,
    AnimalMedicalAuthError,
)
from custom_components.korea_incubator.config_flow import KoreaOptionsFlow

MODULE = "custom_components.korea_incubator.animal_medical.config_flow"
SEARCH = {
    "api_key": "key",
    "institution_type": "hospital",
    "search_method": "road_address",
    "road_address": "서울",
}


@pytest.fixture
def fetch():
    with (
        patch(f"{MODULE}.async_get_clientsession", return_value=MagicMock()),
        patch(f"{MODULE}.async_fetch_institutions", new_callable=AsyncMock) as fetch,
    ):
        yield fetch


def choices(result):
    selector = next(iter(result["data_schema"].schema.values()))
    return {item["value"]: item["label"] for item in selector.config["options"]}


async def test_menu_and_defaults(flow):
    assert "animal_medical" in (await flow.async_step_user())["menu_options"]
    result = await flow.async_step_animal_medical()
    defaults = result["data_schema"]({"api_key": "key"})
    assert defaults["search_method"] == "road_address"
    assert defaults["institution_type"] == "hospital"
    assert "pageNo" not in defaults and "numOfRows" not in defaults


@pytest.mark.parametrize(
    "values,field,code",
    [
        ({**SEARCH, "api_key": " "}, "api_key", "animal_invalid_auth"),
        ({**SEARCH, "road_address": " "}, "road_address", "required_search_value"),
        (
            {**SEARCH, "search_method": "municipality_code"},
            "municipality_code",
            "required_search_value",
        ),
        (
            {
                **SEARCH,
                "search_method": "municipality_code",
                "municipality_code": "1100000000",
            },
            "municipality_code",
            "animal_invalid_code",
        ),
        (
            {
                **SEARCH,
                "search_method": "municipality_code",
                "municipality_code": "abcdefg",
            },
            "municipality_code",
            "animal_invalid_code",
        ),
    ],
)
async def test_invalid_search(flow, fetch, values, field, code):
    result = await flow.async_step_animal_medical(values)
    assert result["errors"] == {field: code}
    fetch.assert_not_awaited()


@pytest.mark.parametrize("method", ["road_address", "municipality_code"])
@pytest.mark.parametrize("kind", ["hospital", "pharmacy"])
async def test_search_registers_selected_identity(flow, fetch, record, method, kind):
    fetch.return_value = ([record], 1)
    result = await flow.async_step_animal_medical(
        {
            **SEARCH,
            "institution_type": kind,
            "search_method": method,
            "municipality_code": " 3000000 ",
            "road_address": " 서울 ",
        }
    )
    params = fetch.call_args.kwargs
    assert params["road_address"] == ("서울" if method == "road_address" else "")
    assert params["municipality_code"] == (
        "3000000" if method == "municipality_code" else ""
    )
    assert params["page"] == 1
    assert set(choices(result)) == {"3000000:A1", "__search__"}
    result = await flow.async_step_animal_medical_select({"selection": "3000000:A1"})
    assert result["type"] == "create_entry"
    assert result["data"]["municipality_code"] == "3000000"
    assert result["data"]["management_number"] == "A1"
    assert result["data"]["service"] == "animal_medical"
    assert "selected_page" not in result["data"]
    assert flow.unique_id == f"animal_{kind}_3000000_A1"


@pytest.mark.parametrize("language", ["ko", "en"])
async def test_next_previous_boundaries_and_search_again(flow, fetch, record, language):
    flow.hass.config.language = language
    fetch.return_value = ([record], 201)
    first = await flow.async_step_animal_medical(SEARCH)
    assert "__previous__" not in choices(first)
    second = await flow.async_step_animal_medical_select({"selection": "__next__"})
    assert fetch.call_args.kwargs["page"] == 2
    assert {"__previous__", "__next__"} <= choices(second).keys()
    third = await flow.async_step_animal_medical_select({"selection": "__next__"})
    assert "__next__" not in choices(third)
    assert third["description_placeholders"] == {
        "page": "3",
        "pages": "3",
        "total": "201",
    }
    await flow.async_step_animal_medical_select({"selection": "__previous__"})
    assert fetch.call_args.kwargs["page"] == 2
    search = await flow.async_step_animal_medical_select({"selection": "__search__"})
    assert search["step_id"] == "animal_medical"
    assert search["data_schema"]({})["road_address"] == "서울"
    await flow.async_step_animal_medical(SEARCH)
    assert fetch.call_args.kwargs["page"] == 1


@pytest.mark.parametrize("total,has_next", [(0, False), (100, False), (101, True)])
async def test_empty_or_unusable_results_and_paging(flow, fetch, total, has_next):
    fetch.return_value = (
        [{}, {"MNG_NO": "bad"}, {"MNG_NO": 3, "OPN_ATMY_GRP_CD": "3000000"}],
        total,
    )
    result = await flow.async_step_animal_medical(SEARCH)
    if has_next:
        assert "__next__" in choices(result)
        fetch.return_value = ([], 0)
        result = await flow.async_step_animal_medical_select({"selection": "__next__"})
        assert "__previous__" in choices(result)
        assert "__search__" in choices(result)
    else:
        assert result["errors"] == {"base": "animal_no_results"}


@pytest.mark.parametrize(
    "error,code",
    [
        (AnimalMedicalApiError("bad response"), "animal_cannot_connect"),
        (AnimalMedicalAuthError("bad key"), "animal_invalid_auth"),
    ],
)
async def test_failed_page_can_be_retried_with_full_form(
    flow, fetch, record, error, code
):
    fetch.return_value = ([record], 101)
    await flow.async_step_animal_medical(SEARCH)
    fetch.side_effect = error
    result = await flow.async_step_animal_medical_select({"selection": "__next__"})
    assert result["errors"] == {"base": code}
    assert flow._animal_medical_page == 1
    values = result["data_schema"]({})
    assert set(SEARCH) <= values.keys()
    fetch.side_effect = None
    result = await flow.async_step_animal_medical(values)
    assert result["step_id"] == "animal_medical_select"


@pytest.mark.parametrize("choice", ["missing", "__previous__", "__next__"])
async def test_invalid_stale_selection(flow, fetch, record, choice):
    fetch.return_value = ([record], 1)
    await flow.async_step_animal_medical(SEARCH)
    result = await flow.async_step_animal_medical_select({"selection": choice})
    assert result["errors"] == {"selection": "animal_invalid_selection"}
    assert fetch.await_count == 1


async def test_duplicate_registration_aborts(flow, fetch, record):
    fetch.return_value = ([record], 1)
    await flow.async_step_animal_medical(SEARCH)
    flow.hass.config_entries.async_entry_for_domain_unique_id.return_value = MagicMock(
        source="user"
    )
    with pytest.raises(AbortFlow, match="already_configured"):
        await flow.async_step_animal_medical_select({"selection": "3000000:A1"})


async def test_missing_name_address_and_status_labels(flow, fetch, record):
    del record["BPLC_NM"]
    del record["ROAD_NM_ADDR"]
    del record["SALS_STTS_NM"]
    record["LOTNO_ADDR"] = "지번주소"
    fetch.return_value = ([record], 1)
    result = await flow.async_step_animal_medical(SEARCH)
    assert "지번주소" in choices(result)["3000000:A1"]
    result = await flow.async_step_animal_medical_select({"selection": "3000000:A1"})
    assert result["step_id"] == "animal_kakao"  # Missing name cannot auto-match.
    result = await flow.async_step_animal_kakao({"selection": "123"})
    assert result["title"] == "A1"


async def test_reauth_form_and_other_services(flow):
    result = await flow.async_step_reauth({"service": "animal_medical"})
    assert result["step_id"] == "animal_medical_reauth"
    result = await flow.async_step_reauth({"service": "other"})
    assert result["reason"] == "animal_reauth_unsupported"


@pytest.mark.parametrize(
    "key,error,expected",
    [
        (" ", None, "animal_invalid_auth"),
        ("new", AnimalMedicalAuthError(), "animal_invalid_auth"),
        ("new", AnimalMedicalApiError(), "animal_cannot_connect"),
        (" new ", None, None),
    ],
)
async def test_reauth_validation_update_and_reload(
    flow, fetch, entry_data, key, error, expected
):
    entry = MagicMock(data=entry_data, entry_id="entry", domain="korea_incubator")
    flow.context = {"source": "reauth", "entry_id": "entry"}
    flow.hass.config_entries.async_get_known_entry.return_value = entry
    fetch.side_effect = error
    fetch.return_value = ([], 0)
    result = await flow.async_step_animal_medical_reauth({"api_key": key})
    if expected:
        assert result["errors"] == {"base": expected}
        flow.hass.config_entries.async_update_entry.assert_not_called()
    else:
        assert result["reason"] == "reauth_successful"
        assert flow.hass.config_entries.async_update_entry.call_args.kwargs["data"] == {
            **entry_data,
            "api_key": "new",
        }
        flow.hass.config_entries.async_schedule_reload.assert_called_once_with("entry")


async def test_options_interval(entry_data):
    options = KoreaOptionsFlow(MagicMock(data=entry_data, options={}))
    result = await options.async_step_init()
    assert result["data_schema"]({})["scan_interval_minutes"] == 60
    result = await options.async_step_animal_medical_options(
        {"scan_interval_minutes": 15}
    )
    assert result["data"] == {"scan_interval_minutes": 15}


async def test_saving_unchanged_options_also_reloads(entry_data, animal_hass):
    entry = MagicMock(
        data=entry_data, options={"scan_interval_minutes": 15}, entry_id="entry"
    )
    options = KoreaOptionsFlow(entry)
    options.hass = animal_hass
    await options.async_step_animal_medical_options({"scan_interval_minutes": 15})
    animal_hass.config_entries.async_schedule_reload.assert_called_once_with("entry")


@pytest.mark.parametrize("interval", [1, 15, 1440])
async def test_config_interval_saved_not_sent_to_api(flow, fetch, record, interval):
    fetch.return_value = ([record], 1)
    form = await flow.async_step_animal_medical()
    values = form["data_schema"]({**SEARCH, "scan_interval_minutes": interval})
    await flow.async_step_animal_medical(values)
    assert "scan_interval_minutes" not in fetch.call_args.kwargs
    result = await flow.async_step_animal_medical_select({"selection": "3000000:A1"})
    assert result["data"]["scan_interval_minutes"] == interval


@pytest.mark.parametrize("interval", [0, -1, 1441, "bad"])
async def test_config_interval_rejects_invalid_values(flow, interval):
    import voluptuous as vol

    result = await flow.async_step_animal_medical()
    with pytest.raises(vol.Invalid):
        result["data_schema"]({**SEARCH, "scan_interval_minutes": interval})


async def test_search_error_detail_in_form_and_log(flow, fetch, caplog):
    fetch.side_effect = AnimalMedicalApiError("daily quota exceeded (22): test detail")
    result = await flow.async_step_animal_medical(SEARCH)
    assert result["description_placeholders"]["error"] == str(fetch.side_effect)
    assert "page 1" in caplog.text
    assert "daily quota exceeded (22)" in caplog.text


async def test_reauth_error_detail_in_form_and_log(flow, fetch, entry_data, caplog):
    flow.context = {"source": "reauth", "entry_id": "entry"}
    flow.hass.config_entries.async_get_known_entry.return_value = MagicMock(
        data=entry_data
    )
    fetch.side_effect = AnimalMedicalAuthError("30: key expired")
    result = await flow.async_step_animal_medical_reauth({"api_key": "new"})
    assert result["description_placeholders"]["error"] == "30: key expired"
    assert "30: key expired" in caplog.text
