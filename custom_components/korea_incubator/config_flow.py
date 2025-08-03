from __future__ import annotations

import ssl

import aiohttp
import certifi
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD
from homeassistant.core import callback
from typing import Any, Dict, Optional

from .const import DOMAIN, LOGGER
from .kepco.api import KepcoApiClient
from .kepco.exceptions import KepcoAuthError
from .gasapp.api import GasAppApiClient
from .gasapp.exceptions import GasAppAuthError
from .safety_alert.api import SafetyAlertApiClient
from .safety_alert.exceptions import SafetyAlertConnectionError
from .goodsflow.api import GoodsFlowApiClient
from .goodsflow.exceptions import GoodsFlowAuthError
from .arisu.api import ArisuApiClient
from .arisu.exceptions import ArisuAuthError
from .kakaomap.api import KakaoMapApiClient
from .kakaomap.exceptions import KakaoMapConnectionError
from .kakaomap.coordinates import convert_coordinates, validate_coordinates


class KoreaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Korea integration."""

    VERSION = 1

    async def async_step_user(self, user_input: Optional[Dict[str, Any]] = None):
        """Handle the initial step."""
        return self.async_show_menu(
            step_id="user",
            menu_options=["kepco", "gasapp", "safety_alert", "goodsflow", "arisu", "kakaomap"],
        )

    async def async_step_kepco(self, user_input: Optional[Dict[str, Any]] = None):
        """Handle KEPCO configuration."""
        errors: Dict[str, str] = {}

        if user_input is not None:
            async with aiohttp.ClientSession() as session:
                client = KepcoApiClient(session)
                client.set_credentials(user_input[CONF_USERNAME], user_input[CONF_PASSWORD])
                try:
                    if await client.async_login(
                            user_input[CONF_USERNAME],
                            user_input[CONF_PASSWORD]
                    ):
                        unique_id = f"kepco_{user_input[CONF_USERNAME]}"
                        await self.async_set_unique_id(unique_id)
                        self._abort_if_unique_id_configured()

                        user_input["service"] = "kepco"
                        return self.async_create_entry(title=f"한전 ({user_input[CONF_USERNAME]})", data=user_input)
                    else:
                        errors["base"] = "auth"
                except KepcoAuthError as e:
                    LOGGER.error(f"KEPCO login failed: {e}")
                    errors["base"] = "invalid_auth"
                except Exception as e:
                    LOGGER.error(f"KEPCO login failed: {e}")
                    errors["base"] = "unknown"

        return self.async_show_form(
            step_id="kepco",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    async def async_step_gasapp(self, user_input: Optional[Dict[str, Any]] = None):
        """Handle GasApp configuration."""
        errors: Dict[str, str] = {}

        if user_input is not None:
            async with aiohttp.ClientSession() as session:
                client = GasAppApiClient(session)
                client.set_credentials(
                    user_input["token"],
                    user_input["member_id"],
                    user_input["use_contract_num"]
                )
                try:
                    if await client.async_validate_credentials():
                        unique_id = f"gasapp_{user_input['use_contract_num']}"
                        await self.async_set_unique_id(unique_id)
                        self._abort_if_unique_id_configured()

                        user_input["service"] = "gasapp"
                        return self.async_create_entry(
                            title=f"가스앱 ({user_input['use_contract_num']})",
                            data=user_input
                        )
                    else:
                        errors["base"] = "auth"
                except GasAppAuthError as e:
                    LOGGER.error(f"GasApp authentication failed: {e}")
                    errors["base"] = "invalid_auth"
                except Exception as e:
                    LOGGER.error(f"GasApp connection failed: {e}")
                    errors["base"] = "unknown"

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
        )

    async def async_step_safety_alert(self, user_input: Optional[Dict[str, Any]] = None):
        """Handle Safety Alert configuration."""
        errors: Dict[str, str] = {}

        if user_input is not None:
            async with aiohttp.ClientSession() as session:
                client = SafetyAlertApiClient(session)
                try:
                    # Test the API with the provided area codes
                    area_code2 = user_input.get("area_code2") if user_input.get("area_code2") else None
                    area_code3 = user_input.get("area_code3") if user_input.get("area_code3") else None

                    alerts = await client.async_get_safety_alerts(
                        user_input["area_code"],
                        area_code2,
                        area_code3
                    )

                    unique_id = f"safety_alert_{user_input['area_code']}"
                    await self.async_set_unique_id(unique_id)
                    self._abort_if_unique_id_configured()

                    user_input["service"] = "safety_alert"
                    return self.async_create_entry(
                        title=f"안전알림 ({user_input['area_name']})",
                        data=user_input
                    )
                except SafetyAlertConnectionError as e:
                    LOGGER.error(f"Safety Alert connection failed: {e}")
                    errors["base"] = "cannot_connect"
                except Exception as e:
                    LOGGER.error(f"Safety Alert setup failed: {e}")
                    errors["base"] = "unknown"

        return self.async_show_form(
            step_id="safety_alert",
            data_schema=vol.Schema(
                {
                    vol.Required("area_code", default="1156000000"): str,
                    vol.Required("area_name", default="서울특별시"): str,
                    vol.Optional("area_code2"): str,
                    vol.Optional("area_name2"): str,
                    vol.Optional("area_code3"): str,
                    vol.Optional("area_name3"): str,
                }
            ),
            errors=errors,
        )

    async def async_step_goodsflow(self, user_input: Optional[Dict[str, Any]] = None):
        """Handle GoodsFlow configuration."""
        errors: Dict[str, str] = {}

        if user_input is not None:
            async with aiohttp.ClientSession() as session:
                client = GoodsFlowApiClient(session)
                client.set_token(user_input["token"])
                try:
                    if await client.async_validate_token():
                        unique_id = f"goodsflow_{user_input['token'][:8]}"
                        await self.async_set_unique_id(unique_id)
                        self._abort_if_unique_id_configured()

                        user_input["service"] = "goodsflow"
                        return self.async_create_entry(
                            title="굿스플로우 택배조회",
                            data=user_input
                        )
                    else:
                        errors["base"] = "invalid_auth"
                except GoodsFlowAuthError as e:
                    LOGGER.error(f"GoodsFlow authentication failed: {e}")
                    errors["base"] = "invalid_auth"
                except Exception as e:
                    LOGGER.error(f"GoodsFlow connection failed: {e}")
                    errors["base"] = "unknown"

        return self.async_show_form(
            step_id="goodsflow",
            data_schema=vol.Schema(
                {
                    vol.Required("token"): str,
                }
            ),
            errors=errors,
        )

    async def async_step_arisu(self, user_input: Optional[Dict[str, Any]] = None):
        """Handle Arisu configuration."""
        errors: Dict[str, str] = {}

        if user_input is not None:
            async with aiohttp.ClientSession() as session:
                client = ArisuApiClient(session)
                try:
                    # Test the API with the provided credentials (both customer number and name)
                    bill_data = await client.async_get_water_bill_data(
                        user_input["customer_number"],
                        user_input["customer_name"]
                    )

                    if bill_data.get("success", False):
                        unique_id = f"arisu_{user_input['customer_number']}"
                        await self.async_set_unique_id(unique_id)
                        self._abort_if_unique_id_configured()

                        user_input["service"] = "arisu"
                        return self.async_create_entry(
                            title=f"아리수 ({user_input['customer_number']})",
                            data=user_input
                        )
                    else:
                        errors["base"] = "invalid_auth"
                except ArisuAuthError as e:
                    LOGGER.error(f"Arisu authentication failed: {e}")
                    errors["base"] = "invalid_auth"
                except Exception as e:
                    LOGGER.error(f"Arisu connection failed: {e}")
                    errors["base"] = "unknown"

        return self.async_show_form(
            step_id="arisu",
            data_schema=vol.Schema(
                {
                    vol.Required("customer_number"): str,
                    vol.Required("customer_name"): str,
                }
            ),
            errors=errors,
        )

    async def async_step_kakaomap(self, user_input: Optional[Dict[str, Any]] = None):
        """Handle KakaoMap configuration."""
        errors: Dict[str, str] = {}

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
                            "latitude": float(user_input["start_y"])
                        }
                        end_coords_input = {
                            "longitude": float(user_input["end_x"]),
                            "latitude": float(user_input["end_y"])
                        }

                        # 좌표 유효성 검사
                        if not validate_coordinates(start_coords_input, "WGS84"):
                            errors["start_x"] = "invalid_wgs84_coordinates"
                        if not validate_coordinates(end_coords_input, "WGS84"):
                            errors["end_x"] = "invalid_wgs84_coordinates"

                        if not errors:
                            # WGS84를 WCONGNAMUL로 변환
                            start_coords = convert_coordinates(start_coords_input, "WGS84", "WCONGNAMUL")
                            end_coords = convert_coordinates(end_coords_input, "WGS84", "WCONGNAMUL")
                    else:
                        # WCONGNAMUL 좌표를 입력받은 경우
                        start_coords = {
                            "x": float(user_input["start_x"]),
                            "y": float(user_input["start_y"])
                        }
                        end_coords = {
                            "x": float(user_input["end_x"]),
                            "y": float(user_input["end_y"])
                        }

                        # 좌표 유효성 검사
                        if not validate_coordinates(start_coords, "WCONGNAMUL"):
                            errors["start_x"] = "invalid_wcongnamul_coordinates"
                        if not validate_coordinates(end_coords, "WCONGNAMUL"):
                            errors["end_x"] = "invalid_wcongnamul_coordinates"

                    if not errors:
                        # Test coordinate to address conversion
                        start_address = await client.async_coordinate_to_address(
                            start_coords["x"], start_coords["y"]
                        )

                        if start_address.get("success"):
                            unique_id = f"kakaomap_{user_input['name'].replace(' ', '_')}"
                            await self.async_set_unique_id(unique_id)
                            self._abort_if_unique_id_configured()

                            user_input["service"] = "kakaomap"
                            user_input["start_coords"] = start_coords
                            user_input["end_coords"] = end_coords
                            # 원본 좌표계 정보도 저장 (참고용)
                            user_input["original_coord_system"] = coord_system

                            return self.async_create_entry(
                                title=f"카카오맵 ({user_input['name']})",
                                data=user_input
                            )
                        else:
                            errors["base"] = "invalid_coordinates"

                except KakaoMapConnectionError as e:
                    LOGGER.error(f"KakaoMap connection failed: {e}")
                    errors["base"] = "cannot_connect"
                except ValueError as e:
                    LOGGER.error(f"Invalid coordinates: {e}")
                    errors["base"] = "invalid_coordinates"
                except Exception as e:
                    LOGGER.error(f"KakaoMap setup failed: {e}")
                    errors["base"] = "unknown"

        return self.async_show_form(
            step_id="kakaomap",
            data_schema=vol.Schema(
                {
                    vol.Required("name", default="집↔회사"): str,
                    vol.Required("coord_system", default="WCONGNAMUL"): vol.In([
                        "WCONGNAMUL", "WGS84"
                    ]),
                    vol.Required("start_x", default="515290"): str,  # 기본값: WCONGNAMUL 건대입구역
                    vol.Required("start_y", default="1122478"): str,
                    vol.Required("end_x", default="506190"): str,   # 기본값: WCONGNAMUL 강남역
                    vol.Required("end_y", default="1110730"): str,
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        """Get the options flow for this handler."""
        return KoreaOptionsFlow(config_entry)


class KoreaOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Korea integration."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input: Optional[Dict[str, Any]] = None):
        """Manage the options."""
        service = self.config_entry.data.get("service")
        if service == "kepco":
            return self.async_abort(reason="no_options_kepco")
        elif service == "gasapp":
            return self.async_abort(reason="no_options_gasapp")
        elif service == "safety_alert":
            return self.async_abort(reason="no_options_safety_alert")
        elif service == "goodsflow":
            return self.async_abort(reason="no_options_goodsflow")
        elif service == "arisu":
            return self.async_abort(reason="no_options_arisu")
        elif service == "kakaomap":
            return self.async_abort(reason="no_options_kakaomap")

        return self.async_abort(reason="no_options")
