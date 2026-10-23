from homeassistant.const import Platform

from .const import DOMAIN, entity_uid, selected_lines
from homeassistant.helpers import entity_registry as er
from .coordinator import FiCoordinator

PLATFORMS = [Platform.SWITCH, Platform.SENSOR, Platform.BINARY_SENSOR, Platform.BUTTON]


async def async_setup_entry(hass, entry):
    # Forget removed line controls; this never changes data on Google's servers.
    registry = er.async_get(hass)
    selected = {entity_uid(entry, f"{identity}_data") for identity in selected_lines(entry)}
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if entity.domain == "switch" and entity.unique_id not in selected:
            registry.async_remove(entity.entity_id)
    coordinator = FiCoordinator(hass, entry)
    await coordinator.async_initialize()
    await coordinator.async_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload))
    return True


async def async_reload(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass, entry):
    success = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if success:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return success
