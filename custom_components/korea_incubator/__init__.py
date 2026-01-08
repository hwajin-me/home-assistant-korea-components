from __future__ import annotations

from datetime import timedelta
from typing import Dict, Any, Union

import aiohttp
import curl_cffi
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .arisu.device import ArisuDevice
from .arisu.exceptions import ArisuAuthError
from .const import DOMAIN, LOGGER, PLATFORMS
from .gasapp.device import GasAppDevice
from .gasapp.exceptions import GasAppAuthError
from .goodsflow.device import GoodsFlowDevice
from .goodsflow.exceptions import GoodsFlowAuthError
from .kakaomap.device import KakaoMapDevice
from .kakaomap.exceptions import KakaoMapConnectionError, KakaoMapDataError
from .kepco.api import KepcoApiClient
from .kepco.device import KepcoDevice
from .kepco.exceptions import KepcoAuthError
from .safety_alert.device import SafetyAlertDevice
from .safety_alert.exceptions import SafetyAlertConnectionError, SafetyAlertDataError

# Device type union for type hints
DeviceType = Union[
    KepcoDevice,
    GasAppDevice,
    SafetyAlertDevice,
    GoodsFlowDevice,
    ArisuDevice,
    KakaoMapDevice,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the Korea platform from a config entry."""
    service: str = entry.data.get("service")
    device: DeviceType
    update_interval: timedelta = timedelta(minutes=20)

    if service == "kepco":
        update_interval = timedelta(minutes=5)
        device = KepcoDevice(
            hass,
            entry.entry_id,
            entry.data.get(CONF_USERNAME),
            entry.data.get(CONF_PASSWORD),
            curl_cffi.AsyncSession(),
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

        async def async_update_data() -> Dict[str, Any]:
            """Fetch data from KEPCO API using the device."""
            try:
                await device.async_update()
                return device.data
            except KepcoAuthError as err:
                raise UpdateFailed(f"Authentication failed for KEPCO: {err}") from err
            except Exception as err:
                raise UpdateFailed(
                    f"Error communicating with KEPCO API: {err}"
                ) from err

    elif service == "gasapp":
        update_interval = timedelta(hours=1)
        device = GasAppDevice(
            hass,
            entry.entry_id,
            entry.data.get("token"),
            entry.data.get("member_id"),
            entry.data.get("use_contract_num"),
            aiohttp.ClientSession(),
        )

        # Initial validation and data fetch
        try:
            await device.async_update()
        except GasAppAuthError as err:
            LOGGER.error(f"Authentication failed during setup for GasApp: {err}")
            await device.async_close_session()
            return False
        except Exception as err:
            LOGGER.error(f"Error during initial data fetch for GasApp: {err}")
            await device.async_close_session()
            return False

        async def async_update_data() -> Dict[str, Any]:
            """Fetch data from GasApp API using the device."""
            try:
                await device.async_update()
                return device.data
            except GasAppAuthError as err:
                raise UpdateFailed(f"Authentication failed for GasApp: {err}") from err
            except Exception as err:
                raise UpdateFailed(
                    f"Error communicating with GasApp API: {err}"
                ) from err

    elif service == "safety_alert":
        update_interval = timedelta(minutes=5)
        device = SafetyAlertDevice(
            hass,
            entry.entry_id,
            entry.data.get("area_code"),
            entry.data.get("area_name"),
            entry.data.get("area_code2"),
            entry.data.get("area_code3"),
            aiohttp.ClientSession(),
        )

        # Initial validation and data fetch
        try:
            await device.async_update()
        except (SafetyAlertConnectionError, SafetyAlertDataError) as err:
            LOGGER.error(f"Error during initial data fetch for SafetyAlert: {err}")
            await device.async_close_session()
            return False
        except Exception as err:
            LOGGER.error(f"Error during initial data fetch for SafetyAlert: {err}")
            await device.async_close_session()
            return False

        async def async_update_data() -> Dict[str, Any]:
            """Fetch data from SafetyAlert API using the device."""
            try:
                await device.async_update()
                return device.data
            except (SafetyAlertConnectionError, SafetyAlertDataError) as err:
                raise UpdateFailed(
                    f"Error communicating with SafetyAlert API: {err}"
                ) from err
            except Exception as err:
                raise UpdateFailed(
                    f"Error communicating with SafetyAlert API: {err}"
                ) from err

    elif service == "goodsflow":
        update_interval = timedelta(minutes=15)
        device = GoodsFlowDevice(
            hass, entry.entry_id, entry.data.get("token"), aiohttp.ClientSession()
        )

        # Initial validation and data fetch
        try:
            await device.async_update()
        except GoodsFlowAuthError as err:
            LOGGER.error(f"Authentication failed during setup for GoodsFlow: {err}")
            await device.async_close_session()
            return False
        except Exception as err:
            LOGGER.error(f"Error during initial data fetch for GoodsFlow: {err}")
            await device.async_close_session()
            return False

        async def async_update_data() -> Dict[str, Any]:
            """Fetch data from GoodsFlow API using the device."""
            try:
                await device.async_update()
                return device.data
            except GoodsFlowAuthError as err:
                raise UpdateFailed(
                    f"Authentication failed for GoodsFlow: {err}"
                ) from err
            except Exception as err:
                raise UpdateFailed(
                    f"Error communicating with GoodsFlow API: {err}"
                ) from err

    elif service == "arisu":
        update_interval = timedelta(minutes=30)
        device = ArisuDevice(
            hass,
            entry.entry_id,
            entry.data.get("customer_number"),
            entry.data.get("customer_name"),
            aiohttp.ClientSession(),
        )

        # Initial validation and data fetch
        try:
            await device.async_update()
        except ArisuAuthError as err:
            LOGGER.error(f"Authentication failed during setup for Arisu: {err}")
            await device.async_close_session()
            return False
        except Exception as err:
            LOGGER.error(f"Error during initial data fetch for Arisu: {err}")
            await device.async_close_session()
            return False

        async def async_update_data() -> Dict[str, Any]:
            """Fetch data from Arisu API using the device."""
            try:
                await device.async_update()
                return device.data
            except ArisuAuthError as err:
                raise UpdateFailed(f"Authentication failed for Arisu: {err}") from err
            except Exception as err:
                raise UpdateFailed(
                    f"Error communicating with Arisu API: {err}"
                ) from err

    elif service == "kakaomap":
        update_interval = timedelta(minutes=1)
        device = KakaoMapDevice(
            hass,
            entry.entry_id,
            entry.data.get("name"),
            entry.data.get("start_coords"),
            entry.data.get("end_coords"),
            aiohttp.ClientSession(),
        )

        # Initial validation and data fetch
        try:
            await device.async_update()
        except (KakaoMapConnectionError, KakaoMapDataError) as err:
            LOGGER.error(f"Error during initial data fetch for KakaoMap: {err}")
            await device.async_close_session()
            return False
        except Exception as err:
            LOGGER.error(f"Error during initial data fetch for KakaoMap: {err}")
            await device.async_close_session()
            return False

        async def async_update_data() -> Dict[str, Any]:
            """Fetch data from KakaoMap API using the device."""
            try:
                await device.async_update()
                return device.data
            except (KakaoMapConnectionError, KakaoMapDataError) as err:
                raise UpdateFailed(
                    f"Error communicating with KakaoMap API: {err}"
                ) from err
            except Exception as err:
                raise UpdateFailed(
                    f"Error communicating with KakaoMap API: {err}"
                ) from err

    else:
        LOGGER.error(f"Unknown service: {service}")
        return False

    # Create update coordinator
    coordinator: DataUpdateCoordinator = DataUpdateCoordinator(
        hass,
        LOGGER,
        name=f"{DOMAIN}_{service}",
        update_method=async_update_data,
        update_interval=update_interval,
    )

    # Store coordinator and device in hass.data
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "device": device,
    }

    # Fetch initial data so we have data when entities are added
    await coordinator.async_config_entry_first_refresh()

    # Setup platforms - FIXED: Use await instead of async_create_task
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        data: Dict[str, Any] = hass.data[DOMAIN].pop(entry.entry_id)
        # Close the device session
        if device := data.get("device"):
            await device.async_close_session()

    return unload_ok
