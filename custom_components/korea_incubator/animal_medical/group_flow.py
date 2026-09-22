"""Select a facility when editing a flat medical service group."""

import voluptuous as vol

from .group import FacilityEntry, save_facility


class MedicalGroupFlow:
    def _get_reconfigure_entry(self):
        return (
            getattr(self, "_medical_facility_entry", None)
            or super()._get_reconfigure_entry()
        )

    def _get_reauth_entry(self):
        return (
            getattr(self, "_medical_facility_entry", None)
            or super()._get_reauth_entry()
        )

    async def async_step_reconfigure(self, user_input=None):
        entry = self._get_reconfigure_entry()
        if entry.data.get("medical_group"):
            self._medical_group_parent = entry
            return await self.async_step_medical_facility(user_input)
        return await super().async_step_reconfigure(user_input)

    async def async_step_reauth(self, entry_data):
        if entry_data.get("medical_group"):
            self._medical_group_parent = super()._get_reauth_entry()
            return await self.async_step_medical_facility()
        return await super().async_step_reauth(entry_data)

    async def async_step_medical_facility(self, user_input=None):
        parent = self._medical_group_parent
        if user_input is None:
            return facility_form(self, parent)
        key = user_input["facility"]
        if key not in parent.data["facilities"]:
            return facility_form(self, parent)
        self._medical_facility_entry = FacilityEntry(parent, key)
        if self.context.get("source") == "reauth":
            return await super().async_step_reauth(self._medical_facility_entry.data)
        return await super().async_step_reconfigure()

    def async_update_reload_and_abort(self, entry, **kwargs):
        if not isinstance(entry, FacilityEntry):
            return super().async_update_reload_and_abort(entry, **kwargs)
        data = kwargs.get("data", {**entry.data, **kwargs.get("data_updates", {})})
        save_facility(self.hass, entry, data=data, options=kwargs.get("options"))
        return self.async_abort(
            reason="reauth_successful"
            if self.context.get("source") == "reauth"
            else "reconfigure_successful"
        )


def facility_form(flow, parent, step_id="medical_facility"):
    return flow.async_show_form(
        step_id=step_id,
        data_schema=vol.Schema(
            {
                vol.Required("facility"): vol.In(
                    {
                        key: member["data"]["business_name"]
                        for key, member in parent.data["facilities"].items()
                    }
                )
            }
        ),
    )
