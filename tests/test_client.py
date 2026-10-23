import base64
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

PATH = Path(__file__).parents[1] / "custom_components/google_fi_data/client.py"
spec = importlib.util.spec_from_file_location("fi_client", PATH)
client = importlib.util.module_from_spec(spec)
spec.loader.exec_module(client)


def varint(value):
    out = bytearray()
    while value >= 128:
        out.append((value & 127) | 128)
        value >>= 7
    return bytes(out + bytes([value]))


def msg(number, body):
    return varint(number * 8 + 2) + varint(len(body)) + body


def resume(target=123, extra=b""):
    reset = varint(8) + varint(client.INT64_MAX)
    config = msg(2, reset) + msg(3, reset) + extra
    update = b"\x09" + target.to_bytes(8, "little") + msg(18, config)
    return base64.b64encode(msg(1, msg(3, update) + msg(13, b"\x08\x01"))).decode()


def account(paused=False):
    user = [None] * 49
    user[0], user[48] = 123, "Test line"
    user[21], user[33] = ([0, 2], [0]) if paused else (None, None)
    value = [None] * 28
    value[4] = [user]
    value[27] = [resume()] if paused else []
    return value


class FakeClient(client.FiClient):
    def __init__(self, path):
        self.calls, self.paused, self.rotation_fails, self.bad_account = [], False, False, False
        super().__init__(path)

    def _request(self, path, body=None, *, account=False, headers=None):
        self.calls.append((path.split("?")[0], body, headers))
        if path.startswith("https://accounts.google.com"):
            if self.rotation_fails:
                raise client.FiError("http_503")
            return b"ok"
        if path.startswith("/account"):
            return b'<script>window.WIZ_global_data={"SNlM0e":"TEST_TOKEN","NF1pM":"TEST_PAGE","EEqW7b":"123"}</script>'
        if path.startswith("/xhr/ppBype"):
            if self.bad_account:
                return b"malformed"
            return json.dumps([[None, account_data(self.paused)]]).encode()
        if path.startswith("/_/data/batchexecute"):
            self.paused = True
            return b"ok"
        if path.startswith("/xhr/c5eExd"):
            self.paused = False
            return b"ok"
        raise AssertionError("Unexpected destination")


