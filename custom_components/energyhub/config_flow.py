"""Config flow for EnergyHub integration."""
import logging
import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN, CONF_PAIRING_CODE, CONF_API_URL, CONF_SCAN_INTERVAL,
    CONF_SELECTED_ENTITIES, DEFAULT_API_URL, DEFAULT_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL, MAX_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


async def validate_pairing_code(hass: HomeAssistant, api_url: str, code: str) -> dict:
    """Validate the pairing code against the EnergyHub API."""
    url = f"{api_url}/webhook/{code}"
    session = async_get_clientsession(hass)
    try:
        async with session.post(
            url,
            json={"entity_id": "_ping", "state": "connected"},
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            if resp.status == 200:
                return {"success": True}
            elif resp.status == 404:
                return {"success": False, "error": "invalid_code"}
            else:
                return {"success": False, "error": "connection_failed"}
    except Exception as err:
        _LOGGER.error("EnergyHub connection error: %s", err)
        return {"success": False, "error": "connection_failed"}


class EnergyHubConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for EnergyHub."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step — pairing code."""
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
                vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): int,
                vol.Optional(CONF_API_URL, default=DEFAULT_API_URL): str,
            }),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Options flow handler."""
        return EnergyHubOptionsFlow(config_entry)


class EnergyHubOptionsFlow(config_entries.OptionsFlow):
    """Handle EnergyHub options."""

    def __init__(self, config_entry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Step 1: Interval setting."""
        if user_input is not None:
            # Go to entity selection
            self._interval = user_input[CONF_SCAN_INTERVAL]
            return await self.async_step_entities()

        current_interval = self.config_entry.options.get(
            CONF_SCAN_INTERVAL,
            self.config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(CONF_SCAN_INTERVAL, default=current_interval): int,
            }),
        )

    async def async_step_entities(self, user_input=None):
        """Step 2: Entity selection."""
        if user_input is not None:
            selected = user_input.get(CONF_SELECTED_ENTITIES, [])
            return self.async_create_entry(
                title="",
                data={
                    CONF_SCAN_INTERVAL: self._interval,
                    CONF_SELECTED_ENTITIES: selected,
                },
            )

        current_entities = self.config_entry.options.get(CONF_SELECTED_ENTITIES, [])

        # Build multi-select from available energy entities
        try:
            from . import get_all_energy_entities
            available = get_all_energy_entities(self.hass)
            entity_dict = {}
            for s in sorted(available, key=lambda x: x.attributes.get("friendly_name", x.entity_id)):
                name = s.attributes.get("friendly_name", s.entity_id)
                unit = s.attributes.get("unit_of_measurement", "")
                label = f"{name} [{unit}]" if unit else name
                entity_dict[s.entity_id] = label
        except Exception as err:
            _LOGGER.error("Error loading entities: %s", err)
            entity_dict = {}

        if not entity_dict:
            # No entities found — skip this step, save interval only
            return self.async_create_entry(
                title="",
                data={
                    CONF_SCAN_INTERVAL: self._interval,
                    CONF_SELECTED_ENTITIES: [],
                },
            )

        return self.async_show_form(
            step_id="entities",
            data_schema=vol.Schema({
                vol.Optional(CONF_SELECTED_ENTITIES, default=current_entities): cv.multi_select(entity_dict),
            }),
        )
