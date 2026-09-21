"""Shared realistic animal-data fixtures."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from homeassistant.core import HomeAssistant

from custom_components.korea_incubator.config_flow import KoreaConfigFlow


@pytest.fixture(autouse=True)
def kakao_network():
    """No external network in flow/coordinator tests; API tests mock HTTP directly."""
    prefix = "custom_components.korea_incubator.animal_medical"
    with (
        patch(f"{prefix}.kakao_flow.async_search", new_callable=AsyncMock) as search,
        patch(f"{prefix}.kakao_flow.async_place", new_callable=AsyncMock) as place,
        patch(f"{prefix}.coordinator.async_place", new_callable=AsyncMock) as refresh,
        patch(f"{prefix}.kakao_flow.async_get_clientsession", return_value=MagicMock()),
    ):
        search.return_value = (
            [
                {
                    "id": "123",
                    "name": "동물병원",
                    "address": "서울 종로구 사직로 1",
                    "phone": "02-123-4567",
                }
            ],
            1,
        )
        place.return_value = refresh.return_value = {
            "summary": {"confirm_id": "123"},
            "open_hours": {},
        }
        yield search, place, refresh


@pytest.fixture
def record():
    return {
        "MNG_NO": "A1",
        "OPN_ATMY_GRP_CD": "3000000",
        "BPLC_NM": "동물병원",
        "ROAD_NM_ADDR": "서울특별시 종로구 사직로 1",
        "SALS_STTS_NM": "영업/정상",
        "TELNO": "02-123-4567",
    }


@pytest.fixture
def entry_data():
    return {
        "service": "animal_medical",
        "api_key": "key",
        "institution_type": "hospital",
        "municipality_code": "3000000",
        "management_number": "A1",
        "business_name": "동물병원",
        "road_address": "서울",
        "selected_page": 3,
    }


@pytest_asyncio.fixture
async def animal_hass():
    hass = MagicMock(spec=HomeAssistant)
    hass.data = {}
    hass.config = MagicMock(language="en")
    hass.loop = asyncio.get_running_loop()
    hass.is_stopping = False
    hass.is_running = True
    hass.config_entries = MagicMock()
    hass.services = MagicMock()
    hass.config_entries.flow.async_progress_by_handler.return_value = []
    hass.config_entries.async_entry_for_domain_unique_id.return_value = None
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    return hass


@pytest.fixture(autouse=True)
def compact_registry():
    with patch(
        "custom_components.korea_incubator.animal_medical.compact_sensor.er.async_get"
    ) as get:
        get.return_value.entities.get_entries_for_config_entry_id.return_value = []
        yield get.return_value


@pytest.fixture
def flow(animal_hass):
    flow = KoreaConfigFlow()
    flow.hass = animal_hass
    flow.context = {"source": "user"}
    flow.handler = "korea_incubator"
    return flow


@pytest.fixture
def memory_store():
    with patch(
        "custom_components.korea_incubator.animal_medical.coordinator.Store"
    ) as factory:
        store = factory.return_value
        store.async_load = AsyncMock(return_value=None)
        store.async_save = AsyncMock()
        yield store
