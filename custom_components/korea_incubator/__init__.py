from __future__ import annotations

from datetime import timedelta
from typing import Dict, Any, Union

import aiohttp
import curl_cffi
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.components import persistent_notification
import voluptuous as vol
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .arisu.device import ArisuDevice
from .arisu.exceptions import ArisuAuthError
from .const import (
    DOMAIN,
    LOGGER,
    PLATFORMS,
    ENTRY_WEATHER,
    ENTRY_TRANSIT,
    ENTRY_FUEL,
    ENTRY_SCHOOL,
    ENTRY_DISASTER,
    ENTRY_SAFETY_ALERT,
    ENTRY_KEPCO,
    ENTRY_GASAPP,
    ENTRY_ARISU,
    ENTRY_PHARMACY,
    ENTRY_AIRKOREA,
    ENTRY_KMA_WEATHER,
    ENTRY_EARTHQUAKE,
    ENTRY_GOODSFLOW,
    ENTRY_KAKAOMAP,
    ENTRY_CJ_ONE_DELIVERY,
    ENTRY_ANIMAL_MEDICAL,
    ENTRY_DH_LOTTERY,
)
from .llm_api import async_cleanup_llm_api, async_setup_llm_api
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
from .safety_alert.migration import migrate_region_unique_ids

# Device type union for type hints
DeviceType = Union[
    KepcoDevice,
    GasAppDevice,
    SafetyAlertDevice,
    GoodsFlowDevice,
    ArisuDevice,
    KakaoMapDevice,
]

