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
    CONF_GRID_POWER, CONF_PV_POWER, CONF_BATTERY_POWER, CONF_BATTERY_SOC,
    CONF_SWITCHES, DEFAULT_API_URL, DEFAULT_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL, MAX_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


def _get_sensor_options(hass, filter_units=None):
    """Build entity dict for dropdowns. filter_units: set of units to include, or None for all."""
    options = {"": "-- Nicht zugewiesen --"}
    for s in sorted(hass.states.async_all(), key=lambda x: x.attributes.get("friendly_name", x.entity_id)):
        if s.entity_id.split(".")[0] != "sensor":
            continue
        if s.state in ("unavailable",):
            continue
        name = s.attributes.get("friendly_name", s.entity_id)
        unit = s.attributes.get("unit_of_measurement", "")
        if filter_units and unit.lower() not in filter_units:
            continue
        options[s.entity_id] = f"{name} [{unit}]" if unit else name
    return options


def _get_switch_options(hass):
    """Build switch entity dict for multi-select."""
    options = {}
    for s in sorted(hass.states.async_all(), key=lambda x: x.attributes.get("friendly_name", x.entity_id)):
        domain = s.entity_id.split(".")[0]
        if domain not in ("switch", "input_boolean"):
            continue
        name = s.attributes.get("friendly_name", s.entity_id)
        options[s.entity_id] = name
    return options


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
        """Step 1: Pairing code."""
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
        return EnergyHubOptionsFlow()


class EnergyHubOptionsFlow(config_entries.OptionsFlow):
    """Guided setup: assign entities to energy roles."""

    async def async_step_init(self, user_input=None):
        """Step 1: Grid + PV sensors."""
        if user_input is not None:
            self._data = user_input
            return await self.async_step_battery()

        entry = self.config_entry
        all_sensors = _get_sensor_options(self.hass)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional(
                    CONF_GRID_POWER,
                    default=entry.options.get(CONF_GRID_POWER, ""),
                ): vol.In(all_sensors),
                vol.Optional(
                    CONF_PV_POWER,
                    default=entry.options.get(CONF_PV_POWER, ""),
                ): vol.In(all_sensors),
            }),
        )

    async def async_step_battery(self, user_input=None):
        """Step 2: Battery sensors."""
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_switches()

        entry = self.config_entry
        all_sensors = _get_sensor_options(self.hass)

        return self.async_show_form(
            step_id="battery",
            data_schema=vol.Schema({
                vol.Optional(
                    CONF_BATTERY_POWER,
                    default=entry.options.get(CONF_BATTERY_POWER, ""),
                ): vol.In(all_sensors),
                vol.Optional(
                    CONF_BATTERY_SOC,
                    default=entry.options.get(CONF_BATTERY_SOC, ""),
                ): vol.In(all_sensors),
            }),
        )

    async def async_step_switches(self, user_input=None):
        """Step 3: Switches + interval."""
        if user_input is not None:
            self._data.update(user_input)
            return self.async_create_entry(title="", data=self._data)

        entry = self.config_entry
        switch_options = _get_switch_options(self.hass)
        current_interval = entry.options.get(
            CONF_SCAN_INTERVAL,
            entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        )
        current_switches = entry.options.get(CONF_SWITCHES, [])

        schema_fields = {
            vol.Required(CONF_SCAN_INTERVAL, default=current_interval): int,
        }
        if switch_options:
            schema_fields[vol.Optional(CONF_SWITCHES, default=current_switches)] = cv.multi_select(switch_options)

        return self.async_show_form(
            step_id="switches",
            data_schema=vol.Schema(schema_fields),
        )
