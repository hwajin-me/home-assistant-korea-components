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
            "animal_medical",
            "pharmacy",
        }
        if service not in steps:
            return self.async_abort(reason="reconfigure_unsupported")
        self._reconfigure_entry = entry
        self._reconfigure_values = deepcopy({**entry.data, **entry.options})
        self._service_inputs = {}
        if service in {"animal_medical", "pharmacy"}:
            return await super().async_step_reconfigure(user_input)
        if service == "safety_alert" and entry.data.get("grouped"):
            return await self.async_step_safety_alert_region(user_input)
        return await getattr(self, f"async_step_{service}")(user_input)

    async def async_step_reauth(self, entry_data):
        """Use the same validated credential steps when HA requests authentication."""
        if entry_data.get(CONF_ENTRY_TYPE) in {"animal_medical", "pharmacy"}:
            return await super().async_step_reauth(entry_data)
        service = entry_data.get(CONF_ENTRY_TYPE)
        if service not in {
            "kepco",
            "gasapp",
            "goodsflow",
            "arisu",
            "kakaomap",
            "dh_lottery",
            "cj_one_delivery",
            "weather_warning",
            "fuel",
            "school",
            "disaster",
            "airkorea",
            "kma_weather",
            "earthquake",
            "transit",
        }:
            return self.async_abort(reason="reconfigure_unsupported")
        entry = self._get_reauth_entry()
        self._reconfigure_entry = entry
        self._reconfigure_values = deepcopy({**entry.data, **entry.options})
        self._service_inputs = {}
        return await getattr(self, f"async_step_{service}")()

    async def _async_validate_public_service(self, service, user_input):
        """Return a retryable form if the API rejects the proposed settings."""
        import aiohttp
        from homeassistant.helpers.aiohttp_client import async_get_clientsession
        from .config_validation import PublicDataAuthError, validate_service

        try:
            await validate_service(
                async_get_clientsession(self.hass), service, user_input
            )
        except PublicDataAuthError as err:
            error, detail = "invalid_api_key", str(err)
        except (aiohttp.ClientError, TimeoutError, ConnectionError) as err:
            error, detail = "cannot_connect", str(err)
        else:
            return None
        result = await getattr(self, f"async_step_{service}")()
        result["errors"] = {"base": error}
        result["description_placeholders"] = {"error": detail[:500]}
        return result

    def _remember_service_input(self, step_id, user_input):
        """Keep rejected edits in the form without changing persisted settings."""
        if user_input is not None:
            if not hasattr(self, "_service_inputs"):
                self._service_inputs = {}
            self._service_inputs[step_id] = deepcopy(user_input)

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
        from .animal_medical.group import FacilityEntry
        for saved in self._async_current_entries():
            for key, member in saved.data.get("facilities", {}).items():
                if member.get("unique_id") == self.unique_id and not (
                    isinstance(entry, FacilityEntry) and entry.parent == saved and entry.key == key
                ):
                    raise AbortFlow("already_configured")
        if entry is None:
            return self._abort_if_unique_id_configured()
        existing = self.hass.config_entries.async_entry_for_domain_unique_id(
            self.handler, self.unique_id
        )
        if existing is not None and existing.entry_id != entry.entry_id:
            raise AbortFlow("already_configured")
        # Account-derived entity IDs must continue to refer to the same account.
        identity_fields = {
            "kepco": "username",
            "gasapp": "use_contract_num",
            "arisu": "customer_number",
            "dh_lottery": "username",
            "cj_one_delivery": "phone_number",
        }
        service = entry.data[CONF_ENTRY_TYPE]
        if service in identity_fields:
            identity = str(entry.data.get(identity_fields[service], ""))
            if service == "cj_one_delivery":
                identity = "".join(char for char in identity if char.isdigit())
            expected = f"{service}_{identity}" if identity else entry.unique_id
            if expected is not None and expected != self.unique_id:
                raise AbortFlow("reconfigure_account_mismatch")

    def _finish_service_entry(self, *, title, data, options=None):
        entry = getattr(self, "_reconfigure_entry", None)
        if entry is None:
            if data.get(CONF_ENTRY_TYPE) == "animal_medical":
                from .animal_medical.group import add_facility
                if result := add_facility(self, data, options):
                    return result
            # A reconfigured entry may still own its original device identity.
            # Adding that original institution/token again must not attach the
            # new entry to those retained entities.
            identity = None
            if data.get(CONF_ENTRY_TYPE) == "goodsflow":
                identity = f"goodsflow_{data['token'][:8]}"
            elif data.get(CONF_ENTRY_TYPE) in {"animal_medical", "pharmacy"}:
                from .animal_medical.sensor import institution_identifier

                identity = institution_identifier(data)
            if identity is not None and any(
                saved.data.get("device_unique_id") == identity
                for saved in self._async_current_entries()
            ):
                from uuid import uuid4

                data = {**data, "device_unique_id": f"{identity}_{uuid4().hex}"}
            kwargs = {} if options is None else {"options": options}
            return self.async_create_entry(title=title, data=data, **kwargs)
        if entry.data[CONF_ENTRY_TYPE] == "goodsflow":
            # A refreshed token must not rename existing devices and entities.
            data = {
                **data,
                "device_unique_id": entry.data.get("device_unique_id")
                or f"goodsflow_{entry.data['token'][:8]}",
            }
        if entry.data[CONF_ENTRY_TYPE] in {"animal_medical", "pharmacy"}:
            from .animal_medical.sensor import institution_identifier

            same_institution = all(
                entry.data.get(field) == data.get(field)
                for field in (
                    "hpid",
                    "institution_type",
                    "municipality_code",
                    "management_number",
                )
            )
            # Keep stable entity IDs, but never carry another institution's place links.
            preserved = (
                {**entry.data, **entry.options}
                if same_institution
                else {
                    key: value
                    for key, value in entry.data.items()
                    if key.startswith("legacy_")
                }
            )
            data = {
                **preserved,
                **data,
                "device_unique_id": institution_identifier(
                    entry.data
                    if entry.data.get("hpid") or entry.data.get("management_number")
                    else data
                ),
            }
        else:
            same_institution = True
        # Remove old options which would override newly validated connection data.
        new_options = {
            key: value
            for key, value in entry.options.items()
            if key not in data
            and (
                same_institution
                or key not in {"naver_place_url", "naver_query", "kakao_place_id"}
            )
        }
        if options is not None:
            new_options.update(options)
        updates = dict(
            data=data, options=new_options, unique_id=self.unique_id or entry.unique_id
        )
        reason = (
            "reauth_successful"
            if self.context.get("source") == "reauth"
            else "reconfigure_successful"
        )
        from .animal_medical.group import FacilityEntry, save_facility
        if isinstance(entry, FacilityEntry):
            if data["institution_type"] != entry.parent.data["institution_type"]:
                return self.async_abort(reason="medical_type_mismatch")
            save_facility(self.hass, entry, **updates)
            return self.async_abort(reason=reason)
        if entry.update_listeners:
            # Connection-data listeners reload once, including CJ and medical entries.
            changed = self.hass.config_entries.async_update_entry(entry, **updates)
            if not changed:
                self.hass.config_entries.async_schedule_reload(entry.entry_id)
            return self.async_abort(reason=reason)
        return self.async_update_reload_and_abort(entry, **updates, reason=reason)

    def _show_service_form(self, *, data_schema=None, **kwargs):
        """Prefill only valid choices; dependent selectors may have changed."""
        entry = getattr(self, "_reconfigure_entry", None)
        if data_schema is None:
            return self.async_show_form(data_schema=data_schema, **kwargs)
        values = deepcopy(getattr(self, "_reconfigure_values", {}))
        service = entry.data[CONF_ENTRY_TYPE] if entry is not None else None
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
            if any(
                field not in values
                for field in ("start_x", "start_y", "end_x", "end_y")
            ):
                # Older entries may only retain normalized coordinates.
                values["coord_system"] = "WCONGNAMUL"
                for point in ("start", "end"):
                    for axis in ("x", "y"):
                        if axis in values.get(f"{point}_coords", {}):
                            values[f"{point}_{axis}"] = values[f"{point}_coords"][axis]
            for field in ("start_x", "start_y", "end_x", "end_y"):
                if field in values:
                    values[field] = str(values[field])
        elif service == "school":
            if "grade_classes" not in values and "grade" in values:
                values["grade_classes"] = [
                    f"{values['grade']}-{class_number}"
                    for class_number in values.get(
                        "classes", [values.get("class", "1")]
                    )
                ]
            values["school_search"] = values.get("school_name", "")
        elif service == "safety_alert":
            values["sido_code"] = values.get("sido_code") or values.get("area_code", "")
            values["sgg_name"] = values.get("area_name2", "")
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
        submitted = getattr(self, "_service_inputs", {}).get(step)
        if submitted is not None:
            values.update(submitted)
            for marker in data_schema.schema:
                if isinstance(marker, vol.Optional) and marker.schema not in submitted:
                    values.pop(marker.schema, None)
        # Identical region names may exist in different provinces: do not reuse
        # a dependent selection after its parent region changes.
        if entry is not None and submitted is None:
            selected_sido = (
                getattr(self, "_air_sido", None)
                if service == "airkorea"
                else getattr(self, "_kma_sido", None)
            )
            if step in {
                "airkorea_select",
                "kma_weather_sgg",
            } and selected_sido != self._reconfigure_values.get("sido"):
                for key in ("stations", "regions", "air_station"):
                    values.pop(key, None)
            if service == "safety_alert":
                if self._safety_alert_data.get("sido_code") != values.get("sido_code"):
                    for key in ("sgg_code", "sgg_name", "emd_code", "emd_name"):
                        values.pop(key, None)
                elif self._safety_alert_data.get("sgg_code") != values.get("sgg_code"):
                    values.pop("emd_code", None)
                    values.pop("emd_name", None)
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
