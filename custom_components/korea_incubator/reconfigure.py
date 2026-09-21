"""Shared reconfiguration support for the service setup flows."""

from copy import copy, deepcopy

import voluptuous as vol
from homeassistant.data_entry_flow import AbortFlow

from .const import CONF_ENTRY_TYPE


class ServiceReconfigureFlow:
    """Reuse service validation while updating the selected entry in place."""

    async def async_step_reconfigure(self, user_input=None):
        entry = self._get_reconfigure_entry()
        service = entry.data.get(CONF_ENTRY_TYPE)
        if service in {"animal_medical", "pharmacy"}:
            # These flows also link institution-specific opening hours.
            return await super().async_step_reconfigure(user_input)
        steps = {
            "kepco",
            "gasapp",
            "goodsflow",
            "cj_one_delivery",
            "arisu",
            "kakaomap",
            "weather_warning",
            "transit",
            "fuel",
            "school",
            "disaster",
            "airkorea",
            "kma_weather",
            "earthquake",
            "dh_lottery",
            "safety_alert",
        }
        if service not in steps:
            return self.async_abort(reason="reconfigure_unsupported")
        self._reconfigure_entry = entry
        self._reconfigure_values = deepcopy({**entry.data, **entry.options})
        if service == "safety_alert" and entry.data.get("grouped"):
            return await self.async_step_safety_alert_region(user_input)
        return await getattr(self, f"async_step_{service}")(user_input)

    async def async_step_safety_alert_region(self, user_input=None):
        """Choose one region without discarding the other configured regions."""
        entry = self._reconfigure_entry
        regions = {**entry.data.get("regions", {})}
        regions.update(
            {
                key: sub.data
                for key, sub in entry.subentries.items()
                if sub.subentry_type == "region"
            }
        )
        if user_input is not None:
            key = user_input["region"]
            self._reconfigure_region = key
            self._reconfigure_values = deepcopy(dict(regions[key]))
            return await self.async_step_safety_alert()
        if not regions:
            self._reconfigure_region = None
            return await self.async_step_safety_alert()
        return self.async_show_form(
            step_id="safety_alert_region",
            data_schema=vol.Schema(
                {
                    vol.Required("region"): vol.In(
                        {
                            key: data.get("area_name", key)
                            for key, data in regions.items()
                        }
                    )
                }
            ),
        )

    def _check_service_unique_id(self):
        entry = getattr(self, "_reconfigure_entry", None)
        if entry is None:
            return self._abort_if_unique_id_configured()
        existing = self.hass.config_entries.async_entry_for_domain_unique_id(
            self.handler, self.unique_id
        )
        if existing is not None and existing.entry_id != entry.entry_id:
            raise AbortFlow("already_configured")
        # Account-derived entity IDs must continue to refer to the same account.
        if (
            entry.data[CONF_ENTRY_TYPE]
            in {"kepco", "gasapp", "arisu", "dh_lottery", "cj_one_delivery"}
            and entry.unique_id is not None
            and entry.unique_id != self.unique_id
        ):
            raise AbortFlow("reconfigure_account_mismatch")

    def _finish_service_entry(self, *, title, data, options=None):
        entry = getattr(self, "_reconfigure_entry", None)
        if entry is None:
            kwargs = {} if options is None else {"options": options}
            return self.async_create_entry(title=title, data=data, **kwargs)
        if entry.data[CONF_ENTRY_TYPE] == "goodsflow":
            # A refreshed token must not rename existing devices and entities.
            data = {
                **data,
                "device_unique_id": entry.data.get("device_unique_id")
                or f"goodsflow_{entry.data['token'][:8]}",
            }
        # Remove old options which would override newly validated connection data.
        new_options = {
            key: value for key, value in entry.options.items() if key not in data
        }
        if options is not None:
            new_options.update(options)
        updates = dict(
            data=data, options=new_options, unique_id=self.unique_id or entry.unique_id
        )
        if entry.update_listeners:
            # KakaoMap's listener reloads; CJ's listener only adjusts polling.
            changed = self.hass.config_entries.async_update_entry(entry, **updates)
            if not changed or entry.data[CONF_ENTRY_TYPE] != "kakaomap":
                self.hass.config_entries.async_schedule_reload(entry.entry_id)
            return self.async_abort(reason="reconfigure_successful")
        return self.async_update_reload_and_abort(
            entry, **updates, reason="reconfigure_successful"
        )

    def _show_service_form(self, *, data_schema=None, **kwargs):
        """Prefill only valid choices; dependent selectors may have changed."""
        entry = getattr(self, "_reconfigure_entry", None)
        if entry is None or data_schema is None:
            return self.async_show_form(data_schema=data_schema, **kwargs)
        values = deepcopy(self._reconfigure_values)
        service = entry.data[CONF_ENTRY_TYPE]
        step = kwargs.get("step_id")
        if service == "earthquake":
            values["latitude"] = values.get("home_latitude", 37.5665)
            values["longitude"] = values.get("home_longitude", 126.978)
        elif service == "fuel":
            for field in ("sido", "fuel"):
                values[f"{field}_codes"] = list(
                    dict.fromkeys(
                        item[f"{field}_code"] for item in values.get("configs", [])
                    )
                )
        elif service == "airkorea" and step == "airkorea_select":
            values["stations"] = [
                item["stationName"] for item in values.get("stations", [])
            ]
        elif service == "kma_weather" and step == "kma_weather_sgg":
            values["regions"] = [item["name"] for item in values.get("regions", [])]
        elif service == "kakaomap":
            values["coord_system"] = values.get("original_coord_system", "WCONGNAMUL")
            for field in ("start_x", "start_y", "end_x", "end_y"):
                if field in values:
                    values[field] = str(values[field])
        elif service == "school":
            values["school_search"] = values.get("school_name", "")
        elif service == "safety_alert":
            values["sido_code"] = values.get("sido_code") or values.get("area_code", "")
            values["sgg_code"] = values.get("area_code2", "")
            values["emd_code"] = values.get("area_code3", "")
            values["emd_name"] = values.get("area_name3", "")
        elif service == "disaster":
            region = values.get("region_filter", "")
            if region not in {
                "",
                "서울",
                "부산",
                "대구",
                "인천",
                "광주",
                "대전",
                "울산",
                "세종",
                "경기",
                "강원",
                "충북",
                "충남",
                "전북",
                "전남",
                "경북",
                "경남",
                "제주",
            }:
                values.update(region_filter="", sub_region=region)
        schema = {}
        for marker, validator in data_schema.schema.items():
            new_marker = copy(marker)
            if isinstance(marker, vol.Marker) and marker.schema in values:
                try:
                    value = vol.Schema(validator)(values[marker.schema])
                except vol.Invalid:
                    pass
                else:
                    new_marker.default = vol.default_factory(value)
            schema[new_marker] = validator
        return self.async_show_form(data_schema=vol.Schema(schema), **kwargs)
