"""Private Google Fi web client. No browser, password, or service-pause operation.

All methods are synchronous and run in HA's executor. Calls are serialized.
Never log transport exceptions: URLs may contain session tokens.
"""
from __future__ import annotations

import base64
import http.cookiejar
import json
import os
from pathlib import Path
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

FI = "https://fi.google.com"
INT64_MAX = 9223372036854775807
AUTH_COOKIES = re.compile(r"SID|HSID|SSID|APISID|OSID")
_SESSION_LOCKS = {}
_SESSION_LOCK_GUARD = threading.Lock()


class FiError(Exception):
    """Contains only a fixed, safe error code."""


class AuthError(FiError):
    pass


def field(value, number):
    return value[number - 1] if isinstance(value, list) and len(value) >= number else None


def build_control_context(member_id):
    """Mirror Fi's request interceptor using the signed-in page's member ID.

    Wx fields 3 and 11 are client constants; field 27 is false because this
    client does not send the browser's `wv` URL flag. IDs are uint64 strings,
    never floating point numbers. No control request is needed to obtain them.
    """
    if (not isinstance(member_id, str) or not re.fullmatch(r"[1-9][0-9]{0,19}", member_id)
            or int(member_id) > 2**64 - 1):
        raise AuthError("account_identity_missing")
    context = [None] * 27
    context[0], context[2], context[10], context[26] = member_id, 1, True, False
    return context


def decode_response(body):
    try:
        text = body.decode("utf-8")
        value = json.loads(text[5:] if text.startswith(")]}'\n") else text)
    except (ValueError, UnicodeError):
        raise FiError("invalid_response") from None
    if not isinstance(value, list) or not value:
        raise FiError("invalid_response")
    if field(value[0], 1) == "er":
        raise FiError("rpc_rejected")
    return value


def parse_lines(account):
    users = field(account, 5)
    if not isinstance(users, list):
        raise FiError("account_format_changed")
    lines = {}
    for user in users:
        identity = field(user, 1)
        if not isinstance(identity, (int, str)):
            raise FiError("line_identity_missing")
        limit, pending = field(user, 22), field(user, 34)
        # Only classify the two wire states actually verified against Fi's UI.
        if limit is None and pending is None:
            enabled = True
        elif limit == [0, 2] and pending == [0]:
            enabled = False
        else:
            enabled = None
        lines[str(identity)] = {
            "name": field(user, 49) or field(user, 5) or "Fi line",
            "enabled": enabled,
        }
    return lines


def protobuf(data):
    """Small strict decoder for validating a server-issued Resume data action."""
    pos, fields = 0, {}

    def varint():
        nonlocal pos
        value = shift = 0
        for _ in range(10):
            if pos >= len(data):
                raise ValueError("short")
            byte = data[pos]
            pos += 1
            value |= (byte & 127) << shift
            if not byte & 128:
                return value
            shift += 7
        raise ValueError("varint")

    while pos < len(data):
        key = varint()
        number, wire = key >> 3, key & 7
        if number == 0:
            raise ValueError("field")
        if wire == 0:
            value = varint()
        elif wire in (1, 5):
            length = 8 if wire == 1 else 4
            if pos + length > len(data):
                raise ValueError("short")
            value = int.from_bytes(data[pos:pos + length], "little")
            pos += length
        elif wire == 2:
            length = varint()
            if pos + length > len(data):
                raise ValueError("short")
            value = data[pos:pos + length]
            pos += length
        else:
            raise ValueError("wire")
        fields.setdefault(number, []).append(value)
    return fields


def one(fields, number):
    values = fields.get(number, [])
    if len(values) != 1:
        raise ValueError("cardinality")
    return values[0]


def is_resume_action(text, target):
    try:
        if not isinstance(text, str) or not 20 <= len(text) <= 2000:
            return False
        data = base64.b64decode(text.replace(" ", "+"), altchars=b"-_", validate=True)
        envelope = protobuf(data)
        if set(envelope) != {1}:
            return False
        request = protobuf(one(envelope, 1))
        if set(request) != {3, 13}:
            return False
        update = protobuf(one(request, 3))
        if set(update) != {1, 18} or str(one(update, 1)) != str(target):
            return False
        config = protobuf(one(update, 18))
        return set(config) == {2, 3} and all(
            protobuf(one(config, n)) == {1: [INT64_MAX]} for n in (2, 3))
    except (ValueError, TypeError, OverflowError):
        return False


