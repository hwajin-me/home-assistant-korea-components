from __future__ import annotations

from typing import Any, Dict, Optional

import aiohttp
import curl_cffi
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .arisu.api import ArisuApiClient
from .arisu.exceptions import ArisuAuthError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectSelector, SelectSelectorConfig, SelectSelectorMode,
)
from .const import *

from .gasapp.api import GasAppApiClient
from .gasapp.exceptions import GasAppAuthError
from .goodsflow.api import GoodsFlowApiClient
from .goodsflow.exceptions import GoodsFlowAuthError
from .kakaomap.api import KakaoMapApiClient
from .kakaomap.coordinates import convert_coordinates, validate_coordinates
from .kakaomap.exceptions import KakaoMapConnectionError
from .kepco.api import KepcoApiClient
from .kepco.exceptions import KepcoAuthError
from .safety_alert.api import SafetyAlertApiClient
from .safety_alert.exceptions import SafetyAlertConnectionError
from .safety_alert.region_api import SafetyAlertRegionApiClient


class KoreaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Korea integration."""

    VERSION = 1

    def __init__(self):
        """Initialize the config flow."""
        self._safety_alert_data = {}

    async def async_step_user(self, user_input: Optional[Dict[str, Any]] = None):
        """Handle the initial step."""
        return self.async_show_menu(
            step_id="user",
            menu_options=[
                "kepco",
                "gasapp",
                "safety_alert",
                "goodsflow",
                "arisu",
                "kakaomap",
                "weather_warning",
                "transit",
                "fuel",
                "school",
                "disaster",
                "pharmacy",
                "airkorea",
                "kma_weather",
                "earthquake",
            ],
        )

    async def async_step_kepco(self, user_input: Optional[Dict[str, Any]] = None):
        """Handle KEPCO configuration."""
        errors: Dict[str, str] = {}
        error_info: Dict[str, str] = {}

        if user_input is not None:
            async with curl_cffi.AsyncSession() as session:
                client = KepcoApiClient(session)
                client.set_credentials(
                    user_input[CONF_USERNAME], user_input[CONF_PASSWORD]
                )
                try:
                    if await client.async_login(
                        user_input[CONF_USERNAME], user_input[CONF_PASSWORD]
                    ):
                        unique_id = f"kepco_{user_input[CONF_USERNAME]}"
                        await self.async_set_unique_id(unique_id)
                        self._abort_if_unique_id_configured()

                        user_input["service"] = "kepco"
                        return self.async_create_entry(
                            title=f"한전 ({user_input[CONF_USERNAME]})", data=user_input
                        )
                    else:
                        errors["base"] = "auth"
                        error_info["error"] = "Login returned false"
                except KepcoAuthError as e:
                    LOGGER.error(f"KEPCO login failed: {e}")
                    errors["base"] = "invalid_auth"
                    error_info["error"] = str(e)
                except Exception as e:
                    LOGGER.error(f"KEPCO login failed: {e}")
                    errors["base"] = "unknown"
                    error_info["error"] = str(e)

        return self.async_show_form(
            step_id="kepco",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
            description_placeholders=error_info,
        )

    async def async_step_gasapp(self, user_input: Optional[Dict[str, Any]] = None):
        """Handle GasApp configuration."""
        errors: Dict[str, str] = {}
        error_info: Dict[str, str] = {}

        if user_input is not None:
            async with aiohttp.ClientSession() as session:
                client = GasAppApiClient(session)
                client.set_credentials(
                    user_input["token"],
                    user_input["member_id"],
                    user_input["use_contract_num"],
                )
                try:
                    if await client.async_validate_credentials():
                        unique_id = f"gasapp_{user_input['use_contract_num']}"
                        await self.async_set_unique_id(unique_id)
                        self._abort_if_unique_id_configured()

                        user_input["service"] = "gasapp"
                        return self.async_create_entry(
                            title=f"가스앱 ({user_input['use_contract_num']})",
                            data=user_input,
                        )
                    else:
                        errors["base"] = "auth"
                        error_info["error"] = "Credential validation returned false"
                except GasAppAuthError as e:
                    LOGGER.error(f"GasApp authentication failed: {e}")
                    errors["base"] = "invalid_auth"
                    error_info["error"] = str(e)
                except Exception as e:
                    LOGGER.error(f"GasApp connection failed: {e}")
                    errors["base"] = "unknown"
                    error_info["error"] = str(e)

        return self.async_show_form(
            step_id="gasapp",
            data_schema=vol.Schema(
                {
                    vol.Required("token"): str,
                    vol.Required("member_id"): str,
                    vol.Required("use_contract_num"): str,
                }
            ),
            errors=errors,
            description_placeholders=error_info,
        )

    async def async_step_safety_alert(
        self, user_input: Optional[Dict[str, Any]] = None
    ):
        """Handle Safety Alert configuration - start with sido selection."""
        errors: Dict[str, str] = {}
        error_info: Dict[str, str] = {}

        if user_input is not None:
            sido_code = user_input["sido_code"]
            sido_name = self._safety_alert_data.get("sido_options", {}).get(sido_code, sido_code)
            self._safety_alert_data["sido_code"] = sido_code
            self._safety_alert_data["sido_name"] = sido_name
            return await self.async_step_safety_alert_sgg()

        # Get sido list
        try:
            async with aiohttp.ClientSession() as session:
                region_client = SafetyAlertRegionApiClient(session)
                sido_list = await region_client.async_get_sido_list()

                if not sido_list:
                    errors["base"] = "no_regions_available"
                    error_info["error"] = "No sido data returned from API"
                else:
                    sido_options = {
                        region["code"]: region["name"] for region in sido_list
                    }
                    self._safety_alert_data["sido_options"] = sido_options

                    return self.async_show_form(
                        step_id="safety_alert",
                        data_schema=vol.Schema(
                            {
                                vol.Required("sido_code", default="1100000000"): vol.In(
                                    sido_options
                                ),
                            }
                        ),
                        errors=errors,
                        description_placeholders=error_info,
                    )

        except SafetyAlertConnectionError as e:
            LOGGER.error(f"Safety Alert region API failed: {e}")
            errors["base"] = "cannot_connect"
            error_info["error"] = str(e)
        except Exception as e:
            LOGGER.error(f"Safety Alert setup failed: {e}")
            errors["base"] = "unknown"
            error_info["error"] = str(e)

        return self.async_show_form(
            step_id="safety_alert",
            data_schema=vol.Schema(
                {
                    vol.Required("sido_code", default="1100000000"): str,
                }
            ),
            errors=errors,
            description_placeholders=error_info,
        )

    async def async_step_safety_alert_sgg(
        self, user_input: Optional[Dict[str, Any]] = None
    ):
        """Handle Safety Alert sgg (시군구) selection."""
        errors: Dict[str, str] = {}
        error_info: Dict[str, str] = {}

        if user_input is not None:
            sgg_code = user_input.get("sgg_code") or user_input.get("sgg_name", "")
            sgg_name = self._safety_alert_data.get("sgg_options", {}).get(sgg_code, sgg_code)
            self._safety_alert_data["sgg_code"] = sgg_code
            self._safety_alert_data["sgg_name"] = sgg_name
            return await self.async_step_safety_alert_emd()

        sido_code = self._safety_alert_data.get("sido_code", "")
        sido_name = self._safety_alert_data.get("sido_name", "")

        region_client = SafetyAlertRegionApiClient()
        sgg_list = await region_client.async_get_sgg_list(sido_code)

        if sgg_list:
            sgg_options = {r["code"]: r["name"] for r in sgg_list}
            self._safety_alert_data["sgg_options"] = sgg_options
            return self.async_show_form(
                step_id="safety_alert_sgg",
                data_schema=vol.Schema(
                    {
                        vol.Required("sgg_code"): vol.In(sgg_options),
                    }
                ),
                description_placeholders={"sido_name": sido_name},
            )

        # API returned no data — fall back to manual text input
        LOGGER.warning("No sgg data returned for sido %s, using text input", sido_code)
        return self.async_show_form(
            step_id="safety_alert_sgg",
            data_schema=vol.Schema(
                {
                    vol.Required("sgg_name"): str,
                }
            ),
            errors=errors,
            description_placeholders={"sido_name": sido_name},
        )

    async def async_step_safety_alert_emd(
        self, user_input: Optional[Dict[str, Any]] = None
    ):
        """Handle Safety Alert emd (읍면동) selection."""
        errors: Dict[str, str] = {}
        error_info: Dict[str, str] = {}

        if user_input is not None:
            emd_code = user_input.get("emd_code") or user_input.get("emd_name", "")
            emd_name = self._safety_alert_data.get("emd_options", {}).get(emd_code, emd_code)
            self._safety_alert_data["emd_code"] = emd_code
            self._safety_alert_data["emd_name"] = emd_name
            return await self._create_safety_alert_entry()

        sido_code = self._safety_alert_data.get("sido_code", "")
        sgg_code = self._safety_alert_data.get("sgg_code", "")
        sgg_name = self._safety_alert_data.get("sgg_name", "")

        region_client = SafetyAlertRegionApiClient()
        emd_list = await region_client.async_get_emd_list(sido_code, sgg_code)

        if emd_list:
            emd_options = {r["code"]: r["name"] for r in emd_list}
            self._safety_alert_data["emd_options"] = emd_options
            return self.async_show_form(
                step_id="safety_alert_emd",
                data_schema=vol.Schema(
                    {
                        vol.Required("emd_code"): vol.In(emd_options),
                    }
                ),
                description_placeholders={"sgg_name": sgg_name},
            )

        # API returned no data — fall back to manual text input
        LOGGER.warning("No emd data returned for sgg %s, using text input", sgg_code)
        return self.async_show_form(
            step_id="safety_alert_emd",
            data_schema=vol.Schema(
                {
                    vol.Required("emd_name"): str,
                }
            ),
            errors=errors,
            description_placeholders={"sgg_name": sgg_name},
        )

    async def _create_safety_alert_entry(self):
        """Create the safety alert config entry."""
        try:
            sido_code = self._safety_alert_data["sido_code"]
            sgg_code = self._safety_alert_data.get("sgg_code", "")
            sgg_name = self._safety_alert_data.get("sgg_name", "")
            emd_code = self._safety_alert_data.get("emd_code", "")
            emd_name = self._safety_alert_data.get("emd_name", "")

            # Use numeric codes for API filtering; text fallbacks are display-only
            api_sgg = sgg_code if sgg_code.isdigit() else None
            api_emd = emd_code if emd_code.isdigit() else None

            async with aiohttp.ClientSession() as session:
                client = SafetyAlertApiClient(session)
                await client.async_get_safety_alerts(sido_code, api_sgg, api_emd)

            display_name = self._safety_alert_data["sido_name"]
            if sgg_name:
                display_name += f" {sgg_name}"
            if emd_name:
                display_name += f" {emd_name}"

            unique_id = f"safety_alert_{sido_code}_{sgg_code}_{emd_code}"
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            entry_data = {
                "service": "safety_alert",
                "area_code": sido_code,
                "area_name": display_name,
                "sido_code": sido_code,
                "sido_name": self._safety_alert_data["sido_name"],
            }
            if sgg_code:
                entry_data["area_code2"] = api_sgg or ""
                entry_data["area_name2"] = sgg_name
            if emd_code or emd_name:
                entry_data["area_code3"] = api_emd or ""
                entry_data["area_name3"] = emd_name

            return self.async_create_entry(
                title=f"안전알림 ({display_name})", data=entry_data
            )

        except SafetyAlertConnectionError as e:
            LOGGER.error(f"Safety Alert connection failed: {e}")
            return self.async_abort(reason="cannot_connect")
        except Exception as e:
            LOGGER.error(f"Safety Alert setup failed: {e}")
            return self.async_abort(reason="unknown")

    async def async_step_arisu(self, user_input: Optional[Dict[str, Any]] = None):
        """Handle Arisu configuration."""
        errors: Dict[str, str] = {}
        error_info: Dict[str, str] = {}

        if user_input is not None:
            async with aiohttp.ClientSession() as session:
                client = ArisuApiClient(session)
                try:
                    # Test the API with the provided credentials (both customer number and name)
                    bill_data = await client.async_get_water_bill_data(
                        user_input["customer_number"], user_input["customer_name"]
                    )

                    if bill_data.get("success", False):
                        unique_id = f"arisu_{user_input['customer_number']}"
                        await self.async_set_unique_id(unique_id)
                        self._abort_if_unique_id_configured()

                        user_input["service"] = "arisu"
                        return self.async_create_entry(
                            title=f"아리수 ({user_input['customer_number']})",
                            data=user_input,
                        )
                    else:
                        errors["base"] = "invalid_auth"
                        error_info["error"] = "Credentials validation failed"
                except ArisuAuthError as e:
                    LOGGER.error(f"Arisu authentication failed: {e}")
                    errors["base"] = "invalid_auth"
                    error_info["error"] = str(e)
                except Exception as e:
                    LOGGER.error(f"Arisu connection failed: {e}")
                    errors["base"] = "unknown"
                    error_info["error"] = str(e)

        return self.async_show_form(
            step_id="arisu",
            data_schema=vol.Schema(
                {
                    vol.Required("customer_number"): str,
                    vol.Required("customer_name"): str,
                }
            ),
            errors=errors,
            description_placeholders=error_info,
        )

    async def async_step_kakaomap(self, user_input: Optional[Dict[str, Any]] = None):
        """Handle KakaoMap configuration."""
        errors: Dict[str, str] = {}
        error_info: Dict[str, str] = {}

        if user_input is not None:
            async with aiohttp.ClientSession() as session:
                client = KakaoMapApiClient(session)
                try:
                    # 좌표계 변환 처리
                    coord_system = user_input.get("coord_system", "WCONGNAMUL")

                    # 입력 좌표 준비
                    if coord_system == "WGS84":
                        # WGS84 좌표를 입력받은 경우
                        start_coords_input = {
                            "longitude": float(user_input["start_x"]),
                            "latitude": float(user_input["start_y"]),
                        }
                        end_coords_input = {
                            "longitude": float(user_input["end_x"]),
                            "latitude": float(user_input["end_y"]),
                        }

                        # 좌표 유효성 검사
                        if not validate_coordinates(start_coords_input, "WGS84"):
                            errors["start_x"] = "invalid_wgs84_coordinates"
                            error_info["error"] = (
                                f"Longitude: {start_coords_input['longitude']}, Latitude: {start_coords_input['latitude']}"
                            )
                        if not validate_coordinates(end_coords_input, "WGS84"):
                            errors["end_x"] = "invalid_wgs84_coordinates"
                            error_info["error"] = (
                                f"Longitude: {end_coords_input['longitude']}, Latitude: {end_coords_input['latitude']}"
                            )

                        if not errors:
                            # WGS84를 WCONGNAMUL로 변환
                            start_coords = convert_coordinates(
                                start_coords_input, "WGS84", "WCONGNAMUL"
                            )
                            end_coords = convert_coordinates(
                                end_coords_input, "WGS84", "WCONGNAMUL"
                            )
                    else:
                        # WCONGNAMUL 좌표를 입력받은 경우
                        start_coords = {
                            "x": float(user_input["start_x"]),
                            "y": float(user_input["start_y"]),
                        }
                        end_coords = {
                            "x": float(user_input["end_x"]),
                            "y": float(user_input["end_y"]),
                        }

                        # 좌표 유효성 검사
                        if not validate_coordinates(start_coords, "WCONGNAMUL"):
                            errors["start_x"] = "invalid_wcongnamul_coordinates"
                            error_info["error"] = (
                                f"X: {start_coords['x']}, Y: {start_coords['y']}"
                            )
                        if not validate_coordinates(end_coords, "WCONGNAMUL"):
                            errors["end_x"] = "invalid_wcongnamul_coordinates"
                            error_info["error"] = (
                                f"X: {end_coords['x']}, Y: {end_coords['y']}"
                            )

                    if not errors:
                        # Test coordinate to address conversion
                        start_address = await client.async_coordinate_to_address(
                            start_coords["x"], start_coords["y"]
                        )

                        if start_address.get("success"):
                            unique_id = (
                                f"kakaomap_{user_input['name'].replace(' ', '_')}"
                            )
                            await self.async_set_unique_id(unique_id)
                            self._abort_if_unique_id_configured()

                            user_input["service"] = "kakaomap"
                            user_input["start_coords"] = start_coords
                            user_input["end_coords"] = end_coords
                            # 원본 좌표계 정보도 저장 (참고용)
                            user_input["original_coord_system"] = coord_system

                            return self.async_create_entry(
                                title=f"카카오맵 ({user_input['name']})",
                                data=user_input,
                            )
                        else:
                            errors["base"] = "invalid_coordinates"
                            error_info["error"] = (
                                "Address lookup failed with the provided coordinates"
                            )

                except KakaoMapConnectionError as e:
                    LOGGER.error(f"KakaoMap connection failed: {e}")
                    errors["base"] = "cannot_connect"
                    error_info["error"] = str(e)
                except ValueError as e:
                    LOGGER.error(f"Invalid coordinates: {e}")
                    errors["base"] = "invalid_coordinates"
                    error_info["error"] = str(e)
                except Exception as e:
                    LOGGER.error(f"KakaoMap setup failed: {e}")
                    errors["base"] = "unknown"
                    error_info["error"] = str(e)

        return self.async_show_form(
            step_id="kakaomap",
            data_schema=vol.Schema(
                {
                    vol.Required("name", default="집↔회사"): str,
                    vol.Required("coord_system", default="WCONGNAMUL"): vol.In(
                        ["WCONGNAMUL", "WGS84"]
                    ),
                    vol.Required(
                        "start_x", default="515290"
                    ): str,  # 기본값: WCONGNAMUL 건대입구역
                    vol.Required("start_y", default="1122478"): str,
                    vol.Required(
                        "end_x", default="506190"
                    ): str,  # 기본값: WCONGNAMUL 강남역
                    vol.Required("end_y", default="1110730"): str,
                }
            ),
            errors=errors,
            description_placeholders=error_info,
        )

    # ══════════ 기상특보 ══════════
    async def async_step_weather_warning(self, user_input=None) -> FlowResult:
        from .weather import AREA_CODES
        from .weather.api import validate_kma_api
        errors: dict[str, str] = {}
        area_options = [{"value": code, "label": f"{name}"} for code, name in AREA_CODES.items()]
        if user_input is not None:
            api_key = user_input["api_key"]
            areas = user_input.get("area_codes", [])
            if not isinstance(areas, list): areas = [areas]
            if not areas: errors["area_codes"] = "no_selection"
            elif await validate_kma_api(api_key, areas[0]):
                return self.async_create_entry(title="기상특보", data={CONF_ENTRY_TYPE: ENTRY_WEATHER, "api_key": api_key, "area_codes": areas})
            else: errors["base"] = "cannot_connect"
        return self.async_show_form(step_id="weather_warning", data_schema=vol.Schema({
            vol.Required("api_key"): str,
            vol.Required("area_codes"): SelectSelector(SelectSelectorConfig(options=area_options, multiple=True, mode=SelectSelectorMode.DROPDOWN)),
        }), errors=errors)

    # ══════════ 대중교통 ══════════
    async def async_step_transit(self, user_input=None) -> FlowResult:
        if user_input is not None:
            self._data = {CONF_ENTRY_TYPE: ENTRY_TRANSIT, "seoul_api_key": user_input.get("seoul_api_key", ""),
                         "bus_api_key": user_input.get("bus_api_key", ""), "subway_items": [], "bus_stops": []}
            return await self.async_step_transit_add()
        return self.async_show_form(step_id="transit", data_schema=vol.Schema({
            vol.Optional("seoul_api_key"): str,
            vol.Optional("bus_api_key"): str,
        }))

    async def async_step_transit_add(self, user_input=None) -> FlowResult:
        return self.async_show_menu(step_id="transit_add", menu_options=["transit_subway", "transit_bus_search", "transit_done"])

    async def async_step_transit_subway(self, user_input=None) -> FlowResult:
        from .transit import DIRECTIONS, SUBWAY_LINES
        if user_input is not None:
            self._data["subway_items"].append({"station": user_input["station"].strip(), "direction": user_input["direction"], "line_id": user_input.get("line_id", "")})
            return await self.async_step_transit_add()
        dir_opts = {d: d for d in DIRECTIONS}
        line_opts = {"": "전체", **SUBWAY_LINES}
        return self.async_show_form(step_id="transit_subway", data_schema=vol.Schema({
            vol.Required("station"): str,
            vol.Required("direction", default="상행"): vol.In(dir_opts),
            vol.Optional("line_id", default=""): vol.In(line_opts),
        }))

    async def async_step_transit_bus_search(self, user_input=None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            stop_id = user_input["kakao_stop_id"].strip()
            from .transit.bus_api import fetch_stop_data, build_bus_labels
            try:
                session = async_get_clientsession(self.hass)
                data = await fetch_stop_data(session, stop_id)
                if not data.get("name"): errors["kakao_stop_id"] = "no_stops_found"
                else:
                    self._bus_stop_id, self._bus_stop_name = stop_id, data["name"]
                    self._bus_labels = build_bus_labels(data)
                    return await self.async_step_transit_bus_select()
            except Exception: errors["kakao_stop_id"] = "cannot_connect"
        return self.async_show_form(step_id="transit_bus_search", data_schema=vol.Schema({vol.Required("kakao_stop_id"): str}), errors=errors)

    async def async_step_transit_bus_select(self, user_input=None) -> FlowResult:
        import homeassistant.helpers.config_validation as cv
        if user_input is not None:
            self._data.setdefault("bus_stops", []).append({"stop_id": self._bus_stop_id, "stop_name": self._bus_stop_name, "buses": user_input.get("buses", [])})
            return await self.async_step_transit_add()
        return self.async_show_form(step_id="transit_bus_select", data_schema=vol.Schema({vol.Required("buses", default=list(self._bus_labels.keys())): cv.multi_select(self._bus_labels)}))

    async def async_step_transit_done(self, user_input=None) -> FlowResult:
        return self.async_create_entry(title="대중교통", data=self._data)

    # ══════════ 유가정보 ══════════
    async def async_step_fuel(self, user_input=None) -> FlowResult:
        from .fuel import SIDO_CODES, FUEL_TYPES
        from .fuel.api import validate_opinet
        errors: dict[str, str] = {}
        sido_opts = [{"value": k, "label": v} for k, v in SIDO_CODES.items()]
        fuel_opts = [{"value": k, "label": v} for k, v in FUEL_TYPES.items()]
        if user_input is not None:
            api_key = user_input["api_key"]
            sidos, fuels = user_input.get("sido_codes", []), user_input.get("fuel_codes", [])
            if not sidos or not fuels: errors["base"] = "no_selection"
            elif await validate_opinet(api_key):
                configs = [{"sido_code": s, "fuel_code": f} for s in sidos for f in fuels]
                return self.async_create_entry(title="유가정보", data={CONF_ENTRY_TYPE: ENTRY_FUEL, "api_key": api_key, "configs": configs})
            else: errors["base"] = "cannot_connect"
        return self.async_show_form(step_id="fuel", data_schema=vol.Schema({
            vol.Required("api_key"): str,
            vol.Required("sido_codes"): SelectSelector(SelectSelectorConfig(options=sido_opts, multiple=True, mode=SelectSelectorMode.DROPDOWN)),
            vol.Required("fuel_codes"): SelectSelector(SelectSelectorConfig(options=fuel_opts, multiple=True, mode=SelectSelectorMode.DROPDOWN)),
        }), errors=errors)

    # ══════════ 학교정보 ══════════
    async def async_step_school(self, user_input=None) -> FlowResult:
        from .school import SCHOOL_LEVELS
        errors: dict[str, str] = {}
        if user_input is not None:
            self._data = {CONF_ENTRY_TYPE: ENTRY_SCHOOL, "api_key": user_input["api_key"], "school_level": user_input["school_level"]}
            return await self.async_step_school_search()
        return self.async_show_form(step_id="school", data_schema=vol.Schema({vol.Required("api_key"): str, vol.Required("school_level", default="elementary"): vol.In(SCHOOL_LEVELS)}), errors=errors)

    async def async_step_school_search(self, user_input=None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            session = async_get_clientsession(self.hass)
            from .school.api import NeisApiClient
            c = NeisApiClient(session, self._data["api_key"])
            if "school_search" in user_input:
                schools = await c.search_school(user_input["school_search"])
                if not schools: errors["school_search"] = "no_schools_found"
                else:
                    opts = {f"{s['ATPT_OFCDC_SC_CODE']}_{s['SD_SCHUL_CODE']}": f"{s['SCHUL_NM']} ({s.get('ORG_RDNMA', '')})" for s in schools[:10]}
                    return self.async_show_form(step_id="school_search", data_schema=vol.Schema({vol.Required("selected_school"): vol.In(opts)}))
            elif "selected_school" in user_input:
                rc, sc = user_input["selected_school"].split("_")
                info = await c.get_school_info(rc, sc)
                if info:
                    from .school.parser import parse_school_info
                    self._data.update(parse_school_info(info))
                    return await self.async_step_school_class()
                errors["base"] = "cannot_connect"
        return self.async_show_form(step_id="school_search", data_schema=vol.Schema({vol.Required("school_search"): str}), errors=errors)

    async def async_step_school_class(self, user_input=None) -> FlowResult:
        import homeassistant.helpers.config_validation as cv
        if user_input is not None:
            selected = user_input.get("grade_classes", [])
            self._data["grade_classes"] = selected
            if selected:
                g, cl = selected[0].split("-")
                self._data.update({"grade": int(g), "classes": [s.split("-")[1] for s in selected], "class": selected[0].split("-")[1]})
            return await self.async_step_school_periods()
        max_g = 6 if self._data["school_level"] == "elementary" else 3
        opts = {f"{g}-{cl}": f"{g}학년 {cl}반" for g in range(1, max_g + 1) for cl in range(1, 21)}
        return self.async_show_form(step_id="school_class", data_schema=vol.Schema({vol.Required("grade_classes"): cv.multi_select(opts)}))

    async def async_step_school_periods(self, user_input=None) -> FlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return self.async_create_entry(title="학교정보", data=self._data)
        defaults = {1:"09:00-09:50",2:"10:00-10:50",3:"11:00-11:50",4:"12:00-12:50",5:"13:40-14:30",6:"14:40-15:30",7:"15:40-16:30"}
        schema = {vol.Required(f"period_1", default=defaults[1]): str}
        for i in range(2, 8): schema[vol.Optional(f"period_{i}", default=defaults.get(i, ""))] = str
        schema.update({vol.Optional("lunch_start", default="12:50"): str, vol.Optional("lunch_end", default="13:40"): str})
        return self.async_show_form(step_id="school_periods", data_schema=vol.Schema(schema))

    # ══════════ 재난정보 ══════════
    async def async_step_disaster(self, user_input=None) -> FlowResult:
        from .disaster.api import validate_disaster_api
        errors, region_opts = {}, [{"value": "", "label": "전체"}]
        for n in ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주"]:
            region_opts.append({"value": n, "label": n})
        if user_input is not None:
            if await validate_disaster_api(user_input["api_key"]):
                region = user_input.get("sub_region", "").strip() or user_input.get("region_filter", "")
                return self.async_create_entry(title=f"재난정보 {region}", data={CONF_ENTRY_TYPE: ENTRY_DISASTER, "api_key": user_input["api_key"], "region_filter": region})
            else: errors["base"] = "cannot_connect"
        return self.async_show_form(step_id="disaster", data_schema=vol.Schema({
            vol.Required("api_key"): str,
            vol.Optional("region_filter", default=""): SelectSelector(SelectSelectorConfig(options=region_opts, mode=SelectSelectorMode.DROPDOWN)),
            vol.Optional("sub_region", default=""): str,
        }), errors=errors)

    # ══════════ 약국 ══════════
    async def async_step_pharmacy(self, user_input=None) -> FlowResult:
        sido_opts = ["서울특별시", "부산광역시", "대구광역시", "인천광역시", "광주광역시", "대전광역시", "울산광역시", "세종특별자치시", "경기도", "강원특별자치도", "충청북도", "충청남도", "전북특별자치도", "전라남도", "경상북도", "경상남도", "제주특별자치도"]
        if user_input is not None:
            return self.async_create_entry(title="약국 정보", data={CONF_ENTRY_TYPE: ENTRY_PHARMACY, "api_key": user_input["api_key"], "q0": user_input["q0"], "q1": user_input.get("q1", "")})
        return self.async_show_form(step_id="pharmacy", data_schema=vol.Schema({vol.Required("api_key"): str, vol.Required("q0", default="서울특별시"): vol.In(sido_opts), vol.Optional("q1", default=""): str}))

    # ══════════ 에어코리아 ══════════
    async def async_step_airkorea(self, user_input=None) -> FlowResult:
        from .airkorea import STATIONS_BY_SIDO
        if user_input is not None:
            self._data = {CONF_ENTRY_TYPE: ENTRY_AIRKOREA, "api_key": user_input["api_key"], "living_api_key": user_input.get("living_api_key", "")}
            self._air_sido = user_input["sido"]
            return await self.async_step_airkorea_select()
        sido_opts = [{"value": k, "label": k} for k in STATIONS_BY_SIDO.keys()]
        return self.async_show_form(step_id="airkorea", data_schema=vol.Schema({
            vol.Required("api_key"): str, vol.Optional("living_api_key", default=""): str,
            vol.Required("sido", default="서울"): SelectSelector(SelectSelectorConfig(options=sido_opts, mode=SelectSelectorMode.DROPDOWN)),
        }))

    async def async_step_airkorea_select(self, user_input=None) -> FlowResult:
        import homeassistant.helpers.config_validation as cv
        from .airkorea import STATIONS_BY_SIDO
        if user_input is not None:
            self._data.update({"stations": [{"stationName": s} for s in user_input.get("stations", [])], "sido": self._air_sido})
            return self.async_create_entry(title="에어코리아", data=self._data)
        station_list = STATIONS_BY_SIDO.get(self._air_sido, [])
        return self.async_show_form(step_id="airkorea_select", data_schema=vol.Schema({vol.Required("stations", default=station_list[:3]): cv.multi_select({s: s for s in station_list})}))

    # ══════════ 기상청 날씨예보 ══════════
    async def async_step_kma_weather(self, user_input=None) -> FlowResult:
        from .kma_weather import SIDO_LIST
        if user_input is not None:
            self._data, self._kma_sido = {CONF_ENTRY_TYPE: ENTRY_KMA_WEATHER, "api_key": user_input["api_key"]}, user_input["sido"]
            return await self.async_step_kma_weather_sgg()
        sido_opts = [{"value": k, "label": k} for k in SIDO_LIST.keys()]
        return self.async_show_form(step_id="kma_weather", data_schema=vol.Schema({vol.Required("api_key"): str, vol.Required("sido"): SelectSelector(SelectSelectorConfig(options=sido_opts, mode=SelectSelectorMode.DROPDOWN))}))

    async def async_step_kma_weather_sgg(self, user_input=None) -> FlowResult:
        import homeassistant.helpers.config_validation as cv
        from .kma_weather import SIDO_LIST
        from .airkorea import STATIONS_BY_SIDO, SIDO_AREA_CODE
        sgg_map = SIDO_LIST.get(self._kma_sido, {})
        if user_input is not None:
            selected = user_input.get("regions", [])
            self._data.update({"regions": [{"name": r, "nx": sgg_map[r][0], "ny": sgg_map[r][1]} for r in selected if r in sgg_map],
                               "air_station": user_input.get("air_station", ""), "area_no": SIDO_AREA_CODE.get(self._kma_sido, ""), "sido": self._kma_sido})
            return self.async_create_entry(title="기상청 날씨예보", data=self._data)
        air_opts = {"": "사용 안 함", **{s: f"{s} (O₃/UV)" for s in STATIONS_BY_SIDO.get(self._kma_sido, [])[:30]}}
        return self.async_show_form(step_id="kma_weather_sgg", data_schema=vol.Schema({vol.Required("regions"): cv.multi_select({k: k for k in sgg_map.keys()}), vol.Optional("air_station", default=""): vol.In(air_opts)}))

    # ══════════ 지진 정보 ══════════
    async def async_step_earthquake(self, user_input=None) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="지진 정보", data={CONF_ENTRY_TYPE: ENTRY_EARTHQUAKE, "api_key": user_input["api_key"], "home_latitude": user_input.get("latitude", 37.5665), "home_longitude": user_input.get("longitude", 126.978), "radius_km": user_input.get("radius_km", 200), "min_magnitude": user_input.get("min_magnitude", 3.0)})
        return self.async_show_form(step_id="earthquake", data_schema=vol.Schema({vol.Required("api_key"): str, vol.Optional("latitude", default=37.5665): vol.Coerce(float), vol.Optional("longitude", default=126.978): vol.Coerce(float), vol.Optional("radius_km", default=200): vol.Coerce(int), vol.Optional("min_magnitude", default=3.0): vol.Coerce(float)}))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        """Get the options flow for this handler."""
        return KoreaOptionsFlow(config_entry)


class KoreaOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Korea integration."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry

    async def async_step_init(self, user_input: Optional[Dict[str, Any]] = None):
        """Manage the options."""
        service = self._config_entry.data.get("service")
        if service in [ENTRY_WEATHER, ENTRY_TRANSIT, ENTRY_FUEL, ENTRY_SCHOOL, ENTRY_DISASTER, ENTRY_SAFETY_ALERT, ENTRY_KEPCO, ENTRY_GASAPP, ENTRY_ARISU, ENTRY_PHARMACY, ENTRY_AIRKOREA, ENTRY_KMA_WEATHER, ENTRY_EARTHQUAKE, ENTRY_GOODSFLOW, ENTRY_KAKAOMAP]:
            # 새 서비스들은 옵션 플로우에서 기본 스키마 제공 가능 (필요시 상세 구현)
            if service == ENTRY_WEATHER:
                from .weather import AREA_CODES
                area_options = [{"value": c, "label": n} for c, n in AREA_CODES.items()]
                return self.async_show_form(step_id="init", data_schema=vol.Schema({
                    vol.Required("api_key", default=self._config_entry.data.get("api_key", "")): str,
                    vol.Required("area_codes", default=self._config_entry.data.get("area_codes", [])): SelectSelector(SelectSelectorConfig(options=area_options, multiple=True, mode=SelectSelectorMode.DROPDOWN)),
                }))
            return self.async_abort(reason=f"no_options_{service}")

async def fetch_stop_data(session: aiohttp.ClientSession, stop_id: str) -> dict:
    """Fetch bus stop data from KakaoMap."""
    url = f"https://map.kakao.com/bus/stop.json?busstopid={stop_id}"
    try:
        async with session.get(url, timeout=10) as response:
            if response.status != 200: return {}
            return await response.json()
    except Exception: return {}

def build_bus_labels(data: dict) -> dict:
    """Build bus labels from KakaoMap data."""
    labels = {}
    for bus in data.get("buses", []):
        name = bus.get("name", "Unknown")
        bus_id = bus.get("id", "")
        labels[bus_id] = name
    return labels
