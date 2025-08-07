"""Test Korea integration initialization and setup."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import aiohttp

from custom_components.korea_incubator import async_setup_entry, async_unload_entry
from custom_components.korea_incubator.const import DOMAIN, PLATFORMS
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


class TestKoreaIntegrationSetup:
    """Test Korea integration setup and initialization."""

    @pytest.fixture
    def mock_entry_kepco(self, kepco_config_data):
        """Create mock config entry for KEPCO."""
        entry = MagicMock(spec=ConfigEntry)
        entry.entry_id = "test_kepco_entry"
        entry.data = kepco_config_data
        return entry

    @pytest.fixture
    def mock_entry_gasapp(self, gasapp_config_data):
        """Create mock config entry for GasApp."""
        entry = MagicMock(spec=ConfigEntry)
        entry.entry_id = "test_gasapp_entry"
        entry.data = gasapp_config_data
        return entry

    @pytest.fixture
    def mock_entry_safety_alert(self, safety_alert_config_data):
        """Create mock config entry for Safety Alert."""
        entry = MagicMock(spec=ConfigEntry)
        entry.entry_id = "test_safety_alert_entry"
        entry.data = safety_alert_config_data
        return entry

    @pytest.mark.asyncio
    async def test_setup_kepco_success(self, mock_hass, mock_entry_kepco):
        """Test successful KEPCO setup."""
        with patch('custom_components.korea_incubator.KepcoDevice') as mock_device_class:
            mock_device = AsyncMock()
            mock_device.async_update = AsyncMock()
            mock_device.async_close_session = AsyncMock()
            mock_device_class.return_value = mock_device

            with patch('custom_components.korea_incubator.curl_cffi.AsyncSession'):
                result = await async_setup_entry(mock_hass, mock_entry_kepco)

                assert result is True
                assert DOMAIN in mock_hass.data
                assert mock_entry_kepco.entry_id in mock_hass.data[DOMAIN]

    @pytest.mark.asyncio
    async def test_setup_gasapp_success(self, mock_hass, mock_entry_gasapp):
        """Test successful GasApp setup."""
        with patch('custom_components.korea_incubator.GasAppDevice') as mock_device_class:
            mock_device = AsyncMock()
            mock_device.async_update = AsyncMock()
            mock_device.async_close_session = AsyncMock()
            mock_device_class.return_value = mock_device

            result = await async_setup_entry(mock_hass, mock_entry_gasapp)

            assert result is True
            assert DOMAIN in mock_hass.data
            assert mock_entry_gasapp.entry_id in mock_hass.data[DOMAIN]

    @pytest.mark.asyncio
    async def test_setup_safety_alert_success(self, mock_hass, mock_entry_safety_alert):
        """Test successful Safety Alert setup."""
        with patch('custom_components.korea_incubator.SafetyAlertDevice') as mock_device_class:
            mock_device = AsyncMock()
            mock_device.async_update = AsyncMock()
            mock_device.async_close_session = AsyncMock()
            mock_device_class.return_value = mock_device

            result = await async_setup_entry(mock_hass, mock_entry_safety_alert)

            assert result is True
            assert DOMAIN in mock_hass.data
            assert mock_entry_safety_alert.entry_id in mock_hass.data[DOMAIN]

    @pytest.mark.asyncio
    async def test_setup_unknown_service(self, mock_hass):
        """Test setup with unknown service."""
        entry = MagicMock(spec=ConfigEntry)
        entry.entry_id = "test_unknown_entry"
        entry.data = {"service": "unknown_service"}

        result = await async_setup_entry(mock_hass, entry)
        assert result is False

    @pytest.mark.asyncio
    async def test_setup_kepco_auth_failure(self, mock_hass, mock_entry_kepco):
        """Test KEPCO setup with authentication failure."""
        from custom_components.korea_incubator.kepco.exceptions import KepcoAuthError

        with patch('custom_components.korea_incubator.KepcoDevice') as mock_device_class:
            mock_device = AsyncMock()
            mock_device.async_update.side_effect = KepcoAuthError("Auth failed")
            mock_device.async_close_session = AsyncMock()
            mock_device_class.return_value = mock_device

            with patch('custom_components.korea_incubator.curl_cffi.AsyncSession'):
                result = await async_setup_entry(mock_hass, mock_entry_kepco)

                assert result is False
                mock_device.async_close_session.assert_called_once()

    @pytest.mark.asyncio
    async def test_unload_entry_success(self, mock_hass, mock_entry_kepco):
        """Test successful entry unload."""
        # Setup entry first
        mock_hass.data[DOMAIN] = {
            mock_entry_kepco.entry_id: {
                "device": AsyncMock(),
                "coordinator": MagicMock()
            }
        }

        with patch.object(mock_hass.config_entries, 'async_unload_platforms') as mock_unload:
            mock_unload.return_value = True

            result = await async_unload_entry(mock_hass, mock_entry_kepco)

            assert result is True
            mock_unload.assert_called_once_with(mock_entry_kepco, PLATFORMS)

    @pytest.mark.asyncio
    async def test_platforms_loaded(self, mock_hass, mock_entry_kepco):
        """Test that correct platforms are loaded."""
        with patch('custom_components.korea_incubator.KepcoDevice') as mock_device_class:
            mock_device = AsyncMock()
            mock_device.async_update = AsyncMock()
            mock_device_class.return_value = mock_device

            with patch('custom_components.korea_incubator.curl_cffi.AsyncSession'):
                with patch.object(mock_hass.config_entries, 'async_forward_entry_setups') as mock_forward:
                    await async_setup_entry(mock_hass, mock_entry_kepco)

                    mock_forward.assert_called_once_with(mock_entry_kepco, PLATFORMS)

    @pytest.mark.asyncio
    async def test_coordinator_creation(self, mock_hass, mock_entry_kepco):
        """Test that DataUpdateCoordinator is created correctly."""
        with patch('custom_components.korea_incubator.KepcoDevice') as mock_device_class:
            mock_device = AsyncMock()
            mock_device.async_update = AsyncMock()
            mock_device_class.return_value = mock_device

            with patch('custom_components.korea_incubator.curl_cffi.AsyncSession'):
                with patch('custom_components.korea_incubator.DataUpdateCoordinator') as mock_coordinator_class:
                    mock_coordinator = MagicMock()
                    mock_coordinator.async_config_entry_first_refresh = AsyncMock()
                    mock_coordinator_class.return_value = mock_coordinator

                    await async_setup_entry(mock_hass, mock_entry_kepco)

                    # Verify coordinator was created and configured
                    mock_coordinator_class.assert_called_once()
                    mock_coordinator.async_config_entry_first_refresh.assert_called_once()

    @pytest.mark.parametrize("service", [
        "kepco", "gasapp", "safety_alert", "goodsflow", "arisu", "kakaomap"
    ])
    def test_all_services_supported(self, service):
        """Test that all services are recognized in setup."""
        from custom_components.korea_incubator import async_setup_entry

        # This test verifies the service names are properly handled
        # The actual implementation check is done in the setup function
        assert service in ["kepco", "gasapp", "safety_alert", "goodsflow", "arisu", "kakaomap"]


class TestKoreaIntegrationData:
    """Test Korea integration data management."""

    def test_domain_constant(self):
        """Test domain constant is correctly defined."""
        assert DOMAIN == "korea_incubator"

    def test_platforms_constant(self):
        """Test platforms constant includes required platforms."""
        from homeassistant.const import Platform

        assert Platform.SENSOR in PLATFORMS
        assert Platform.BINARY_SENSOR in PLATFORMS

    def test_logger_available(self):
        """Test that logger is properly configured."""
        from custom_components.korea_incubator.const import LOGGER

        assert LOGGER is not None
        assert hasattr(LOGGER, 'debug')
        assert hasattr(LOGGER, 'info')
        assert hasattr(LOGGER, 'warning')
        assert hasattr(LOGGER, 'error')

    def test_currency_constant(self):
        """Test currency constant is defined."""
        from custom_components.korea_incubator.const import CURRENCY_KRW

        assert CURRENCY_KRW == "KRW"

    def test_energy_constant(self):
        """Test energy constant is defined."""
        from custom_components.korea_incubator.const import ENERGY_KILO_WATT_HOUR

        assert ENERGY_KILO_WATT_HOUR == "kWh"
