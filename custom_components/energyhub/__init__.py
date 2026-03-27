"""EnergyHub integration for Home Assistant.

Pushes energy sensor data to the EnergyHub cloud platform.
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
    CONF_GRID_POWER, CONF_PV_POWER, CONF_BATTERY_POWER, CONF_BATTERY_SOC,
    CONF_SWITCHES, CONF_INVERT_GRID, DEFAULT_SCAN_INTERVAL,
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


def get_all_energy_entities(hass: HomeAssistant) -> list[State]:
    """Get all energy-relevant entities."""
    return [s for s in hass.states.async_all() if is_energy_entity(s)]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up EnergyHub from a config entry."""
    api_url = entry.data[CONF_API_URL]
    webhook_key = entry.data[CONF_PAIRING_CODE]
    interval = entry.options.get(CONF_SCAN_INTERVAL,
                entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))

    # Entity role assignments from options
    grid_entity = entry.options.get(CONF_GRID_POWER, "")
    pv_entity = entry.options.get(CONF_PV_POWER, "")
    battery_entity = entry.options.get(CONF_BATTERY_POWER, "")
    battery_soc_entity = entry.options.get(CONF_BATTERY_SOC, "")
    switch_entities = entry.options.get(CONF_SWITCHES, [])
    invert_grid = entry.options.get(CONF_INVERT_GRID, False)

    # Build set of entities to push
    assigned = {e for e in [grid_entity, pv_entity, battery_entity, battery_soc_entity] if e}
    assigned.update(switch_entities)

    session = async_get_clientsession(hass)
    hass.data.setdefault(DOMAIN, {})

    # Role map: entity_id -> role name
    role_map = {}
    if grid_entity:
        role_map[grid_entity] = "grid_power"
    if pv_entity:
        role_map[pv_entity] = "pv_power"
    if battery_entity:
        role_map[battery_entity] = "battery_power"
    if battery_soc_entity:
        role_map[battery_soc_entity] = "battery_soc"
    for sw in switch_entities:
        role_map[sw] = "switch"

    async def push_energy_data(_now=None):
        """Collect assigned entities and push to EnergyHub."""
        states = []

        for state in hass.states.async_all():
            # If entities are assigned, push those + auto-detect rest
            if assigned:
                if state.entity_id not in assigned and not is_energy_entity(state):
                    continue
            else:
                # Nothing assigned yet — push all energy entities
                if not is_energy_entity(state):
                    continue

            if state.state in ("unavailable", "unknown"):
                continue

            # Invert grid power if configured
            value = state.state
            if invert_grid and state.entity_id == grid_entity:
                try:
                    value = str(-float(value))
                except (ValueError, TypeError):
                    pass

            entry_data = {
                "entity_id": state.entity_id,
                "state": value,
                "attributes": {
                    "unit_of_measurement": state.attributes.get("unit_of_measurement"),
                    "friendly_name": state.attributes.get("friendly_name"),
                    "device_class": state.attributes.get("device_class"),
                },
                "last_changed": state.last_changed.isoformat() if state.last_changed else None,
            }

            # Add role if assigned
            if state.entity_id in role_map:
                entry_data["role"] = role_map[state.entity_id]

            states.append(entry_data)

        if not states:
            return

        # Also send the role assignments as metadata
        payload = {
            "states": states,
            "roles": {
                "grid_power": grid_entity or None,
                "pv_power": pv_entity or None,
                "battery_power": battery_entity or None,
                "battery_soc": battery_soc_entity or None,
                "switches": switch_entities or [],
            },
        }

        try:
            async with session.post(
                f"{api_url}/webhook/{webhook_key}",
                json=payload,
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
        "cancel_interval": cancel_interval,
    }

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    # Initial push
    await push_energy_data()

    roles_info = []
    if grid_entity:
        roles_info.append(f"Netz={grid_entity}")
    if pv_entity:
        roles_info.append(f"PV={pv_entity}")
    if battery_entity:
        roles_info.append(f"Batterie={battery_entity}")
    _LOGGER.info("EnergyHub gestartet — %s, alle %ds", ", ".join(roles_info) or "auto-detect", interval)
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
