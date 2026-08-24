"""Tests for the Korea binary sensor platform dispatcher."""

from unittest.mock import MagicMock

import pytest

from custom_components.korea_incubator.binary_sensor import async_setup_entry
from custom_components.korea_incubator.const import DOMAIN


@pytest.mark.asyncio
async def test_setup_airkorea_without_legacy_device(mock_hass, mock_coordinator):
    """AirKorea uses its coordinator directly and creates its actual class."""
    entry = MagicMock()
    entry.entry_id = "test_airkorea_entry"
    entry.data = {"service": "airkorea", "sido": "서울"}
    mock_coordinator.data = {"forecast": []}
    mock_hass.data[DOMAIN] = {
        entry.entry_id: {
            "coordinator": mock_coordinator,
            "stations": [{"stationName": "용산구"}],
        }
    }
    add_entities = MagicMock()

    await async_setup_entry(mock_hass, entry, add_entities)

    entities = add_entities.call_args[0][0]
    assert len(entities) == 1
    assert entities[0].__class__.__name__ == "AirAlertBinarySensor"
    assert entities[0]._sido == "서울"
