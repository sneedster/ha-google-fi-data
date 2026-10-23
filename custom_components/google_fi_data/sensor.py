from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.helpers.entity import EntityCategory
from homeassistant.util import dt as dt_util

from .const import DOMAIN, entity_uid
from .entity import FiEntity


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([FiHealthSensor(coordinator), FiLastSuccessSensor(coordinator)])


class FiHealthSensor(FiEntity, SensorEntity):
    _attr_name = "Authentication"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:shield-account"

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_unique_id = entity_uid(coordinator.entry, "authentication")
        self._attr_suggested_object_id = "google_fi_authentication"

    @property
    def native_value(self):
        return self.coordinator.status

    @property
    def extra_state_attributes(self):
        return self.coordinator.health_attributes


class FiLastSuccessSensor(FiEntity, SensorEntity):
    _attr_name = "Last successful read"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_unique_id = entity_uid(coordinator.entry, "last_success")
        self._attr_suggested_object_id = "google_fi_last_successful_read"

    @property
    def native_value(self):
        return dt_util.utc_from_timestamp(self.coordinator.last_success) if self.coordinator.last_success else None
