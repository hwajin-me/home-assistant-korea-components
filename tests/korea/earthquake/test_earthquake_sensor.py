"""Tests for earthquake event entities."""

from unittest.mock import MagicMock, patch

from custom_components.korea_incubator.earthquake.sensor import EarthquakeEvent
from custom_components.korea_incubator.event import _migrate_earthquake_unique_id


def test_unique_id_is_scoped_to_config_entry():
    first = EarthquakeEvent(MagicMock(), "entry-one", 37.5, 127.0, 200, 3.0)
    second = EarthquakeEvent(MagicMock(), "entry-two", 37.5, 127.0, 200, 3.0)

    assert first.unique_id == "korea_incubator_entry-one_earthquake_event"
    assert second.unique_id == "korea_incubator_entry-two_earthquake_event"
    assert first.unique_id != second.unique_id
    assert first.device_info["identifiers"] != second.device_info["identifiers"]


def test_legacy_unique_id_is_migrated_for_owning_entry():
    hass = MagicMock()
    entry = MagicMock(entry_id="entry-one")
    registry = MagicMock()
    entity_entry = MagicMock(
        domain="event",
        platform="korea_incubator",
        unique_id="korea_incubator_earthquake_event",
        entity_id="event.jijin_gyeongbo",
    )

    with (
        patch(
            "custom_components.korea_incubator.event.er.async_get",
            return_value=registry,
        ),
        patch(
            "custom_components.korea_incubator.event.er.async_entries_for_config_entry",
            return_value=[entity_entry],
        ),
    ):
        _migrate_earthquake_unique_id(hass, entry)

    registry.async_update_entity.assert_called_once_with(
        "event.jijin_gyeongbo",
        new_unique_id="korea_incubator_entry-one_earthquake_event",
    )
