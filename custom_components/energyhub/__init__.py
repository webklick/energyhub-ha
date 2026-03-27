"""EnergyHub integration for Home Assistant.

Pushes energy sensor data to the EnergyHub cloud platform.
Allows device control from EnergyHub dashboard.
"""
import logging
from datetime import timedelta

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    DOMAIN, CONF_PAIRING_CODE, CONF_API_URL, CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

ENERGY_DEVICE_CLASSES = {"power", "energy", "voltage", "current", "power_factor", "frequency"}
ENERGY_UNITS = {"w", "kw", "wh", "kwh", "v", "a", "va"}


def is_energy_entity(state: State) -> bool:
    """Check if an entity is energy-related."""
    domain = state.entity_id.split(".")[0]
    attrs = state.attributes

    if domain == "sensor":
        dc = attrs.get("device_class", "")
        if dc in ENERGY_DEVICE_CLASSES:
            return True
        unit = (attrs.get("unit_of_measurement") or "").lower()
        if unit in ENERGY_UNITS:
            return True

    if domain == "switch":
        return True

    return False


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up EnergyHub from a config entry."""
    api_url = entry.data[CONF_API_URL]
    webhook_key = entry.data[CONF_PAIRING_CODE]
    interval = entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

    # Options override config (allows changing interval after setup)
    if entry.options.get(CONF_SCAN_INTERVAL):
        interval = entry.options[CONF_SCAN_INTERVAL]

    session = async_get_clientsession(hass)

    hass.data.setdefault(DOMAIN, {})

    async def push_energy_data(_now=None):
        """Collect all energy entities and push to EnergyHub."""
        states = []
        for state in hass.states.async_all():
            if not is_energy_entity(state):
                continue
            if state.state in ("unavailable", "unknown"):
                continue

            states.append({
                "entity_id": state.entity_id,
                "state": state.state,
                "attributes": {
                    "unit_of_measurement": state.attributes.get("unit_of_measurement"),
                    "friendly_name": state.attributes.get("friendly_name"),
                    "device_class": state.attributes.get("device_class"),
                    "icon": state.attributes.get("icon"),
                },
                "last_changed": state.last_changed.isoformat() if state.last_changed else None,
            })

        if not states:
            return

        try:
            async with session.post(
                f"{api_url}/webhook/{webhook_key}",
                json={"states": states},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 200:
                    _LOGGER.debug("Pushed %d entities to EnergyHub", len(states))
                else:
                    _LOGGER.warning("EnergyHub push failed: HTTP %d", resp.status)
        except Exception as err:
            _LOGGER.warning("EnergyHub push error: %s", err)

    cancel_interval = async_track_time_interval(
        hass, push_energy_data, timedelta(seconds=interval)
    )

    hass.data[DOMAIN][entry.entry_id] = {
        "api_url": api_url,
        "webhook_key": webhook_key,
        "cancel_interval": cancel_interval,
    }

    # Reload when options change (interval)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    # Initial push
    await push_energy_data()

    _LOGGER.info("EnergyHub started — pushing every %ds", interval)
    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload EnergyHub config entry."""
    data = hass.data[DOMAIN].pop(entry.entry_id, {})
    cancel = data.get("cancel_interval")
    if cancel:
        cancel()
    return True
