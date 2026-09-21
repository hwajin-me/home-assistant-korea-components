"""Search and select a single pharmacy, then link Kakao opening hours."""

import logging
import math

import voluptuous as vol
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import SelectSelector, SelectSelectorConfig

from ..animal_medical import CONF_INTERVAL, DEFAULT_INTERVAL, MAX_INTERVAL
from ..animal_medical.api import AnimalMedicalApiError, AnimalMedicalAuthError
from . import PAGE_SIZE
from .api import fetch_detail, fetch_page

_LOGGER = logging.getLogger(__name__)


class PharmacyFlow:
    async def async_step_pharmacy(self, user_input=None):
        if not hasattr(self, "_pharmacy_input"):
            self._pharmacy_input = (
                {
                    **self._get_reconfigure_entry().data,
                    **self._get_reconfigure_entry().options,
                }
                if self.context.get("source") == "reconfigure"
                else {}
            )
        if user_input is not None:
            self._pharmacy_input = {
                **user_input,
                "api_key": user_input["api_key"].strip(),
            }
            self._pharmacy_items = self._pharmacy_raw = []
            self._pharmacy_page = self._pharmacy_pages = 1
            return await self._async_pharmacy_page(1)
        data = self._pharmacy_input
        return self.async_show_form(
            step_id="pharmacy",
            data_schema=vol.Schema(
                {
                    vol.Required("api_key", default=data.get("api_key", "")): str,
                    vol.Required("q0", default=data.get("q0", "서울특별시")): str,
                    vol.Optional("q1", default=data.get("q1", "")): str,
                    vol.Optional("name", default=data.get("name", "")): str,
                    vol.Optional(
                        "road_address", default=data.get("road_address", "")
                    ): str,
                    vol.Required(
                        CONF_INTERVAL, default=data.get(CONF_INTERVAL, DEFAULT_INTERVAL)
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=MAX_INTERVAL)),
                }
            ),
        )

    async def _async_pharmacy_page(self, page):
        data = self._pharmacy_input
        try:
            items, total = await fetch_page(
                async_get_clientsession(self.hass),
                data["api_key"],
                data["q0"],
                data.get("q1", ""),
                name=data.get("name", ""),
                page=page,
            )
            if page != self._pharmacy_page and items and items == self._pharmacy_raw:
                raise AnimalMedicalApiError("Pharmacy API repeated the previous page")
            if not items and (page - 1) * PAGE_SIZE < total:
                raise AnimalMedicalApiError("Pharmacy API returned an incomplete page")
        except AnimalMedicalApiError as err:
            return self._pharmacy_form(
                "animal_invalid_auth"
                if isinstance(err, AnimalMedicalAuthError)
                else "animal_cannot_connect",
                str(err),
            )
        self._pharmacy_raw = items
        self._pharmacy_page, self._pharmacy_pages = (
            page,
            max(1, math.ceil(total / PAGE_SIZE)),
        )
        address = "".join(data.get("road_address", "").split())
        self._pharmacy_items = [
            item
            for item in items
            if item.get("hpid") and address in "".join(item.get("dutyAddr", "").split())
        ]
        return self._pharmacy_form("" if self._pharmacy_items else "animal_no_results")

    async def async_step_pharmacy_select(self, user_input=None):
        if user_input is None:
            return self._pharmacy_form()
        choice = user_input["selection"]
        if choice == "__search__":
            return await self.async_step_pharmacy()
        if choice == "__next__" and self._pharmacy_page < self._pharmacy_pages:
            return await self._async_pharmacy_page(self._pharmacy_page + 1)
        if choice == "__previous__" and self._pharmacy_page > 1:
            return await self._async_pharmacy_page(self._pharmacy_page - 1)
        selected = next(
            (item for item in self._pharmacy_items if item["hpid"] == choice), None
        )
        if selected is None:
            return self._pharmacy_form("animal_invalid_selection")
        await self.async_set_unique_id(f"pharmacy_{choice}")
        existing = self.hass.config_entries.async_entry_for_domain_unique_id(
            self.handler, self.unique_id
        )
        if existing is not None and (
            self.context.get("source") != "reconfigure"
            or existing.entry_id != self._get_reconfigure_entry().entry_id
        ):
            return self.async_abort(reason="already_configured")
        try:
            selected = await fetch_detail(
                async_get_clientsession(self.hass),
                self._pharmacy_input["api_key"],
                choice,
            )
        except AnimalMedicalApiError as err:
            return self._pharmacy_form(
                "animal_invalid_auth"
                if isinstance(err, AnimalMedicalAuthError)
                else "animal_cannot_connect",
                str(err),
            )
        data = {
            **self._pharmacy_input,
            "service": "pharmacy",
            "hpid": choice,
            "business_name": selected.get("dutyName") or choice,
        }
        if self.context.get("source") == "reconfigure":
            old = self._get_reconfigure_entry().data
            if not old.get("hpid"):
                from ..const import DOMAIN

                data["legacy_count_unique_id"] = (
                    f"{DOMAIN}_pharmacy_{old['q0']}_{old.get('q1', '')}"
                )
        return await self._async_link_kakao(
            {
                "BPLC_NM": data["business_name"],
                "ROAD_NM_ADDR": selected.get("dutyAddr", ""),
                "TELNO": selected.get("dutyTel1", ""),
            },
            data,
        )

    def _pharmacy_form(self, error="", detail=""):
        if detail:
            _LOGGER.warning("Pharmacy configuration: %s", detail)
        ko = self.hass.config.language == "ko"
        options = [
            {
                "value": item["hpid"],
                "label": " | ".join(
                    (item.get("dutyName", ""), item.get("dutyAddr", ""), item["hpid"])
                ),
            }
            for item in self._pharmacy_items
        ]
        if self._pharmacy_page > 1:
            options.append(
                {"value": "__previous__", "label": "← 이전" if ko else "← Previous"}
            )
        if self._pharmacy_page < self._pharmacy_pages:
            options.append({"value": "__next__", "label": "다음 →" if ko else "Next →"})
        options.append(
            {"value": "__search__", "label": "다시 검색" if ko else "Search again"}
        )
        return self.async_show_form(
            step_id="pharmacy_select",
            data_schema=vol.Schema(
                {
                    vol.Required("selection"): SelectSelector(
                        SelectSelectorConfig(options=options)
                    )
                }
            ),
            errors={"base": error} if error else {},
            description_placeholders={
                "page": str(self._pharmacy_page),
                "pages": str(self._pharmacy_pages),
                "error": detail,
            },
        )

    async def async_step_pharmacy_reauth(self, user_input=None):
        errors, detail = {}, ""
        if user_input is not None:
            entry = self._get_reauth_entry()
            key = user_input["api_key"].strip()
            try:
                await fetch_detail(
                    async_get_clientsession(self.hass), key, entry.data["hpid"]
                )
            except AnimalMedicalApiError as err:
                errors["base"] = (
                    "animal_invalid_auth"
                    if isinstance(err, AnimalMedicalAuthError)
                    else "animal_cannot_connect"
                )
                detail = str(err)
                _LOGGER.warning("Pharmacy reauthentication: %s", err)
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates={"api_key": key}
                )
        return self.async_show_form(
            step_id="pharmacy_reauth",
            data_schema=vol.Schema({vol.Required("api_key"): str}),
            errors=errors,
            description_placeholders={"error": detail},
        )
