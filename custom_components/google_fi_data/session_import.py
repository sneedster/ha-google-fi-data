"""Stage imported credentials without changing the active session or line state."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile

from .client import AUTH_COOKIES, FiClient, FiError

MAX_SESSION_BYTES = 256_000


def normalize_session(text):
    """Accept only a minimal seed; never echo credentials in errors."""
    try:
        if not isinstance(text, str) or len(text.encode()) > MAX_SESSION_BYTES:
            raise ValueError
        raw = json.loads(text)
        agent, context = raw["user_agent"], raw.get("control_context")
        if not isinstance(agent, str) or not 1 <= len(agent) <= 2048 or any(c in agent for c in "\r\n"):
            raise ValueError
        if ((context is not None and (not isinstance(context, list) or not context))
                or not isinstance(raw["cookies"], list)):
            raise ValueError
        cookies = []
        for cookie in raw["cookies"]:
            name, value, domain = cookie["name"], cookie["value"], cookie["domain"]
            if domain not in ("google.com", ".google.com", "fi.google.com", ".fi.google.com"):
                continue
            if not isinstance(name, str) or not AUTH_COOKIES.search(name):
                continue
            if not isinstance(value, str) or not value or any(c in name + value for c in "\r\n"):
                raise ValueError
            cookies.append({"name": name, "value": value, "domain": domain,
                            "secure": True, "path": "/", "expires": None})
        if not cookies:
            raise ValueError
        return {"user_agent": agent, "control_context": context, "cookies": cookies}
    except (ValueError, TypeError, KeyError, RecursionError):
        raise FiError("invalid_session") from None


def save_session(path, session):
    """Write an owner-only replacement atomically."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".fi-session-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(session, stream, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def validate_session(path, session, expected_ids=()):
    """Read the candidate in private scratch space; committing is separate.

    Only Fi bootstrap/account reads run; cookie renewal is deferred.
    No pause/resume operation is called.
    A wrong account cannot replace a working session during reauthentication.
    """
    parent = Path(path).parent
    parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".fi-import-", dir=parent) as directory:
        candidate = Path(directory) / "session.json"
        save_session(candidate, session)
        snapshot = FiClient(candidate).poll(force=True, rotate_cookies=False)
        lines = snapshot["lines"]
        if not lines:
            raise FiError("no_lines")
        if expected_ids and not set(expected_ids).intersection(lines):
            raise FiError("account_mismatch")
        return json.loads(candidate.read_text()), lines