def find_resume_action(account, target):
    matches = set()
    stack = [account]
    while stack:
        value = stack.pop()
        if isinstance(value, list):
            stack.extend(value)
        elif isinstance(value, str) and is_resume_action(value, target):
            matches.add(value)
    if len(matches) != 1:
        raise FiError("resume_action_unavailable")
    return matches.pop()


class Redirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        url = urllib.parse.urlsplit(newurl)
        if url.scheme != "https" or url.hostname not in {
            "fi.google.com", "accounts.google.com", "www.google.com"}:
            raise AuthError("unexpected_redirect")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class FiClient:
    def __init__(self, session_file):
        self.path = Path(session_file)
        with _SESSION_LOCK_GUARD:
            self.lock = _SESSION_LOCKS.setdefault(self.path.resolve(), threading.RLock())
        self.jar = http.cookiejar.CookieJar()
        self.token = self.page_token = None
        self.bootstrap_at = self.last_rotation = self.last_rotation_attempt = 0.0
        self.rotation_count = 0
        self.rotation_error = None
        self.user_agent = ""
        self.control_context = None
        with self.lock:
            self._load()
        self.opener = urllib.request.build_opener(
            Redirects(), urllib.request.HTTPCookieProcessor(self.jar))
        self.opener.addheaders = [("User-Agent", self.user_agent)]

    def _load(self):
        try:
            raw = json.loads(self.path.read_text())
            self.user_agent = raw["user_agent"]
            self.control_context = raw.get("control_context")
            now = time.time()
            self.last_rotation = float(raw.get("last_rotation", 0))
            self.last_rotation_attempt = float(raw.get("last_rotation_attempt", 0))
            if self.last_rotation > now + 60 or self.last_rotation_attempt > now + 60:
                self.last_rotation = self.last_rotation_attempt = 0.0
            self.rotation_error = raw.get("rotation_error")
            cookies = raw["cookies"]
            if not isinstance(cookies, list) or not cookies or not self.user_agent:
                raise ValueError()
            self.jar.clear()
            for c in cookies:
                if c["domain"].lstrip(".") not in {"google.com", "fi.google.com"}:
                    continue
                if not AUTH_COOKIES.search(c["name"]):
                    continue
                self.jar.set_cookie(http.cookiejar.Cookie(
                    version=0, name=c["name"], value=c["value"], port=None,
                    port_specified=False, domain=c["domain"],
                    domain_specified=c["domain"].startswith("."),
                    domain_initial_dot=c["domain"].startswith("."),
                    path=c.get("path", "/"), path_specified=True,
                    secure=c.get("secure", True),
                    expires=int(c["expires"]) if isinstance(c.get("expires"), (float, int)) and c["expires"] > 0 else None,
                    discard=False, comment=None, comment_url=None, rest={}, rfc2109=False))
            self._loaded_mtime = self.path.stat().st_mtime_ns
            if hasattr(self, "opener"):
                self.opener.addheaders = [("User-Agent", self.user_agent)]
        except (OSError, ValueError, KeyError, TypeError):
            raise AuthError("session_import_required") from None

    def _save(self):
        """Only called after an authenticated account read; atomic and owner-only."""
        raw = {"user_agent": self.user_agent, "control_context": self.control_context,
               "last_rotation": self.last_rotation, "last_rotation_attempt": self.last_rotation_attempt,
               "rotation_error": self.rotation_error,
               "cookies": [{"name": c.name, "value": c.value, "domain": c.domain,
                            "path": c.path, "secure": c.secure, "expires": c.expires}
                           for c in self.jar if AUTH_COOKIES.search(c.name)]}
        temporary = self.path.with_suffix(".tmp")
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w") as stream:
                json.dump(raw, stream, separators=(",", ":"))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            os.chmod(self.path, 0o600)
            self._loaded_mtime = self.path.stat().st_mtime_ns
        finally:
            temporary.unlink(missing_ok=True)

    def _request(self, path, body=None, *, account=False, headers=None):
        url = path if account else FI + path
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "https" or parsed.hostname not in {"fi.google.com", "accounts.google.com"}:
            raise FiError("destination_rejected")
        request = urllib.request.Request(url, data=body, headers=headers or {})
        try:
            try:
                response = self.opener.open(request, timeout=25)
            except urllib.error.HTTPError as error:
                response = error
            with response:
                status, final = response.status, response.geturl()
                data = response.read(4000000)
            if status in (401, 403) or urllib.parse.urlsplit(final).hostname != parsed.hostname:
                raise AuthError("session_rejected")
            if status != 200:
                raise FiError(f"http_{status}")
            return data
        except FiError:
            raise
        except (OSError, ValueError, urllib.error.URLError):
            raise FiError("connection_failed") from None

    def _bootstrap(self):
        html = self._request("/account?pli=1").decode("utf-8", "replace")
        def get(key):
            match = re.search(r'"' + key + r'"\s*:\s*("(?:\\.|[^"\\])*")', html)
            return json.loads(match.group(1)) if match else None
        token, page_token = get("SNlM0e"), get("NF1pM")
        if not token:
            raise AuthError("sign_in_required")
        context = build_control_context(get("EEqW7b"))
        self.token, self.page_token, self.control_context = token, page_token, context
        self.bootstrap_at = time.time()

    def _rotate(self):
        self._request("https://accounts.google.com/RotateCookies",
                      b'[000,"-0000000000000000000"]', account=True,
                      headers={"Content-Type": "application/json", "Origin": "https://accounts.google.com"})
        self.last_rotation = time.time()
        self.rotation_count += 1

    def _read_account(self):
        query = urllib.parse.urlencode({"pli": "1", "xtdc2": self.token, "rt": "r"})
        data = self._request("/xhr/ppBype?" + query, b"[]", headers={
            "Content-Type": "application/json", "Referer": FI + "/account"})
        account = field(decode_response(data)[0], 2)
        parse_lines(account)  # Validate before accepting or persisting the session.
        return account

    def poll(self, force=False):
        with self.lock:
            try:
                changed = self.path.stat().st_mtime_ns != self._loaded_mtime
            except OSError:
                raise AuthError("session_import_required") from None
            if changed:
                self._load()
                self.token = self.page_token = None
            if time.time() - self.last_rotation_attempt >= 600:
                self.last_rotation_attempt = time.time()
                try:
                    self._rotate()
                    self.rotation_error = None
                except FiError as error:
                    self.rotation_error = str(error)
            if force or not self.token or time.time() - self.bootstrap_at >= 600:
                self._bootstrap()
            try:
                account = self._read_account()
            except FiError:
                # Retrying this read is safe; write operations are never retried.
                self._bootstrap()
                account = self._read_account()
            self._save()
            return {"lines": parse_lines(account), "rotation_error": self.rotation_error,
                    "last_rotation": self.last_rotation,
                    "rotation_count": self.rotation_count, "account": account}

    def set_enabled(self, target, enabled):
        with self.lock:
            snapshot = self.poll(force=True)
            line = snapshot["lines"].get(str(target))
            if line is None or line["enabled"] is None:
                raise FiError("line_status_unknown")
            if line["enabled"] == enabled:
                return snapshot
            headers = {"Content-Type": "application/json", "Referer": FI + "/account", "X-Same-Domain": "1"}
            if self.page_token:
                headers["X-Fi-PageToken"] = self.page_token
            if enabled:
                # Fresh server action, validated for this target and only a data reset.
                action = find_resume_action(snapshot["account"], target)
                query = urllib.parse.urlencode({"pli": "1", "xtdc2": self.token, "rt": "r"})
                self._request("/xhr/c5eExd?" + query,
                              json.dumps([None, None, action]).encode(), headers=headers)
            else:
                if not self.control_context:
                    raise FiError("control_context_missing")
                update = [int(target)] + [None] * 16 + [[None, [0], [0]]]
                payload = [self.control_context, None, [update]]
                call = [[["aU43Ic", json.dumps(payload, separators=(",", ":")), None, "generic"]]]
                body = urllib.parse.urlencode({"f.req": json.dumps(call), "xtdc2": self.token}).encode()
                headers["Content-Type"] = "application/x-www-form-urlencoded;charset=UTF-8"
                self._request("/_/data/batchexecute?rpcids=aU43Ic&source-path=%2Faccount&rt=c", body, headers=headers)
            # No optimistic switch state and no repeat of an uncertain write.
            result = self.poll(force=True)
            if result["lines"].get(str(target), {}).get("enabled") != enabled:
                raise FiError("change_not_confirmed")
            return result
