from __future__ import annotations

import hashlib

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv, selector

from .client import FiClient, FiError
from .const import DOMAIN, SESSION_FILE, known_line_ids, selected_lines, session_file
from .session_import import normalize_session, save_session, validate_session

SESSION_ERRORS = {"invalid_session", "no_lines", "session_rejected", "sign_in_required",
                  "account_identity_missing", "http_429"}


class GoogleFiConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self):
        self._candidate = None
        self._lines = {}
        self._account_key = None
        self._title = "Google Fi"

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return GoogleFiOptionsFlow()

    async def _validate(self, text, expected=()):
        seed = normalize_session(text)
        return await self.hass.async_add_executor_job(
            validate_session, self.hass.config.path(SESSION_FILE), seed, expected)

    def _session_form(self, step, error=None):
        return self.async_show_form(
            step_id=step,
            data_schema=vol.Schema({**({vol.Optional("account_name", default="Google Fi"): str} if step == "user" else {}),
                vol.Required("session_json"): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD))}),
            errors={"base": error} if error else {},
            description_placeholders=({"setup_url": "https://github.com/sneedster/ha-google-fi-data#authentication"}
                                      if step == "user" else {"fi_url": "https://fi.google.com/account"}))

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            try:
                self._candidate, self._lines = await self._validate(user_input.get("session_json"))
            except FiError as error:
                code = str(error)
                return self._session_form("user", code if code in SESSION_ERRORS else "cannot_connect")
            except OSError:
                return self._session_form("user", "storage_failed")
            identities = set(self._lines)
            for entry in self._async_current_entries():
                if identities.intersection(known_line_ids(entry)):
                    return self.async_abort(reason="account_already_configured")
            self._account_key = hashlib.sha256("|".join(sorted(identities)).encode()).hexdigest()[:24]
            await self.async_set_unique_id("google_fi_account_" + self._account_key)
            self._abort_if_unique_id_configured()
            self._title = user_input.get("account_name", "Google Fi").strip() or "Google Fi"
            return await self.async_step_lines()
        return self._session_form("user")

    @property
    def _session_path(self):
        return f".storage/google_fi_data.{self._account_key}.session.json"

    async def async_step_lines(self, user_input=None):
        choices = {identity: str(line["name"]) for identity, line in self._lines.items()}
        services = self.hass.services.async_services().get("notify", {})
        notifiers = {"": "Home Assistant alert only"}
        notifiers.update({name: name.replace("mobile_app_", "") for name in services if name.startswith("mobile_app_")})
        errors = {}
        if user_input is not None:
            selected = user_input.get("line_ids", [])
            if selected and all(identity in choices for identity in selected):
                self._abort_if_unique_id_configured()
                try:
                    await self.hass.async_add_executor_job(
                        save_session, self.hass.config.path(self._session_path), self._candidate)
                except OSError:
                    errors["base"] = "storage_failed"
                else:
                    self._candidate = None
                    return self.async_create_entry(title=self._title, data={
                        "account_key": self._account_key, "account_line_ids": list(self._lines),
                        "session_file": self._session_path,
                        "lines": {identity: choices[identity] for identity in selected},
                        "notify_service": user_input.get("notify_service", "")})
            else:
                errors["base"] = "select_lines"
        return self.async_show_form(step_id="lines", data_schema=vol.Schema({
            vol.Required("line_ids", default=[]): cv.multi_select(choices),
            vol.Optional("notify_service", default=""): vol.In(notifiers),
        }), errors=errors)

    async def async_step_reauth(self, entry_data):
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        if user_input is not None:
            entry = self._get_reauth_entry()
            try:
                candidate, _ = await self._validate(user_input.get("session_json"), tuple(known_line_ids(entry)))
                await self.hass.async_add_executor_job(
                    save_session, self.hass.config.path(session_file(entry)), candidate)
            except FiError as error:
                code = str(error)
                return self._session_form("reauth_confirm", code if code in SESSION_ERRORS | {"account_mismatch"} else "cannot_connect")
            except OSError:
                return self._session_form("reauth_confirm", "storage_failed")
            return self.async_update_reload_and_abort(entry, data_updates={})
        return self._session_form("reauth_confirm")


class GoogleFiOptionsFlow(config_entries.OptionsFlow):
    """Change selected lines without submitting any data-control operation."""

    async def async_step_init(self, user_input=None):
        entry = self.config_entry
        try:
            def fetch():
                return FiClient(self.hass.config.path(session_file(entry))).poll(force=True)["lines"]
            lines = await self.hass.async_add_executor_job(fetch)
        except (FiError, OSError):
            return self.async_show_form(step_id="init", data_schema=vol.Schema({}),
                                        errors={"base": "reauth_required"})
        choices = {identity: str(line["name"]) for identity, line in lines.items()}
        # Keep missing selected lines visible until explicitly deselected.
        for identity, name in selected_lines(entry).items():
            choices.setdefault(identity, f"{name} (not returned by Fi)")
        services = self.hass.services.async_services().get("notify", {})
        notifiers = {"": "Home Assistant alert only"}
        notifiers.update({name: name.replace("mobile_app_", "") for name in services if name.startswith("mobile_app_")})
        old_notifier = entry.options.get("notify_service", entry.data.get("notify_service", ""))
        if old_notifier:
            notifiers.setdefault(old_notifier, old_notifier)
        errors = {}
        if user_input is not None and "line_ids" in user_input:
            selected = user_input["line_ids"]
            if all(identity in choices for identity in selected):
                return self.async_create_entry(title="", data={
                    "lines": {identity: choices[identity] for identity in selected},
                    "account_line_ids": list(set(known_line_ids(entry)).union(lines)),
                    "notify_service": user_input.get("notify_service", "")})
            errors["base"] = "select_lines"
        return self.async_show_form(step_id="init", data_schema=vol.Schema({
            vol.Required("line_ids", default=list(selected_lines(entry))): cv.multi_select(choices),
            vol.Optional("notify_service", default=old_notifier): vol.In(notifiers),
        }), errors=errors)
