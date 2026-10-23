"""Exercise auth-failure behavior with HA boundaries stubbed, never real lines."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, Mock
from datetime import datetime, timezone

BASE = Path(__file__).parents[1] / "custom_components/google_fi_data"


def module(name):
    value = types.ModuleType(name)
    sys.modules[name] = value
    return value


package = module("google_fi_data")
package.__path__ = [str(BASE)]
ha = module("homeassistant")
components = module("homeassistant.components")
notifications = module("homeassistant.components.persistent_notification")
notifications.async_create = Mock()
notifications.async_dismiss = Mock()
components.persistent_notification = notifications
module("homeassistant.helpers")
storage = module("homeassistant.helpers.storage")
storage.Store = Mock(return_value=types.SimpleNamespace(async_save=AsyncMock(), async_load=AsyncMock(return_value={})))
updates = module("homeassistant.helpers.update_coordinator")


class FakeCoordinator:
    def __init__(self, hass, *args, **kwargs):
        self.hass = hass

    def async_set_updated_data(self, data):
        self.data = data


updates.DataUpdateCoordinator = FakeCoordinator
util = module("homeassistant.util")
util.dt = types.SimpleNamespace(utc_from_timestamp=lambda n: datetime.fromtimestamp(n, timezone.utc))

from google_fi_data.coordinator import FiCoordinator
from google_fi_data.client import AuthError, FiError


class AlertTests(unittest.IsolatedAsyncioTestCase):
    def make(self):
        hass = types.SimpleNamespace(services=types.SimpleNamespace(has_service=lambda *a: True, async_call=AsyncMock()),
                                     config=types.SimpleNamespace(path=lambda p: p),
                                     async_add_executor_job=AsyncMock())
        entry = types.SimpleNamespace(data={"lines": {"123": "Test child"}, "notify_service": "test_phone"},
                                      options={}, async_start_reauth=Mock())
        c = FiCoordinator(hass, entry)
        c.last_known = {"123": {"name": "Test child", "enabled": False}}
        notifications.async_create.reset_mock()
        notifications.async_dismiss.reset_mock()
        return c, hass, entry

    async def test_auth_failure_preserves_paused_knowledge_and_alerts(self):
        c, hass, entry = self.make()
        c.client = object()
        hass.async_add_executor_job.side_effect = AuthError("session_rejected")
        # Use a real minimal mock with a poll method to reach the auth boundary.
        c.client = types.SimpleNamespace(poll=Mock())
        await c._async_update_data()
        self.assertEqual(c.status, "authentication_failed")
        self.assertFalse(c.data_available)
        self.assertFalse(c.last_known["123"]["enabled"])
        message = notifications.async_create.call_args.args[1]
        self.assertIn("Last verified as PAUSED when this problem began: Test child", message)
        self.assertIn("https://fi.google.com/account", message)
        self.assertIn("No automatic resume", message)
        entry.async_start_reauth.assert_called_once()

    async def test_repeated_failure_does_not_spam_phone(self):
        c, hass, _ = self.make()
        await c._alert("session_rejected")
        await c._alert("session_rejected")
        self.assertEqual(hass.services.async_call.await_count, 1)
        self.assertEqual(notifications.async_create.call_count, 1)

    async def test_successful_recovery_clears_quietly_and_saves_verified_state(self):
        c, hass, _ = self.make()
        await c._alert("session_rejected")
        await c._accept({"lines": {"123": {"name": "Test child", "enabled": True}},
                         "last_rotation": 100, "rotation_count": 1, "rotation_error": None})
        self.assertEqual(c.status, "healthy")
        self.assertTrue(c.data_available)
        notifications.async_dismiss.assert_called_once()
        self.assertTrue(c.last_known["123"]["enabled"])
        self.assertEqual(hass.services.async_call.await_count, 1)
        self.assertFalse(c._alerted)

    async def test_dismissal_is_not_undone_by_polling_or_line_state_changes(self):
        c, hass, _ = self.make()
        await c._alert("http_429")
        # A dismissed notification is absent from HA; the component must not
        # recreate it when the same issue persists and line knowledge changes.
        notifications.async_create.reset_mock()
        c.last_known["123"]["enabled"] = True
        for _ in range(5):
            await c._alert("http_429")
        notifications.async_create.assert_not_called()
        self.assertEqual(hass.services.async_call.await_count, 1)

    async def test_problem_notification_deduplication_survives_restart(self):
        c, hass, _ = self.make()
        c.state_store.async_load = AsyncMock(return_value={
            "lines": c.last_known, "last_success": 100, "problem_notified": True})
        await c.async_initialize()
        await c._alert("http_429")
        notifications.async_create.assert_not_called()
        hass.services.async_call.assert_not_awaited()

    async def test_new_problem_after_recovery_notifies_once_again(self):
        c, hass, _ = self.make()
        await c._alert("http_429")
        await c._accept({"lines": {"123": {"name": "Test child", "enabled": True}},
                         "last_rotation": 100, "rotation_count": 1, "rotation_error": None})
        await c._alert("session_rejected")
        await c._alert("session_rejected")
        self.assertEqual(hass.services.async_call.await_count, 2)
        self.assertEqual(notifications.async_create.call_count, 2)

    async def test_mismatched_account_cannot_replace_last_known_state(self):
        c, _, _ = self.make()
        with self.assertRaises(AuthError):
            await c._accept({"lines": {"456": {"name": "Other account", "enabled": True}}})
        self.assertFalse(c.last_known["123"]["enabled"])

    async def test_unknown_format_keeps_last_verified_paused_state(self):
        c, _, _ = self.make()
        await c._accept({"lines": {"123": {"name": "Test child", "enabled": None}},
                         "last_rotation": 100, "rotation_count": 0, "rotation_error": None})
        self.assertEqual(c.status, "unknown_status")
        self.assertFalse(c.data_available)
        self.assertFalse(c.last_known["123"]["enabled"])
        self.assertIn("PAUSED when this problem began: Test child", notifications.async_create.call_args.args[1])

    async def test_unknown_pause_outcome_warns_even_if_last_read_was_enabled(self):
        c, _, _ = self.make()
        c.last_known["123"]["enabled"] = True
        c.pending_action = {"identity": "123", "name": "Test child", "enabled": False}
        await c._alert("control_outcome_unknown")
        self.assertIn("tried to PAUSE Test child", notifications.async_create.call_args.args[1])

    async def test_paused_state_and_pending_request_survive_coordinator_restart(self):
        c, hass, _ = self.make()
        c.last_known = {}
        c.state_store.async_load = AsyncMock(return_value={
            "lines": {"123": {"name": "Test child", "enabled": False}},
            "last_success": 100, "pending_action": {"identity": "123", "name": "Test child", "enabled": False}})
        await c.async_initialize()
        c.client = types.SimpleNamespace(poll=Mock())
        hass.async_add_executor_job.side_effect = AuthError("session_rejected")
        await c._async_update_data()
        self.assertEqual(c.health_attributes["last_known_paused_lines"], ["Test child"])
        self.assertIsNotNone(c.pending_action)

    async def test_uncertain_write_is_resolved_by_read_without_repeating_write(self):
        c, hass, _ = self.make()
        c.last_known["123"]["enabled"] = True
        c.client = types.SimpleNamespace(set_enabled=Mock(), poll=Mock())
        snapshot = {"lines": {"123": {"name": "Test child", "enabled": False}},
                    "last_rotation": 100, "rotation_count": 0, "rotation_error": None}
        hass.async_add_executor_job.side_effect = [FiError("connection_failed"), snapshot]
        await c.async_set_enabled("123", False)
        calls = hass.async_add_executor_job.call_args_list
        self.assertEqual([a.args[0] for a in calls], [c.client.set_enabled, c.client.poll])
        self.assertIsNone(c.pending_action)

    async def test_unknown_write_outcome_is_persisted_and_alerted(self):
        c, hass, _ = self.make()
        c.last_known["123"]["enabled"] = True
        c.client = types.SimpleNamespace(set_enabled=Mock(), poll=Mock())
        hass.async_add_executor_job.side_effect = [FiError("connection_failed"), AuthError("session_rejected")]
        with self.assertRaises(FiError):
            await c.async_set_enabled("123", False)
        self.assertFalse(c.pending_action["enabled"])
        self.assertFalse(c.data_available)
        self.assertIn("tried to PAUSE Test child", notifications.async_create.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