PLATFORM_MAP = {
    ENTRY_WEATHER: [Platform.EVENT, Platform.CALENDAR, Platform.BINARY_SENSOR],
    ENTRY_TRANSIT: [Platform.SENSOR],
    ENTRY_FUEL: [Platform.SENSOR],
    ENTRY_SCHOOL: [Platform.SENSOR, Platform.CALENDAR],
    ENTRY_DISASTER: [Platform.SENSOR, Platform.EVENT],
    ENTRY_SAFETY_ALERT: [Platform.BINARY_SENSOR, Platform.SENSOR],
    ENTRY_KEPCO: [Platform.SENSOR],
    ENTRY_GASAPP: [Platform.SENSOR],
    ENTRY_ARISU: [Platform.SENSOR],
    ENTRY_PHARMACY: [Platform.SENSOR, Platform.CALENDAR, Platform.BINARY_SENSOR],
    ENTRY_AIRKOREA: [
        Platform.SENSOR,
        Platform.BINARY_SENSOR,
        Platform.EVENT,
        Platform.CALENDAR,
    ],
    ENTRY_KMA_WEATHER: [Platform.WEATHER],
    ENTRY_EARTHQUAKE: [Platform.EVENT],
    ENTRY_GOODSFLOW: [Platform.SENSOR],
    ENTRY_KAKAOMAP: [Platform.SENSOR],
    ENTRY_CJ_ONE_DELIVERY: [Platform.SENSOR],
    ENTRY_ANIMAL_MEDICAL: [Platform.SENSOR, Platform.CALENDAR, Platform.BINARY_SENSOR],
    ENTRY_DH_LOTTERY: [Platform.SENSOR],
}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the Korea platform from a config entry."""
    service: str = entry.data.get("service")
    device: DeviceType = None
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
            company_id=entry.data.get("company_id", "1"),
        )
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
            entry.data.get("area_name2"),
            entry.data.get("area_name3"),
        )
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
            entry.options.get("api_key", entry.data.get("api_key")),
            entry.options.get("web_cookie", entry.data.get("web_cookie")),
            entry.data.get("start_id", ""),
            entry.data.get("end_id", ""),
        )
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

    elif service == ENTRY_CJ_ONE_DELIVERY:
        from .cj_one_delivery.api import AuthSession, CJOneDeliveryClient
        from .cj_one_delivery.const import (
            CONF_ACCESS_TOKEN,
            CONF_PHONE_NUMBER,
            CONF_REFRESH_TOKEN,
            CONF_USER_ID,
        )
        from .cj_one_delivery.coordinator import CJOneDeliveryCoordinator

        async def async_update_tokens(auth_session: AuthSession) -> None:
            hass.config_entries.async_update_entry(
                entry,
                data={
                    **entry.data,
                    CONF_USER_ID: auth_session.user_id,
                    CONF_ACCESS_TOKEN: auth_session.access_token,
                    CONF_REFRESH_TOKEN: auth_session.refresh_token,
                },
            )

        client = CJOneDeliveryClient(
            session=async_get_clientsession(hass),
            phone_number=entry.data[CONF_PHONE_NUMBER],
            user_id=entry.data[CONF_USER_ID],
            access_token=entry.data[CONF_ACCESS_TOKEN],
            refresh_token=entry.data[CONF_REFRESH_TOKEN],
            token_update_callback=async_update_tokens,
        )
        coordinator = CJOneDeliveryCoordinator(hass, entry, client)
        await coordinator.async_config_entry_first_refresh()
        store = {"coordinator": coordinator}
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][entry.entry_id] = store
        entry.async_on_unload(entry.add_update_listener(_async_cj_options_updated))
        await hass.config_entries.async_forward_entry_setups(
            entry, PLATFORM_MAP[service]
        )
        store["unregister_llm"] = await async_setup_llm_api(hass, entry, service)
        return True

    elif service == "weather_warning":
        from .weather.coordinator import WeatherWarningCoordinator

        api_key = entry.data["api_key"]
        c = WeatherWarningCoordinator(hass, api_key, entry.data.get("area_codes", []))
        await c.async_config_entry_first_refresh()
        store = {"coordinator": c, "area_codes": entry.data.get("area_codes", [])}
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][entry.entry_id] = store
        await hass.config_entries.async_forward_entry_setups(
            entry, PLATFORM_MAP.get(service, [])
        )
        store["unregister_llm"] = await async_setup_llm_api(hass, entry, service)
        return True

    elif service == "transit":
        from .transit.subway_coordinator import SubwayCoordinator
        from .transit.bus_coordinator import BusCoordinator
        from .transit.services import async_register_services

        seoul_key = entry.data.get("seoul_api_key", "")
        bus_key = entry.data.get("bus_api_key", "")
        sg: dict[str, list] = {}
        for item in entry.data.get("subway_items", []):
            sg.setdefault(item["station"], []).append(item)
        sc = {}
        for station, subs in sg.items():
            c = SubwayCoordinator(hass, seoul_key, station, subs)
            await c.async_config_entry_first_refresh()
            sc[station] = c
        bus_coords = {}
        for stop in entry.data.get("bus_stops", []):
            bc = BusCoordinator(hass, stop["stop_id"], stop["stop_name"])
            await bc.async_config_entry_first_refresh()
            bus_coords[stop["stop_id"]] = bc
        store = {
            "subway_coords": sc,
            "bus_coords": bus_coords,
            "subway_items": entry.data.get("subway_items", []),
            "bus_stops": entry.data.get("bus_stops", []),
        }
        if bus_key:
            async_register_services(hass, bus_key)
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][entry.entry_id] = store
        await hass.config_entries.async_forward_entry_setups(
            entry, PLATFORM_MAP.get(service, [])
        )
        store["unregister_llm"] = await async_setup_llm_api(hass, entry, service)
        return True

    elif service == "fuel":
        from .fuel.coordinator import FuelCoordinator

        api_key = entry.data["api_key"]
        configs = entry.data.get("configs", [])
        c = FuelCoordinator(hass, api_key, configs)
        await c.async_config_entry_first_refresh()
        store = {"coordinator": c, "configs": configs}
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][entry.entry_id] = store
        await hass.config_entries.async_forward_entry_setups(
            entry, PLATFORM_MAP.get(service, [])
        )
        store["unregister_llm"] = await async_setup_llm_api(hass, entry, service)
        return True

    elif service == "school":
        from .school.coordinator import SchoolCoordinator

        c = SchoolCoordinator(hass, entry)
        await c.async_config_entry_first_refresh()
        store = {"coordinator": c}
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][entry.entry_id] = store
        await hass.config_entries.async_forward_entry_setups(
            entry, PLATFORM_MAP.get(service, [])
        )
        store["unregister_llm"] = await async_setup_llm_api(hass, entry, service)
        return True

    elif service == "disaster":
        from .disaster.coordinator import DisasterCoordinator

        api_key = entry.data["api_key"]
        region = entry.data.get("region_filter", "")
        c = DisasterCoordinator(hass, api_key, region)
        await c.async_config_entry_first_refresh()
        store = {"coordinator": c, "region": region}
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][entry.entry_id] = store
        await hass.config_entries.async_forward_entry_setups(
            entry, PLATFORM_MAP.get(service, [])
        )
        store["unregister_llm"] = await async_setup_llm_api(hass, entry, service)
        return True

    elif service == "pharmacy":
        from .pharmacy.coordinator import PharmacyCoordinator
        from .pharmacy.services import async_register_pharmacy_service
        from homeassistant.exceptions import ConfigEntryError

        api_key = entry.data["api_key"]
        if not entry.data.get("hpid"):
            raise ConfigEntryError(translation_domain=DOMAIN, translation_key="pharmacy_selection_required")
        c = PharmacyCoordinator(hass, dict(entry.data), config_entry=entry)
        startup_entries = hass.data.setdefault(f"{DOMAIN}_animal_started", set())
        restore = not hass.is_running and entry.entry_id not in startup_entries
        startup_entries.add(entry.entry_id)
        if restore:
            await c.async_restore()
        await c.async_config_entry_first_refresh()
        entry.async_on_unload(entry.add_update_listener(_async_animal_options_updated))
        from .pharmacy.migration import remove_legacy_count
        remove_legacy_count(hass, entry)
        store = {"coordinator": c}
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][entry.entry_id] = store
        await hass.config_entries.async_forward_entry_setups(
            entry, PLATFORM_MAP.get(service, [])
        )
        store["unregister_llm"] = await async_setup_llm_api(hass, entry, service)
        async_register_pharmacy_service(hass, api_key, entry.entry_id)
        return True

    elif service == ENTRY_ANIMAL_MEDICAL:
        from .animal_medical.coordinator import AnimalMedicalCoordinator

        coordinator = AnimalMedicalCoordinator(
            hass, dict(entry.data), config_entry=entry
        )
        startup_entries = hass.data.setdefault(f"{DOMAIN}_animal_started", set())
        restore = not hass.is_running and entry.entry_id not in startup_entries
        startup_entries.add(entry.entry_id)
        if restore:
            await coordinator.async_restore()
        await coordinator.async_config_entry_first_refresh()
        entry.async_on_unload(entry.add_update_listener(_async_animal_options_updated))
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][entry.entry_id] = {"coordinator": coordinator}
        await hass.config_entries.async_forward_entry_setups(
            entry, PLATFORM_MAP.get(service, [])
        )
        hass.data[DOMAIN][entry.entry_id]["unregister_llm"] = await async_setup_llm_api(
            hass, entry, service
        )
        return True

    elif service == ENTRY_DH_LOTTERY:
        from .lottery import LotteryClient, LotteryCoordinator, LotteryError

        client = LotteryClient(entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD])
        try:
            await client.login()
            coordinator = LotteryCoordinator(hass, client)
            await coordinator.async_config_entry_first_refresh()
        except Exception as err:
            await client.close()
            LOGGER.error("Donghaeng Lottery setup failed: %s", err)
            return False
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][entry.entry_id] = {"coordinator": coordinator, "device": client}
        await _async_setup_lottery_services(hass)
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORM_MAP[service])
        return True

    elif service == "airkorea":
        from .airkorea.coordinator import AirKoreaCoordinator

        api_key = entry.data["api_key"]
        living_key = entry.data.get("living_api_key", "") or api_key
        stations = entry.data.get("stations", [])
        sido = entry.data.get("sido", "서울")
        c = AirKoreaCoordinator(
            hass, api_key, stations, living_api_key=living_key, sido=sido
        )
        await c.async_config_entry_first_refresh()
        store = {"coordinator": c, "stations": stations}
        from .airkorea.services import async_register_airkorea_services

        async_register_airkorea_services(hass, api_key, living_key, sido)
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][entry.entry_id] = store
        await hass.config_entries.async_forward_entry_setups(
            entry, PLATFORM_MAP.get(service, [])
        )
        store["unregister_llm"] = await async_setup_llm_api(hass, entry, service)
        return True

    elif service == "kma_weather":
        from .kma_weather.coordinator import KMAWeatherCoordinator

        api_key = entry.data["api_key"]
        regions = entry.data.get("regions", [])
        c = KMAWeatherCoordinator(
            hass,
            api_key,
            regions,
            air_api_key=api_key,
            air_station=entry.data.get("air_station", ""),
            living_api_key=api_key,
            area_no=entry.data.get("area_no", ""),
        )
        await c.async_config_entry_first_refresh()
        store = {"coordinator": c, "regions": regions}
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][entry.entry_id] = store
        await hass.config_entries.async_forward_entry_setups(
            entry, PLATFORM_MAP.get(service, [])
        )
        store["unregister_llm"] = await async_setup_llm_api(hass, entry, service)
        return True

    elif service == "earthquake":
        from .earthquake.coordinator import EarthquakeCoordinator

        api_key = entry.data["api_key"]
        c = EarthquakeCoordinator(hass, api_key)
        await c.async_config_entry_first_refresh()
        store = {"coordinator": c}
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][entry.entry_id] = store
        await hass.config_entries.async_forward_entry_setups(
            entry, PLATFORM_MAP.get(service, [])
        )
        store["unregister_llm"] = await async_setup_llm_api(hass, entry, service)
        return True

    else:
        LOGGER.error(f"Unknown service: {service}")
        return False

    # Create update coordinator (기존 서비스용 공통 로직)
    coordinator: DataUpdateCoordinator = DataUpdateCoordinator(
        hass,
        LOGGER,
        name=f"{DOMAIN}_{service}",
        config_entry=entry,
        update_method=async_update_data,
        update_interval=update_interval,
    )

    # Store coordinator and device in hass.data
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "device": device,
    }

    if service == ENTRY_KAKAOMAP:
        entry.async_on_unload(entry.add_update_listener(_async_kakaomap_options_updated))

    if service == "safety_alert":
        migrate_region_unique_ids(hass, entry, device)

    # Fetch initial data so we have data when entities are added
    await coordinator.async_config_entry_first_refresh()

    # Setup platforms
    await hass.config_entries.async_forward_entry_setups(
        entry, PLATFORM_MAP.get(service, [Platform.SENSOR, Platform.BINARY_SENSOR])
    )

    # Setup LLM API
    unregister_llm = await async_setup_llm_api(hass, entry, service)
    hass.data[DOMAIN][entry.entry_id]["unregister_llm"] = unregister_llm

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    service = entry.data.get("service")
    store = hass.data.get(DOMAIN, {}).get(entry.entry_id, {}) or {}

    if unload_ok := await hass.config_entries.async_unload_platforms(
        entry, PLATFORM_MAP.get(service, PLATFORMS)
    ):
        async_cleanup_llm_api(store.get("unregister_llm"))
        if service == "pharmacy":
            from .pharmacy.services import async_unregister_pharmacy_service
            async_unregister_pharmacy_service(hass, entry.entry_id)
        data: Dict[str, Any] = hass.data[DOMAIN].pop(entry.entry_id)
        # Close the device session
        if device := data.get("device"):
            await device.async_close_session()

    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove persisted animal medical data when its entry is deleted."""
    if entry.data.get("service") in (ENTRY_ANIMAL_MEDICAL, "pharmacy"):
        from homeassistant.helpers.storage import Store

        await Store(hass, 1, f"{DOMAIN}.{entry.data['service']}.{entry.entry_id}").async_remove()
        hass.data.get(f"{DOMAIN}_animal_started", set()).discard(entry.entry_id)


