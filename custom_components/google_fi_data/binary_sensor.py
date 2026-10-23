from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
from homeassistant.helpers.entity import EntityCategory
from .const import DOMAIN, entity_uid
from .entity import FiEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([FiProblemSensor(hass.data[DOMAIN][entry.entry_id])])


class FiProblemSensor(FiEntity, BinarySensorEntity):
    _attr_name = "Access problem"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_unique_id = entity_uid(coordinator.entry, "access_problem")

    @property
    def is_on(self):
        return self.coordinator.status != "healthy"

    @property
    def extra_state_attributes(self):
        return self.coordinator.health_attributes
