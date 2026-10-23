from homeassistant.components.switch import SwitchEntity
from homeassistant.exceptions import HomeAssistantError

from .client import FiError
from .const import DOMAIN, entity_uid, selected_lines
from .entity import FiEntity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([FiDataSwitch(coordinator, identity, name) for identity, name in selected_lines(entry).items()])


class FiDataSwitch(FiEntity, SwitchEntity):
    _attr_icon = "mdi:signal-cellular-3"

    def __init__(self, coordinator, identity, name):
        super().__init__(coordinator)
        self.identity = identity
        self._attr_name = f"{name} data"
        self._attr_unique_id = entity_uid(coordinator.entry, f"{identity}_data")

    @property
    def available(self):
        return self.coordinator.data_available and self.is_on is not None

    @property
    def is_on(self):
        return self.coordinator.last_known.get(self.identity, {}).get("enabled")

    @property
    def extra_state_attributes(self):
        from homeassistant.util import dt as dt_util
        verified = self.coordinator.last_known.get(self.identity, {}).get("verified_at")
        return {"pause_duration": "indefinite", "last_verified_enabled": self.is_on,
                "last_verified_at": dt_util.utc_from_timestamp(verified).isoformat() if verified else None}

    async def _set(self, enabled):
        try:
            await self.coordinator.async_set_enabled(self.identity, enabled)
        except FiError:
            raise HomeAssistantError("Google Fi could not confirm the change. Check Fi directly before retrying.") from None

    async def async_turn_on(self, **kwargs):
        await self._set(True)

    async def async_turn_off(self, **kwargs):
        await self._set(False)
