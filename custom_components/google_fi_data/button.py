from homeassistant.components import persistent_notification
from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.entity import EntityCategory
from .const import DOMAIN, entity_uid
from .entity import FiEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([FiTestAlertButton(hass.data[DOMAIN][entry.entry_id])])


class FiTestAlertButton(FiEntity, ButtonEntity):
    _attr_name = "Test alerts"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:bell-check"

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_unique_id = entity_uid(coordinator.entry, "test_alerts")

    async def async_press(self):
        message = ("TEST: Google Fi alert delivery is working. In a real access failure, "
                   "the alert identifies lines last verified as paused and links to Fi for manual recovery. "
                   "This test does not change authentication or any phone line.")
        persistent_notification.async_create(self.hass, message, title="Google Fi alert test",
                                             notification_id=self.coordinator.notification_id + "_test")
        await self.coordinator._push("Google Fi alert test", message)
