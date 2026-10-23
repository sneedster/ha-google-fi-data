"""Read-only bootstrap and upgrade regressions using synthetic identifiers."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

PATH = Path(__file__).parents[1] / "custom_components/google_fi_data/client.py"
spec = importlib.util.spec_from_file_location("context_client", PATH)
client = importlib.util.module_from_spec(spec)
spec.loader.exec_module(client)


class ContextTests(unittest.TestCase):
    def test_full_uint64_context_is_exact_and_only_expected_fields_are_set(self):
        context = client.build_control_context("18446744073709551615")
        self.assertEqual(len(context), 27)
        self.assertEqual({i + 1: v for i, v in enumerate(context) if v is not None},
                         {1: "18446744073709551615", 3: 1, 11: True, 27: False})
        self.assertIn('"18446744073709551615"', json.dumps(context))

    def test_missing_or_malformed_member_is_not_replaced_with_old_context(self):
        for value in (None, "", "0", "-1", "1.5", "SECRET", "18446744073709551616", 123, True):
            with self.assertRaisesRegex(client.AuthError, "^account_identity_missing$"):
                client.build_control_context(value)

    def test_cookie_only_seed_derives_context_with_reads_and_persists_it(self):
        self.exercise(None)

    def test_upgrade_replaces_legacy_context_and_does_not_change_the_session_path(self):
        self.exercise(["LEGACY_CONTEXT_MUST_NOT_BE_USED"])

    def exercise(self, legacy):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "same-session.json"
            raw = {"user_agent": "Synthetic", "last_rotation": 1e20,
                   "cookies": [{"name": "SID", "value": "SYNTHETIC", "domain": ".google.com"}]}
            if legacy is not None:
                raw["control_context"] = legacy
            path.write_text(json.dumps(raw))
            class Reader(client.FiClient):
                def _rotate(self): pass
                def _request(self, endpoint, body=None, **kwargs):
                    if endpoint.startswith("/account"):
                        return b'{"SNlM0e":"SYNTHETIC","EEqW7b":"9007199254740993"}'
                    if endpoint.startswith("/xhr/ppBype"):
                        account = [None] * 5
                        user = [None] * 49
                        user[0], user[48] = 123, "Invented line"
                        account[4] = [user]
                        return json.dumps([[None, account]]).encode()
                    raise AssertionError("A control request must never run in bootstrap")
            reader = Reader(path)
            snapshot = reader.poll(force=True)
            self.assertTrue(snapshot["lines"]["123"]["enabled"])
            self.assertEqual(reader.path, path)
            self.assertEqual(json.loads(path.read_text())["control_context"],
                             client.build_control_context("9007199254740993"))


if __name__ == "__main__":
    unittest.main()
