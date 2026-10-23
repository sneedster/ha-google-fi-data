from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
import time

from homeassistant.components import persistent_notification
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .client import AuthError, FiClient, FiError
from .const import DOMAIN, NOTIFICATION_ID, STATE_KEY, scoped_key, selected_lines, session_file

_LOGGER = logging.getLogger(__name__)


class FiCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry):
        super().__init__(hass, _LOGGER, name="Google Fi data", update_interval=timedelta(seconds=60))
        self.entry = entry
        self.client = None
        self.action_lock = asyncio.Lock()
        self.notification_id = scoped_key(entry, NOTIFICATION_ID)
        self.state_store = Store(hass, 1, scoped_key(entry, STATE_KEY))
        self.last_known = {}
        self.pending_action = None
        self.last_success = 0.0
        self.last_rotation = 0.0
        self.successful_reads = 0
        self.rotation_count = 0
        self.status = "starting"
        self.error_code = None
        self._alerted = False
        self._reauth_started = False

    async def async_initialize(self):
        restored = await self.state_store.async_load() or {}
        self.last_known = restored.get("lines", {})
        self.last_success = restored.get("last_success", 0)
        self.pending_action = restored.get("pending_action")
        self._alerted = bool(restored.get("problem_notified", False))

    async def _save_state(self):
        await self.state_store.async_save({"lines": self.last_known, "last_success": self.last_success,
                                          "pending_action": self.pending_action,
                                          "problem_notified": self._alerted})

    def _make_client(self):
        return FiClient(self.hass.config.path(session_file(self.entry)))

    async def _push(self, title, message):
        service = self.entry.options.get("notify_service", self.entry.data.get("notify_service", ""))
        if not service or not self.hass.services.has_service("notify", service):
            return
        try:
            await self.hass.services.async_call("notify", service, {
                "title": title, "message": message,
                "data": {"tag": self.notification_id, "url": "https://fi.google.com/account"}}, blocking=True)
        except Exception:
            _LOGGER.warning("Google Fi phone notification failed; the persistent HA alert remains available")

    async def _alert(self, issue):
        # One notification per uninterrupted problem, even after dismissal/restart.
        # Polling and changing paused-line knowledge must not recreate a dismissed
        # notification or wake the phone again.
        if self._alerted:
            return
        paused = [line["name"] for identity, line in self.last_known.items()
                  if identity in selected_lines(self.entry) and line.get("enabled") is False]
        text = (f"{self.entry.title if hasattr(self.entry, 'title') else 'Google Fi'} data access needs attention ({issue}). "
                "The switches cannot currently be trusted to change cellular data. ")
        if paused:
            text += ("Last verified as PAUSED when this problem began: " + ", ".join(paused) + ". "
                     "Those lines may remain paused until you resume them in Google Fi. ")
        else:
            text += "If any line is paused, it may remain paused until you resume it in Google Fi. "
        if self.pending_action and not self.pending_action["enabled"]:
            text += (f'The last request tried to PAUSE {self.pending_action["name"]}; '
                     "its outcome could not be verified, so that line may also be paused. ")
        text += "Open https://fi.google.com/account for direct control. No automatic resume is performed."
        self._alerted = True
        try:
            await self._save_state()
        except Exception:
            _LOGGER.warning("Google Fi could not persist notification deduplication state")
        persistent_notification.async_create(self.hass, text, title="Google Fi data access problem",
                                             notification_id=self.notification_id)
        await self._push("Google Fi data access problem", text)

    async def _accept(self, snapshot):
        selected = selected_lines(self.entry)
        if not all(identity in snapshot["lines"] for identity in selected):
            raise AuthError("account_or_line_mismatch")
        now = time.time()
        unknown = any(snapshot["lines"][identity]["enabled"] is None for identity in selected)
        merged = {k: v for k, v in self.last_known.items() if k in selected}
        for identity, line in snapshot["lines"].items():
            if identity not in selected:
                continue
            if line["enabled"] is not None:
                merged[identity] = {**line, "verified_at": now}
            elif identity not in merged:
                merged[identity] = {**line, "verified_at": None}
        self.last_known = merged
        self.last_success = now
        if self.pending_action and snapshot["lines"].get(self.pending_action["identity"], {}).get("enabled") is not None:
            self.pending_action = None
        self.successful_reads += 1
        self.last_rotation = snapshot["last_rotation"]
        self.rotation_count = snapshot["rotation_count"]
        self.status = "degraded" if snapshot["rotation_error"] else "healthy"
        self.error_code = snapshot["rotation_error"]
        if unknown:
            self.status, self.error_code = "unknown_status", "line_status_format_changed"
        await self._save_state()
        if self.status != "healthy":
            await self._alert(self.error_code)
        elif self._alerted:
            persistent_notification.async_dismiss(self.hass, self.notification_id)
            self._alerted = False
            await self._save_state()

    async def _async_update_data(self):
        async with self.action_lock:
            try:
                if self.client is None:
                    self.client = await self.hass.async_add_executor_job(self._make_client)
                snapshot = await self.hass.async_add_executor_job(self.client.poll)
                await self._accept(snapshot)
            except AuthError as error:
                self.status, self.error_code = "authentication_failed", str(error)
                self.client = None
                await self._alert(self.error_code)
                if not self._reauth_started:
                    self._reauth_started = True
                    self.entry.async_start_reauth(self.hass)
            except FiError as error:
                self.status, self.error_code = "connection_failed", str(error)
                await self._alert(self.error_code)
            except Exception:
                # Suppress exception text/tracebacks; transport URLs contain secrets.
                self.status, self.error_code = "internal_error", "unexpected_client_error"
                await self._alert(self.error_code)
            return {"status": self.status, "lines": self.last_known}

    async def async_set_enabled(self, identity, enabled):
        async with self.action_lock:
            if self.client is None:
                raise FiError("authentication_required")
            self.pending_action = {"identity": identity, "enabled": enabled,
                                   "name": selected_lines(self.entry)[identity], "requested_at": time.time()}
            await self._save_state()
            try:
                result = await self.hass.async_add_executor_job(self.client.set_enabled, identity, enabled)
                await self._accept(result)
            except FiError:
                # Unknown write outcomes are resolved only by a read, never a repeat write.
                try:
                    snapshot = await self.hass.async_add_executor_job(self.client.poll, True)
                    await self._accept(snapshot)
                    if snapshot["lines"].get(identity, {}).get("enabled") == enabled:
                        self.async_set_updated_data({"status": self.status, "lines": self.last_known})
                        return
                except FiError:
                    self.status, self.error_code = "connection_failed", "control_outcome_unknown"
                    await self._alert(self.error_code)
                self.async_set_updated_data({"status": self.status, "lines": self.last_known})
                raise FiError("change_not_confirmed_check_fi") from None
            self.async_set_updated_data({"status": self.status, "lines": self.last_known})

    @property
    def data_available(self):
        return self.status in ("healthy", "degraded") and time.time() - self.last_success < 180

    @property
    def health_attributes(self):
        return {"last_success": dt_util.utc_from_timestamp(self.last_success).isoformat() if self.last_success else None,
                "last_rotation": dt_util.utc_from_timestamp(self.last_rotation).isoformat() if self.last_rotation else None,
                "successful_reads_this_start": self.successful_reads,
                "cookie_rotations_this_start": self.rotation_count,
                "error_code": self.error_code,
                "problem_notification_active": self._alerted,
                "last_known_paused_lines": [v["name"] for k, v in self.last_known.items()
                                            if k in selected_lines(self.entry) and v.get("enabled") is False],
                "pending_action": self.pending_action,
                "push_notification_available": bool(self.entry.options.get("notify_service", self.entry.data.get("notify_service", ""))) and self.hass.services.has_service("notify", self.entry.options.get("notify_service", self.entry.data.get("notify_service", ""))),
                "direct_control_url": "https://fi.google.com/account"}
