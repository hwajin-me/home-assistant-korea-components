"""Tests for shared Public Data Portal config-flow defaults."""

from types import SimpleNamespace

from custom_components.korea_incubator.public_data import configured_data_go_kr_api_key


def test_configured_data_go_kr_api_key_uses_existing_public_data_entry() -> None:
    """A saved portal key is offered to another public-data service."""
    entries = [
        SimpleNamespace(data={"service": "school", "api_key": "neis-key"}, options={}),
        SimpleNamespace(
            data={"service": "airkorea", "api_key": "saved-key"}, options={}
        ),
    ]
    hass = SimpleNamespace(
        config_entries=SimpleNamespace(async_entries=lambda domain: entries)
    )

    assert configured_data_go_kr_api_key(hass) == "saved-key"


def test_configured_data_go_kr_api_key_prefers_an_updated_option() -> None:
    """The default reflects an API key changed through a service's options."""
    entry = SimpleNamespace(
        data={"service": "weather_warning", "api_key": "old-key"},
        options={"api_key": "new-key"},
    )
    hass = SimpleNamespace(
        config_entries=SimpleNamespace(async_entries=lambda domain: [entry])
    )

    assert configured_data_go_kr_api_key(hass) == "new-key"
