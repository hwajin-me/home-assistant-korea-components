import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD
from homeassistant.core import callback

from .const import DOMAIN, LOGGER
from .kepco.api import KepcoApiClient
from .kepco.exceptions import KepcoAuthError


class KoreaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        return self.async_show_menu(
            step_id="user",
            menu_options=["kepco"],
        )

    async def async_step_kepco(self, user_input=None):
        errors = {}

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

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return KoreaOptionsFlow(config_entry)


class KoreaOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if self.config_entry.data.get("service") == "kepco":
            return self.async_abort(reason="no_options_kepco")
        return self.async_abort(reason="no_options")
