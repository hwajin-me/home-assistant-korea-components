"""Tests for CJ O-NE setup in the Korea integration."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.korea_incubator import (
    _async_cj_options_updated,
    async_setup_entry,
)
from custom_components.korea_incubator.const import DOMAIN


@pytest.mark.asyncio
async def test_setup_stores_coordinator_and_forwards_sensor(mock_hass) -> None:
    entry = MagicMock()
    entry.entry_id = "cj_entry"
    entry.data = {
        "service": "cj_one_delivery",
        "phone_number": "010-1234-5678",
        "user_id": "user",
        "access_token": "access",
        "refresh_token": "refresh",
    }
    entry.options = {"scan_interval_minutes": 20}
    coordinator = MagicMock()
    coordinator.async_config_entry_first_refresh = AsyncMock()
    mock_hass.config_entries.async_forward_entry_setups = AsyncMock()

    with (
        patch("custom_components.korea_incubator.async_get_clientsession"),
        patch(
            "custom_components.korea_incubator.cj_one_delivery.api.CJOneDeliveryClient"
        ) as client_class,
        patch(
            "custom_components.korea_incubator.cj_one_delivery.coordinator.CJOneDeliveryCoordinator",
            return_value=coordinator,
        ),
        patch(
            "custom_components.korea_incubator.async_setup_llm_api",
            new=AsyncMock(return_value=None),
        ),
    ):
        result = await async_setup_entry(mock_hass, entry)

    assert result is True
    assert mock_hass.data[DOMAIN][entry.entry_id]["coordinator"] is coordinator
    coordinator.async_config_entry_first_refresh.assert_awaited_once()
    mock_hass.config_entries.async_forward_entry_setups.assert_awaited_once()
    assert "completed_retention_days" not in client_class.call_args.kwargs


@pytest.mark.asyncio
async def test_token_data_update_does_not_reload_entry(mock_hass) -> None:
    entry = MagicMock()
    entry.entry_id = "cj_entry"
    entry.options = {"scan_interval_minutes": 30}
    coordinator = MagicMock()
    coordinator.loaded_options = dict(entry.options)
    coordinator.async_request_refresh = AsyncMock()
    mock_hass.data = {DOMAIN: {entry.entry_id: {"coordinator": coordinator}}}
    mock_hass.config_entries.async_reload = AsyncMock()

    await _async_cj_options_updated(mock_hass, entry)

    mock_hass.config_entries.async_reload.assert_not_awaited()
    coordinator.apply_options.assert_not_called()
    coordinator.async_request_refresh.assert_not_awaited()


@pytest.mark.asyncio
async def test_option_change_updates_coordinator_without_reload(mock_hass) -> None:
    entry = MagicMock()
    entry.entry_id = "cj_entry"
    entry.options = {"scan_interval_minutes": 20}
    coordinator = MagicMock()
    coordinator.loaded_options = {"scan_interval_minutes": 30}
    coordinator.async_request_refresh = AsyncMock()
    mock_hass.data = {DOMAIN: {entry.entry_id: {"coordinator": coordinator}}}
    mock_hass.config_entries.async_reload = AsyncMock()

    await _async_cj_options_updated(mock_hass, entry)

    mock_hass.config_entries.async_reload.assert_not_awaited()
    coordinator.apply_options.assert_called_once_with()
    coordinator.async_request_refresh.assert_awaited_once_with()
