"""Config flow for EnergyHub integration."""
import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant

from .const import DOMAIN, CONF_PAIRING_CODE, CONF_API_URL, DEFAULT_API_URL


async def validate_pairing_code(hass: HomeAssistant, api_url: str, code: str) -> dict:
    """Validate the pairing code against the EnergyHub API."""
    async with aiohttp.ClientSession() as session:
        # The pairing code IS the webhook key — test it
        async with session.post(
            f"{api_url}/webhook/{code}",
            json={"entity_id": "_ping", "state": "connected"},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                return {"success": True, "webhook_key": code}
            elif resp.status == 404:
                return {"success": False, "error": "invalid_code"}
            else:
                return {"success": False, "error": "connection_failed"}


class EnergyHubConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for EnergyHub."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step — user enters pairing code."""
        errors = {}

        if user_input is not None:
            api_url = user_input.get(CONF_API_URL, DEFAULT_API_URL).rstrip("/")
            code = user_input[CONF_PAIRING_CODE].strip()

            result = await validate_pairing_code(self.hass, api_url, code)

            if result["success"]:
                # Check not already configured
                await self.async_set_unique_id(code)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title="EnergyHub",
                    data={
                        CONF_API_URL: api_url,
                        CONF_PAIRING_CODE: code,
                    },
                )
            else:
                errors["base"] = result["error"]

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_PAIRING_CODE): str,
                vol.Optional(CONF_API_URL, default=DEFAULT_API_URL): str,
            }),
            errors=errors,
        )
