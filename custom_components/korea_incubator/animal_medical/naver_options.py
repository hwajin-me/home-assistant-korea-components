"""Explicit selection from bounded public Naver search results."""

import voluptuous as vol
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import SelectSelector, SelectSelectorConfig

from .naver import NaverError, async_search


async def choose(flow, user_input=None):
    error = ""
    if user_input is not None:
        query = user_input["query"].strip()
        selected = user_input["selection"]
        if query == flow._naver_query and any(
            row["id"] == selected for row in flow._naver_items
        ):
            data = {
                **flow._medical_options,
                "naver_place_url": f"https://map.naver.com/p/entry/place/{selected}",
            }
            if dict(flow._config_entry.options) == data:
                flow.hass.config_entries.async_schedule_reload(
                    flow._config_entry.entry_id
                )
            return flow.async_create_entry(title="", data=data)
        flow._naver_query = query
    try:
        flow._naver_items = await async_search(
            async_get_clientsession(flow.hass),
            flow._naver_query,
            latitude=flow.hass.config.latitude,
            longitude=flow.hass.config.longitude,
        )
    except NaverError as err:
        flow._naver_items = []
        error = str(err)
    return flow.async_show_form(
        step_id="medical_naver",
        data_schema=vol.Schema(
            {
                vol.Required("query", default=flow._naver_query): vol.All(
                    str, vol.Length(min=1)
                ),
                vol.Required("selection", default="__search__"): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            {
                                "value": row["id"],
                                "label": f"{row['name']} | {row['address']} | {row['id']}",
                            }
                            for row in flow._naver_items
                        ]
                        + [{"value": "__search__", "label": "검색 / Search"}]
                    )
                ),
            }
        ),
        description_placeholders={"error": error},
    )
