"""Validate routing, setup/unload, sensors and identity at the integration boundary."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState

pytestmark = pytest.mark.asyncio
from homeassistant.const import Platform
from homeassistant.exceptions import ConfigEntryNotReady

from custom_components.korea_incubator import async_setup_entry, async_unload_entry
from custom_components.korea_incubator.animal_medical.sensor import AnimalMedicalSensor
from custom_components.korea_incubator.const import DOMAIN
from custom_components.korea_incubator.sensor import async_setup_entry as setup_sensors

COORD = "custom_components.korea_incubator.animal_medical.coordinator.AnimalMedicalCoordinator"


@pytest.mark.parametrize("kind", ["hospital", "pharmacy"])
async def test_setup_sensor_refresh_unload(animal_hass, entry_data, record, kind):
    entry_data["institution_type"] = kind
    entry = MagicMock(data=entry_data, entry_id="entry")
    coordinator = MagicMock(data=record, last_update_success=True)
    coordinator.async_config_entry_first_refresh = AsyncMock()
    with patch(COORD, return_value=coordinator) as factory:
        assert await async_setup_entry(animal_hass, entry)
    factory.assert_called_once_with(animal_hass, entry_data, config_entry=entry)
    coordinator.async_config_entry_first_refresh.assert_awaited_once()
    animal_hass.config_entries.async_forward_entry_setups.assert_awaited_once_with(
        entry, [Platform.SENSOR]
    )
    add_entities = MagicMock()
    await setup_sensors(animal_hass, entry, add_entities)
    sensor = add_entities.call_args.args[0][0]
    assert sensor.available
    assert sensor.native_value is None  # License status is not current opening state.
    assert sensor.unique_id == f"{DOMAIN}_animal_{kind}_3000000_A1"
    assert sensor.device_info["identifiers"] == {(DOMAIN, f"animal_{kind}_3000000_A1")}
    assert sensor.translation_key == "animal_medical_status"
    assert sensor.extra_state_attributes["phone"] == "02-123-4567"
    assert sensor.extra_state_attributes["coordinate_system"] == "EPSG:5174"
    assert sensor.extra_state_attributes["api_record"] == record
    assert sensor.extra_state_attributes["api_record"] is not record
    coordinator.data = {**record, "SALS_STTS_NM": "폐업", "TELNO": "new"}
    assert sensor.native_value is None
    assert sensor.extra_state_attributes["phone"] == "new"
    coordinator.last_update_success = False
    assert not sensor.available
    assert await async_unload_entry(animal_hass, entry)
    assert "entry" not in animal_hass.data[DOMAIN]
    animal_hass.config_entries.async_unload_platforms.assert_awaited_once_with(
        entry, [Platform.SENSOR]
    )


async def test_unload_failure_retains_store(animal_hass, entry_data):
    entry = MagicMock(data=entry_data, entry_id="entry")
    animal_hass.data[DOMAIN] = {"entry": {"coordinator": MagicMock()}}
    animal_hass.config_entries.async_unload_platforms.return_value = False
    assert not await async_unload_entry(animal_hass, entry)
    assert "entry" in animal_hass.data[DOMAIN]


async def test_setup_failure_does_not_register_entities(animal_hass, entry_data):
    entry = MagicMock(data=entry_data, entry_id="entry")
    coordinator = MagicMock()
    coordinator.async_config_entry_first_refresh = AsyncMock(
        side_effect=ConfigEntryNotReady()
    )
    with patch(COORD, return_value=coordinator), pytest.raises(ConfigEntryNotReady):
        await async_setup_entry(animal_hass, entry)
    animal_hass.config_entries.async_forward_entry_setups.assert_not_awaited()
    assert "entry" not in animal_hass.data.get(DOMAIN, {})


async def test_sensor_before_data(entry_data):
    sensor = AnimalMedicalSensor(
        MagicMock(data=None, last_update_success=False), entry_data
    )
    assert sensor.native_value is None
    assert sensor.extra_state_attributes["api_record"] == {}
    assert not sensor.available


async def test_search_second_page_to_real_coordinator_refresh(
    flow, animal_hass, record, memory_store
):
    """A selected second-page result must refresh from narrowed page one."""
    responses = [
        {"totalCount": 101, "items": {"item": [{**record, "MNG_NO": "other"}]}},
        {"totalCount": 101, "items": {"item": [record]}},
        {"totalCount": 1, "items": {"item": [{**record, "SALS_STTS_NM": "폐업"}]}},
    ]
    response = MagicMock(status=200)
    response.text = AsyncMock(
        side_effect=[
            json.dumps({"response": {"header": {"resultCode": "00"}, "body": body}})
            for body in responses
        ]
    )
    session = MagicMock()
    session.get.return_value.__aenter__ = AsyncMock(return_value=response)
    session.get.return_value.__aexit__ = AsyncMock(return_value=None)
    with (
        patch(
            "custom_components.korea_incubator.animal_medical.config_flow.async_get_clientsession",
            return_value=session,
        ),
        patch(
            "custom_components.korea_incubator.animal_medical.coordinator.async_get_clientsession",
            return_value=session,
        ),
    ):
        await flow.async_step_animal_medical(
            {
                "api_key": "key",
                "institution_type": "hospital",
                "search_method": "road_address",
                "road_address": "서울",
            }
        )
        await flow.async_step_animal_medical_select({"selection": "__next__"})
        result = await flow.async_step_animal_medical_select(
            {"selection": "3000000:A1"}
        )
        entry = MagicMock(
            data=result["data"],
            entry_id="entry",
            state=ConfigEntryState.SETUP_IN_PROGRESS,
            pref_disable_polling=False,
        )
        assert await async_setup_entry(animal_hass, entry)
        coordinator = animal_hass.data[DOMAIN]["entry"]["coordinator"]
        assert coordinator.data["SALS_STTS_NM"] == "폐업"
        params = [c.kwargs["params"] for c in session.get.call_args_list]
        assert [p["pageNo"] for p in params] == ["1", "2", "1"]
        assert params[2]["cond[BPLC_NM::LIKE]"] == "동물병원"
        assert params[2]["cond[OPN_ATMY_GRP_CD::EQ]"] == "3000000"
        assert "cond[ROAD_NM_ADDR::LIKE]" not in params[2]
        assert "cond[SALS_STTS_CD::EQ]" not in params[2]
        await coordinator.async_shutdown()