async def _async_animal_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """A settings update always reloads and fetches fresh API data."""
    await hass.config_entries.async_reload(entry.entry_id)


async def _async_cj_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Apply CJ O-NE polling options without unloading its entities."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    if dict(entry.options) == coordinator.loaded_options:
        return
    coordinator.apply_options()
    await coordinator.async_request_refresh()


async def _async_kakaomap_options_updated(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Reload KakaoMap after its REST API key changes."""
    await hass.config_entries.async_reload(entry.entry_id)


async def _async_setup_lottery_services(hass: HomeAssistant) -> None:
    """Register account-targeted lottery services once per Home Assistant instance."""
    marker = f"{DOMAIN}_lottery_services"
    if hass.data.get(marker):
        return

    from .lottery import LotteryError

    async def _find(call: ServiceCall):
        entity_id = call.data["entity_id"]
        from homeassistant.helpers import entity_registry as er

        registry_entry = er.async_get(hass).async_get(entity_id)
        if not registry_entry:
            raise LotteryError("동행복권 예치금 엔티티를 찾지 못했습니다.")
        data = hass.data.get(DOMAIN, {}).get(registry_entry.config_entry_id)
        if not data or "coordinator" not in data:
            raise LotteryError("동행복권 설정 항목을 찾지 못했습니다.")
        return data["coordinator"]

    async def refresh(call: ServiceCall) -> None:
        coordinator = await _find(call)
        await coordinator.async_request_refresh()

    async def buy_pension(call: ServiceCall) -> dict:
        coordinator = None
        try:
            coordinator = await _find(call)
            tickets = await coordinator.client.buy_pension_auto(call.data["games"])
            await coordinator.async_request_refresh()
            message = "\n".join(f"{ticket['round']}회 {ticket['group']}조 {ticket['number']}" for ticket in tickets)
            persistent_notification.async_create(hass, message, "연금복권 720+ 자동 구매", call.context.id)
            return {"result": "success", "tickets": tickets}
        except Exception as err:
            persistent_notification.async_create(hass, str(err), "연금복권 720+ 구매 실패", call.context.id)
            return {"result": "fail", "message": str(err)}

    async def buy_lotto(call: ServiceCall) -> dict:
        try:
            coordinator = await _find(call)
            result = await coordinator.client.buy_lotto_645_auto(call.data["games"])
            await coordinator.async_request_refresh()
            games = result.get("arrGameChoiceNum", [])
            persistent_notification.async_create(hass, "\n".join(games), "로또 6/45 자동 구매", call.context.id)
            return {"result": "success", "value": result}
        except Exception as err:
            persistent_notification.async_create(hass, str(err), "로또 6/45 구매 실패", call.context.id)
            return {"result": "fail", "message": str(err)}

    hass.services.async_register(DOMAIN, "refresh_dh_lottery", refresh, schema=vol.Schema({vol.Required("entity_id"): str}))
    hass.services.async_register(
        DOMAIN, "buy_pension_720_auto", buy_pension,
        schema=vol.Schema({vol.Required("entity_id"): str, vol.Optional("games", default=5): vol.All(vol.Coerce(int), vol.Range(min=1, max=5))}),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN, "buy_lotto_645_auto", buy_lotto,
        schema=vol.Schema({vol.Required("entity_id"): str, vol.Optional("games", default=5): vol.All(vol.Coerce(int), vol.Range(min=1, max=5))}),
        supports_response=SupportsResponse.ONLY,
    )
    hass.data[marker] = True
