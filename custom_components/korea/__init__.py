from datetime import timedelta

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, LOGGER
from .kepco.api import KepcoApiClient
from .kepco.device import KepcoDevice
from .kepco.exceptions import KepcoAuthError

PLATFORMS = ["sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the Korea platform from a config entry."""
    service = entry.data.get("service")

    if service == "kepco":
        device = KepcoDevice(
            hass,
            entry.entry_id,
            entry.data.get(CONF_USERNAME),
            entry.data.get(CONF_PASSWORD),
            aiohttp.ClientSession()  # Pass a new session to the device
        )
        # Initial login and data fetch
        try:
            await device.api_client.async_login(
                entry.data.get(CONF_USERNAME), entry.data.get(CONF_PASSWORD)
            )
            await device.async_update()
        except KepcoAuthError as err:
            LOGGER.error(f"Authentication failed during setup for KEPCO: {err}")
            await device.async_close_session()
            return False
        except Exception as err:
            LOGGER.error(f"Error during initial data fetch for KEPCO: {err}")
            await device.async_close_session()
            return False

        async def async_update_data():
            """Fetch data from KEPCO API using the device."""
            try:
                await device.async_update()
                return device.data
            except KepcoAuthError as err:
                raise UpdateFailed(f"Authentication failed for KEPCO: {err}") from err
            except Exception as err:
                raise UpdateFailed(f"Error communicating with KEPCO API: {err}") from err

    else:
        LOGGER.error(f"Unknown service: {service}")
        return False

    coordinator = DataUpdateCoordinator(
        hass,
        LOGGER,
        name=f"{DOMAIN}_{service}",
        update_method=async_update_data,
        update_interval=timedelta(minutes=15),
    )

    # Store the device instance on the coordinator
    coordinator.device = device

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        if hasattr(coordinator, "device") and coordinator.device:
            await coordinator.device.async_close_session()

    return unload_ok