account_data = account


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "session.json"
        self.path.write_text(json.dumps({"user_agent": "test", "control_context": [1], "cookies": [
            {"name": "SID", "value": "TEST_NOT_A_CREDENTIAL", "domain": ".google.com",
             "secure": True, "path": "/", "expires": None}]}))

    def tearDown(self):
        self.tmp.cleanup()

    def test_verified_state_cycle(self):
        self.assertTrue(client.parse_lines(account())["123"]["enabled"])
        self.assertFalse(client.parse_lines(account(True))["123"]["enabled"])

    def test_unknown_limit_state_fails_closed(self):
        value = account(True)
        value[4][0][21] = [250000, 2]
        self.assertIsNone(client.parse_lines(value)["123"]["enabled"])

    def test_resume_action_is_target_bound(self):
        self.assertTrue(client.is_resume_action(resume(), "123"))
        self.assertFalse(client.is_resume_action(resume(), "456"))

    def test_resume_action_rejects_extra_mutation(self):
        self.assertFalse(client.is_resume_action(resume(extra=b"\x20\x01"), "123"))

    def test_resume_action_rejects_malformed_and_arbitrary_text(self):
        for text in ("hello", "=" * 80, base64.b64encode(b"bad").decode()):
            self.assertFalse(client.is_resume_action(text, "123"))

    def test_discover_fresh_resume_action_without_fixed_ui_path(self):
        self.assertEqual(client.find_resume_action([[[resume()]]], "123"), resume())
        with self.assertRaises(client.FiError):
            client.find_resume_action([resume(456)], "123")

    def test_resume_keeps_int64_precision(self):
        self.assertGreater(client.INT64_MAX, 2**53)
        self.assertTrue(client.is_resume_action(resume(), "123"))

    def test_cookie_persistence_and_fresh_process_load(self):
        first = FakeClient(self.path)
        result = first.poll()
        self.assertTrue(result["lines"]["123"]["enabled"])
        self.assertEqual(os.stat(self.path).st_mode & 0o777, 0o600)
        second = FakeClient(self.path)
        self.assertTrue(second.poll()["lines"]["123"]["enabled"])
        self.assertFalse(any(p.startswith("https://accounts.google.com") for p, _, _ in second.calls))

    def test_failed_read_does_not_overwrite_credential_file(self):
        original = self.path.read_bytes()
        instance = FakeClient(self.path)
        instance.bad_account = True
        with self.assertRaises(client.FiError):
            instance.poll()
        self.assertEqual(self.path.read_bytes(), original)

    def test_rotation_failure_remains_visible_and_is_throttled(self):
        instance = FakeClient(self.path)
        instance.rotation_fails = True
        self.assertEqual(instance.poll()["rotation_error"], "http_503")
        self.assertEqual(instance.poll()["rotation_error"], "http_503")
        self.assertEqual(sum(p.startswith("https://accounts.google.com") for p, _, _ in instance.calls), 1)

    def test_poll_never_performs_a_fi_write(self):
        instance = FakeClient(self.path)
        instance.poll()
        self.assertEqual({p for p, _, _ in instance.calls},
                         {"https://accounts.google.com/RotateCookies", "/account", "/xhr/ppBype"})

    def test_fresh_session_validation_reads_only_and_defers_renewal_across_restart(self):
        with patch.object(client.time, "time", return_value=10000):
            instance = FakeClient(self.path)
            self.assertTrue(instance.poll(force=True, rotate_cookies=False)["lines"]["123"]["enabled"])
            self.assertEqual({p for p, _, _ in instance.calls}, {"/account", "/xhr/ppBype"})
            self.assertEqual(json.loads(self.path.read_text())["rotation_not_before"], 10600)
        with patch.object(client.time, "time", return_value=10599):
            restarted = FakeClient(self.path)
            restarted.poll(force=True)
            self.assertFalse(any(p.startswith("https://accounts.google.com") for p, _, _ in restarted.calls))
        with patch.object(client.time, "time", return_value=10600):
            restarted.poll(force=True)
            self.assertEqual(sum(p.startswith("https://accounts.google.com") for p, _, _ in restarted.calls), 1)

    def test_pause_uses_verified_indefinite_payload(self):
        instance = FakeClient(self.path)
        self.assertFalse(instance.set_enabled("123", False)["lines"]["123"]["enabled"])
        writes = [(p, b) for p, b, _ in instance.calls if "batchexecute" in p]
        self.assertEqual(len(writes), 1)
        from urllib.parse import parse_qs
        call = json.loads(parse_qs(writes[0][1].decode())["f.req"][0])[0][0]
        update = json.loads(call[1])[2][0]
        self.assertEqual(call[0], "aU43Ic")
        self.assertEqual(update[0], 123)
        self.assertEqual(update[17], [None, [0], [0]])

    def test_resume_uses_validated_current_server_action(self):
        instance = FakeClient(self.path)
        instance.paused = True
        self.assertTrue(instance.set_enabled("123", True)["lines"]["123"]["enabled"])
        writes = [b for p, b, _ in instance.calls if p == "/xhr/c5eExd"]
        self.assertEqual([json.loads(b) for b in writes], [[None, None, resume()]])

    def test_already_enabled_does_not_write(self):
        instance = FakeClient(self.path)
        instance.set_enabled("123", True)
        self.assertFalse(any(p in ("/xhr/c5eExd", "/_/data/batchexecute") for p, _, _ in instance.calls))

    def test_wrong_target_cannot_write(self):
        instance = FakeClient(self.path)
        with self.assertRaises(client.FiError):
            instance.set_enabled("456", False)
        self.assertFalse(any("batchexecute" in p for p, _, _ in instance.calls))

    def test_invalid_seed_error_does_not_include_contents(self):
        self.path.write_text("DO_NOT_LEAK_CONTENT")
        with self.assertRaisesRegex(client.AuthError, "^session_import_required$"):
            FakeClient(self.path)


if __name__ == "__main__":
    unittest.main()
