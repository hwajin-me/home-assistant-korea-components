"""Search, pagination, selection and credential recovery for animal facilities."""

from __future__ import annotations

import logging
import math
import re

import voluptuous as vol
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import SelectSelector, SelectSelectorConfig

from ..const import CONF_ENTRY_TYPE, ENTRY_ANIMAL_MEDICAL
from . import CONF_INTERVAL, DEFAULT_INTERVAL, MAX_INTERVAL, MIN_INTERVAL
from .api import (
    MAX_ROWS,
    AnimalMedicalApiError,
    AnimalMedicalAuthError,
    async_fetch_institutions,
)
from .kakao_flow import KakaoPlaceFlow
from ..public_data import configured_data_go_kr_api_key

_LOGGER = logging.getLogger(__name__)


def interval_schema(default=DEFAULT_INTERVAL):
    """Minute-based polling setting shared by initial setup and options."""
    return {
        vol.Required(CONF_INTERVAL, default=default): vol.All(
            vol.Coerce(int), vol.Range(min=MIN_INTERVAL, max=MAX_INTERVAL)
        )
    }


class AnimalMedicalFlow(KakaoPlaceFlow):
    """Shared steps attached to the Korea config flow."""

    def _animal_search_form(self, errors=None, detail=""):
        values = getattr(self, "_animal_input", {})
        return self.async_show_form(
            step_id="animal_medical",
            data_schema=vol.Schema(
                {
                    **interval_schema(values.get(CONF_INTERVAL, DEFAULT_INTERVAL)),
                    vol.Required(
                        "api_key",
                        default=values.get("api_key")
                        or configured_data_go_kr_api_key(getattr(self, "hass", None)),
                    ): str,
                    vol.Required(
                        "institution_type",
                        default=values.get("institution_type", "hospital"),
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=["hospital", "pharmacy"],
                            translation_key="animal_type",
                        )
                    ),
                    vol.Required(
                        "search_method",
                        default=values.get("search_method", "road_address"),
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=["road_address", "municipality_code"],
                            translation_key="animal_search",
                        )
                    ),
                    vol.Optional(
                        "road_address", default=values.get("road_address", "")
                    ): str,
                    vol.Optional(
                        "municipality_code", default=values.get("municipality_code", "")
                    ): str,
                }
            ),
            errors=errors or {},
            description_placeholders={"error": detail},
        )

    async def async_step_animal_medical(self, user_input=None):
        """Search by address by default, or by a seven-digit municipality code."""
        if user_input is None:
            return self._animal_search_form()
        self._animal_input = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in user_input.items()
        }
        values = self._animal_input
        method = values["search_method"]
        if not values["api_key"]:
            return self._animal_search_form({"api_key": "animal_invalid_auth"})
        if not values.get(method):
            return self._animal_search_form({method: "required_search_value"})
        if method == "municipality_code" and not re.fullmatch(
            r"[0-9]{7}", values["municipality_code"]
        ):
            return self._animal_search_form(
                {"municipality_code": "animal_invalid_code"}
            )
        self._animal_medical_data = {
            "api_key": values["api_key"],
            "institution_type": values["institution_type"],
            "road_address": values.get("road_address", "")
            if method == "road_address"
            else "",
            "municipality_code": values.get("municipality_code", "")
            if method == "municipality_code"
            else "",
        }
        return await self._async_animal_medical_fetch_page(1)

    async def _async_animal_medical_fetch_page(self, page):
        """Only commit navigation after a successful response; preserve retry input."""
        try:
            items, total = await async_fetch_institutions(
                async_get_clientsession(self.hass),
                **self._animal_medical_data,
                page=page,
            )
        except AnimalMedicalApiError as err:
            _LOGGER.warning(
                "Animal medical search (%s), page %s: %s",
                self._animal_medical_data["institution_type"],
                page,
                err,
            )
            return self._animal_search_form(
                {
                    "base": "animal_invalid_auth"
                    if isinstance(err, AnimalMedicalAuthError)
                    else "animal_cannot_connect"
                },
                str(err),
            )
        # Missing IDs cannot be registered safely, but still allow navigation.
        self._animal_medical_results = [
            item
            for item in items
            if isinstance(item.get("MNG_NO"), str)
            and item["MNG_NO"]
            and isinstance(item.get("OPN_ATMY_GRP_CD"), str)
            and re.fullmatch(r"[0-9]{7}", item["OPN_ATMY_GRP_CD"])
        ]
        if not self._animal_medical_results and page == 1 and total <= MAX_ROWS:
            return self._animal_search_form({"base": "animal_no_results"})
        self._animal_medical_page = page
        self._animal_medical_total = total
        return await self.async_step_animal_medical_select()

    async def async_step_animal_medical_select(self, user_input=None):
        """Pick an exact record or navigate/search again without exposing page sizes."""
        pages = max(1, math.ceil(self._animal_medical_total / MAX_ROWS))
        errors = {}
        if user_input is not None:
            choice = user_input["selection"]
            if choice == "__search__":
                return self._animal_search_form()
            if choice == "__previous__" and self._animal_medical_page > 1:
                return await self._async_animal_medical_fetch_page(
                    self._animal_medical_page - 1
                )
            if choice == "__next__" and self._animal_medical_page < pages:
                return await self._async_animal_medical_fetch_page(
                    self._animal_medical_page + 1
                )
            selected = next(
                (
                    item
                    for item in self._animal_medical_results
                    if f"{item['OPN_ATMY_GRP_CD']}:{item['MNG_NO']}" == choice
                ),
                None,
            )
            if selected is not None:
                data = {
                    **self._animal_medical_data,
                    "municipality_code": selected["OPN_ATMY_GRP_CD"],
                    "management_number": selected["MNG_NO"],
                    "business_name": selected.get("BPLC_NM") or selected["MNG_NO"],
                    CONF_INTERVAL: self._animal_input.get(
                        CONF_INTERVAL, DEFAULT_INTERVAL
                    ),
                }
                await self.async_set_unique_id(
                    f"animal_{data['institution_type']}_{data['municipality_code']}_{data['management_number']}"
                )
                self._check_service_unique_id()
                return await self._async_link_kakao(selected, data)
            errors["selection"] = "animal_invalid_selection"

        korean = self.hass.config.language == "ko"
        options = []
        for item in self._animal_medical_results:
            label = " | ".join(
                str(value)
                for value in (
                    item.get("BPLC_NM") or item["MNG_NO"],
                    item.get("ROAD_NM_ADDR") or item.get("LOTNO_ADDR") or "",
                    item.get("SALS_STTS_NM") or "",
                    item["MNG_NO"],
                )
                if value
            )
            options.append(
                {
                    "value": f"{item['OPN_ATMY_GRP_CD']}:{item['MNG_NO']}",
                    "label": label,
                }
            )
        if self._animal_medical_page > 1:
            options.append(
                {
                    "value": "__previous__",
                    "label": "← 이전 페이지" if korean else "← Previous page",
                }
            )
        if self._animal_medical_page < pages:
            options.append(
                {
                    "value": "__next__",
                    "label": "다음 페이지 →" if korean else "Next page →",
                }
            )
        options.append(
            {"value": "__search__", "label": "다시 검색" if korean else "Search again"}
        )
        return self.async_show_form(
            step_id="animal_medical_select",
            data_schema=vol.Schema(
                {
                    vol.Required("selection"): SelectSelector(
                        SelectSelectorConfig(options=options)
                    ),
                }
            ),
            errors=errors,
            description_placeholders={
                "page": str(self._animal_medical_page),
                "pages": str(pages),
                "total": str(self._animal_medical_total),
            },
        )

    async def async_step_reauth(self, entry_data):
        """Recover an expired/revoked animal API key."""
        if entry_data.get(CONF_ENTRY_TYPE) == "pharmacy":
            return await self.async_step_pharmacy_reauth()
        if entry_data.get(CONF_ENTRY_TYPE) != ENTRY_ANIMAL_MEDICAL:
            return self.async_abort(reason="animal_reauth_unsupported")
        return await self.async_step_animal_medical_reauth()

    async def async_step_reconfigure(self, user_input=None):
        """Edit institution settings, validate selection, then link opening hours."""
        entry = self._get_reconfigure_entry()
        if entry.data.get(CONF_ENTRY_TYPE) == "pharmacy":
            return await self.async_step_pharmacy(user_input)
        values = {**entry.data, **entry.options}
        self._animal_input = {
            **values,
            "search_method": "road_address"
            if values.get("road_address")
            else "municipality_code",
        }
        return await self.async_step_animal_medical(user_input)

    async def async_step_animal_medical_reauth(self, user_input=None):
        errors = {}
        detail = ""
        if user_input is not None:
            entry = self._get_reauth_entry()
            api_key = user_input["api_key"].strip()
            try:
                if not api_key:
                    raise AnimalMedicalAuthError("Empty key")
                await async_fetch_institutions(
                    async_get_clientsession(self.hass),
                    api_key,
                    entry.data["institution_type"],
                    rows=1,
                    municipality_code=entry.data["municipality_code"],
                    business_name=entry.data["business_name"],
                )
            except AnimalMedicalApiError as err:
                detail = str(err)
                errors["base"] = (
                    "animal_invalid_auth"
                    if isinstance(err, AnimalMedicalAuthError)
                    else "animal_cannot_connect"
                )
                _LOGGER.warning("Animal medical reauthentication: %s", err)
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates={"api_key": api_key}
                )
        return self.async_show_form(
            step_id="animal_medical_reauth",
            data_schema=vol.Schema({vol.Required("api_key"): str}),
            errors=errors,
            description_placeholders={"error": detail},
        )
