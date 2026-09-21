"""Refresh across result pages, mutations, failures and recovery."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState

pytestmark = pytest.mark.asyncio
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.korea_incubator.animal_medical.api import (
    AnimalMedicalApiError,
    AnimalMedicalAuthError,
)
from custom_components.korea_incubator.animal_medical.coordinator import (
    AnimalMedicalCoordinator,
)

MODULE = "custom_components.korea_incubator.animal_medical.coordinator"


@pytest.fixture
def fetch():
    with (
        patch(f"{MODULE}.async_get_clientsession", return_value=MagicMock()),
        patch(f"{MODULE}.async_fetch_institutions", new_callable=AsyncMock) as fetch,
    ):
        yield fetch


@pytest.fixture
def coordinator(animal_hass, entry_data):
    return AnimalMedicalCoordinator(animal_hass, entry_data)


async def test_refresh_starts_at_one_with_narrow_filters(coordinator, fetch, record):
    fetch.return_value = ([record], 1)
    assert await coordinator._async_update_data() == record
    assert coordinator.update_interval == timedelta(hours=1)
    assert fetch.call_args.kwargs == {
        "page": 1,
        "municipality_code": "3000000",
        "business_name": "동물병원",
    }


async def test_target_moves_to_later_page(coordinator, fetch, record):
    fetch.side_effect = [
        ([{**record, "MNG_NO": "other"}], 201),
        ([{**record, "MNG_NO": "another"}], 201),
        ([record], 201),
    ]
    assert await coordinator._async_update_data() == record
    assert [c.kwargs["page"] for c in fetch.call_args_list] == [1, 2, 3]


async def test_renamed_relocated_closed_record_found_then_name_cached(
    coordinator, fetch, record
):
    changed = {
        **record,
        "BPLC_NM": "새이름",
        "ROAD_NM_ADDR": "새주소",
        "SALS_STTS_NM": "폐업",
    }
    fetch.side_effect = [
        ([], 0),
        ([{**record, "MNG_NO": "other"}], 101),
        ([changed], 101),
    ]
    assert await coordinator._async_update_data() == changed
    assert [
        (c.kwargs["page"], c.kwargs["business_name"]) for c in fetch.call_args_list
    ] == [
        (1, "동물병원"),
        (1, ""),
        (2, ""),
    ]
    fetch.side_effect = None
    fetch.return_value = ([changed], 1)
    await coordinator._async_update_data()
    assert fetch.call_args.kwargs["business_name"] == "새이름"


@pytest.mark.parametrize("name", ["동물병원", ""])
async def test_missing_record_is_unavailable_not_wrong_business(
    coordinator, fetch, record, name
):
    coordinator._business_name = name
    fetch.return_value = ([{**record, "OPN_ATMY_GRP_CD": "3010000"}], 1)
    with pytest.raises(UpdateFailed, match="no longer listed"):
        await coordinator._async_update_data()
    assert fetch.await_count == (2 if name else 1)


@pytest.mark.parametrize(
    "responses",
    [
        [([], 200)],
        [([{"MNG_NO": "other"}], 300), ([{"MNG_NO": "other"}], 300)],
    ],
)
async def test_incomplete_or_repeated_pages_terminate(coordinator, fetch, responses):
    fetch.side_effect = responses
    with pytest.raises(UpdateFailed, match="Incomplete or repeated"):
        await coordinator._async_update_data()
    assert fetch.await_count == len(responses)


async def test_auth_failure_requests_reauth(coordinator, fetch):
    fetch.side_effect = AnimalMedicalAuthError("expired")
    with pytest.raises(ConfigEntryAuthFailed, match="expired"):
        await coordinator._async_update_data()


async def test_null_business_name_does_not_break_next_update(
    coordinator, fetch, record
):
    fetch.return_value = ([{**record, "BPLC_NM": None}], 1)
    await coordinator._async_update_data()
    await coordinator._async_update_data()
    assert fetch.call_args.kwargs["business_name"] == ""


async def test_first_refresh_failure_retries_setup(coordinator, fetch):
    coordinator.config_entry = MagicMock(
        state=ConfigEntryState.SETUP_IN_PROGRESS, pref_disable_polling=False
    )
    fetch.side_effect = AnimalMedicalApiError("offline")
    with pytest.raises(ConfigEntryNotReady):
        await coordinator.async_config_entry_first_refresh()


async def test_failed_refresh_keeps_last_data_and_recovers(coordinator, fetch, record):
    fetch.return_value = ([record], 1)
    await coordinator.async_refresh()
    assert coordinator.last_update_success
    fetch.side_effect = AnimalMedicalApiError("offline")
    await coordinator.async_refresh()
    assert not coordinator.last_update_success
    assert coordinator.next_refresh is None
    assert coordinator.data == record
    fetch.side_effect = None
    fetch.return_value = ([{**record, "SALS_STTS_NM": "폐업"}], 1)
    await coordinator.async_refresh()
    assert coordinator.last_update_success
    assert coordinator.data["SALS_STTS_NM"] == "폐업"


async def test_hourly_schedule_and_shutdown(coordinator, fetch, record):
    fetch.return_value = ([record], 1)
    with patch.object(coordinator.hass.loop, "call_at") as track:
        unsub = coordinator.async_add_listener(MagicMock())
        assert track.call_count == 1
        deadline = track.call_args.args[0]
        assert 3599 <= deadline - coordinator.hass.loop.time() <= 3601
        await coordinator.async_shutdown()
        track.return_value.cancel.assert_called_once()
        unsub()
