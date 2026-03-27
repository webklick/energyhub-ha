"""Config flow for EnergyHub integration."""
import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback

from .const import (
    DOMAIN, CONF_PAIRING_CODE, CONF_API_URL, CONF_SCAN_INTERVAL,
    DEFAULT_API_URL, DEFAULT_SCAN_INTERVAL, MIN_SCAN_INTERVAL, MAX_SCAN_INTERVAL,
)


async def validate_pairing_code(hass: HomeAssistant, api_url: str, code: str) -> dict:
    """Validate the pairing code against the EnergyHub API."""
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{api_url}/webhook/{code}",
            json={"entity_id": "_ping", "state": "connected"},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status == 200:
                return {"success": True}
            elif resp.status == 404:
                return {"success": False, "error": "invalid_code"}
            else:
                return {"success": False, "error": "connection_failed"}


class EnergyHubConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for EnergyHub."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            api_url = user_input.get(CONF_API_URL, DEFAULT_API_URL).rstrip("/")
            code = user_input[CONF_PAIRING_CODE].strip().upper()
            interval = user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

            result = await validate_pairing_code(self.hass, api_url, code)

            if result["success"]:
                await self.async_set_unique_id(code)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title="EnergyHub",
                    data={
                        CONF_API_URL: api_url,
                        CONF_PAIRING_CODE: code,
                        CONF_SCAN_INTERVAL: interval,
                    },
                )
            else:
                errors["base"] = result["error"]

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_PAIRING_CODE): str,
                vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
                    vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)
                ),
                vol.Optional(CONF_API_URL, default=DEFAULT_API_URL): str,
            }),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Options flow — allows changing interval after setup."""
        return EnergyHubOptionsFlow(config_entry)


class EnergyHubOptionsFlow(config_entries.OptionsFlow):
    """Handle options for EnergyHub (change interval after setup)."""

    def __init__(self, config_entry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current = self.config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional(CONF_SCAN_INTERVAL, default=current): vol.All(
                    vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)
                ),
            }),
        )
