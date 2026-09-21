"""Automatic exact matching and paginated manual Kakao place selection."""

import logging

import voluptuous as vol
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import SelectSelector, SelectSelectorConfig

from ..const import CONF_ENTRY_TYPE, ENTRY_ANIMAL_MEDICAL
from .kakao import KakaoError, async_place, async_search, exact_candidate
from .services import group_title

_LOGGER = logging.getLogger(__name__)


class KakaoPlaceFlow:
    """Mixin for the animal facility flow; credentials never enter entry data."""

    async def _async_link_kakao(self, record, entry_data):
        self._kakao_record = record
        self._kakao_entry = entry_data
        region = " ".join((record.get("ROAD_NM_ADDR") or "").split()[:2])
        self._kakao_query = f"{region} {entry_data['business_name']}".strip()
        self._kakao_items = []
        self._kakao_page = self._kakao_pages = 1
        return await self._async_kakao_page(1, automatic=True)

    async def _async_kakao_page(self, page, automatic=False):
        try:
            items, pages = await async_search(
                async_get_clientsession(self.hass), self._kakao_query, page
            )
            if page != self._kakao_page and items and items == self._kakao_items:
                raise KakaoError("Kakao repeated the previous page")
        except KakaoError as err:
            return self._kakao_form("animal_kakao_error", str(err))
        self._kakao_items, self._kakao_page, self._kakao_pages = items, page, pages
        # Never auto-select against an incomplete candidate set.
        candidate = exact_candidate(self._kakao_record, items) if pages == 1 else None
        if automatic and candidate is not None:
            return await self._async_kakao_finish(candidate["id"])
        return self._kakao_form("" if items else "animal_kakao_no_results")

    async def _async_kakao_finish(self, place_id):
        try:
            await async_place(async_get_clientsession(self.hass), place_id)
        except KakaoError as err:
            return self._kakao_form("animal_kakao_error", str(err))
        data = {
            CONF_ENTRY_TYPE: ENTRY_ANIMAL_MEDICAL,
            **self._kakao_entry,
            "kakao_place_id": place_id,
        }
        if self.context.get("source") == "reconfigure":
            self._medical_edit_data = data
            entry = self._get_reconfigure_entry()
            same = all(
                entry.data.get(key) == data.get(key)
                for key in (
                    "hpid",
                    "institution_type",
                    "municipality_code",
                    "management_number",
                )
            )
            self._medical_edit_values = {
                "kakao_place_id": place_id,
                "naver_place_url": (
                    entry.options.get(
                        "naver_place_url", entry.data.get("naver_place_url", "")
                    )
                    if same
                    else ""
                ),
            }
            return await self.async_step_medical_links()
        return self._finish_service_entry(
            title=group_title(data),
            data={CONF_ENTRY_TYPE: ENTRY_ANIMAL_MEDICAL, **data},
        )

    async def async_step_medical_links(self, user_input=None):
        """Review both map links before committing any reconfiguration."""
        from .naver import place_id as naver_place_id

        errors = {}
        detail = ""
        if user_input is not None:
            self._medical_edit_values.update(user_input)
            kakao = self._medical_edit_values["kakao_place_id"].strip()
            naver = self._medical_edit_values["naver_place_url"].strip()
            if not kakao.isascii() or not kakao.isdigit():
                errors["kakao_place_id"] = "animal_invalid_selection"
            try:
                naver = (
                    f"https://map.naver.com/p/entry/place/{naver_place_id(naver)}"
                    if naver
                    else ""
                )
            except ValueError:
                errors["naver_place_url"] = "invalid_naver_url"
            if not errors:
                try:
                    await async_place(async_get_clientsession(self.hass), kakao)
                except KakaoError as err:
                    errors["kakao_place_id"] = "animal_kakao_error"
                    detail = str(err)
                else:
                    data = {
                        **self._medical_edit_data,
                        "kakao_place_id": kakao,
                        "naver_place_url": naver,
                    }
                    return self._finish_service_entry(
                        title=group_title(data), data=data
                    )
        return self.async_show_form(
            step_id="medical_links",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "kakao_place_id",
                        default=self._medical_edit_values["kakao_place_id"],
                    ): str,
                    vol.Optional(
                        "naver_place_url",
                        default=self._medical_edit_values["naver_place_url"],
                    ): str,
                }
            ),
            errors=errors,
            description_placeholders={"error": detail},
        )

    async def async_step_animal_kakao(self, user_input=None):
        if user_input is None:
            return self._kakao_form()
        query = user_input.get("query", self._kakao_query).strip()
        choice = user_input.get("selection", "__retry__")
        if not query:
            return self._kakao_form("required_search_value")
        if query != self._kakao_query:
            self._kakao_query = query
            self._kakao_items = []
            self._kakao_page = self._kakao_pages = 1
            return await self._async_kakao_page(1, automatic=True)
        if choice == "__retry__":
            return await self._async_kakao_page(self._kakao_page, automatic=True)
        if choice == "__previous__" and self._kakao_page > 1:
            return await self._async_kakao_page(self._kakao_page - 1)
        if choice == "__next__" and self._kakao_page < self._kakao_pages:
            return await self._async_kakao_page(self._kakao_page + 1)
        if any(item["id"] == choice for item in self._kakao_items):
            return await self._async_kakao_finish(choice)
        return self._kakao_form("animal_invalid_selection")

    def _kakao_form(self, error="", detail=""):
        if detail:
            _LOGGER.warning("Animal medical Kakao configuration: %s", detail)
        korean = self.hass.config.language == "ko"
        options = [
            {
                "value": item["id"],
                "label": " | ".join(
                    (item["name"], item["address"], item["phone"], item["id"])
                ),
            }
            for item in self._kakao_items
        ]
        if self._kakao_page > 1:
            options.append(
                {
                    "value": "__previous__",
                    "label": "← 이전 페이지" if korean else "← Previous page",
                }
            )
        if self._kakao_page < self._kakao_pages:
            options.append(
                {
                    "value": "__next__",
                    "label": "다음 페이지 →" if korean else "Next page →",
                }
            )
        options.append(
            {
                "value": "__retry__",
                "label": "검색 / 다시 시도" if korean else "Search / Retry",
            }
        )
        return self.async_show_form(
            step_id="animal_kakao",
            data_schema=vol.Schema(
                {
                    vol.Required("query", default=self._kakao_query): str,
                    vol.Required("selection", default="__retry__"): SelectSelector(
                        SelectSelectorConfig(options=options)
                    ),
                }
            ),
            errors={"base": error} if error else {},
            description_placeholders={
                "page": str(self._kakao_page),
                "pages": str(self._kakao_pages),
                "error": detail,
            },
        )
