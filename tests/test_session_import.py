"""Credentials and account-validation boundaries, with no Google requests."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).parents[1]
BASE = ROOT / 'custom_components/google_fi_data'
pkg = types.ModuleType('fi_import_test')
pkg.__path__ = [str(BASE)]
sys.modules['fi_import_test'] = pkg
from fi_import_test import session_import as subject

spec = importlib.util.spec_from_file_location('har_import', ROOT / 'tools/import_session.py')
har_import = importlib.util.module_from_spec(spec)
spec.loader.exec_module(har_import)


def seed():
    return {'user_agent': 'Synthetic browser', 'control_context': [1],
            'cookies': [{'name': 'SID', 'value': 'NOT_A_REAL_CREDENTIAL', 'domain': '.google.com'}]}


def har():
    from urllib.parse import urlencode
    call = [[['aU43Ic', json.dumps([[1], None, ['irrelevant captured mutation']]), None, 'generic']]]
    return {'log': {'entries': [{'request': {
        'url': 'https://fi.google.com/_/data/batchexecute?rpcids=aU43Ic',
        'headers': [{'name': 'Cookie', 'value': 'SID=NOT_A_REAL_CREDENTIAL; unrelated=discard'},
                    {'name': 'User-Agent', 'value': 'Synthetic browser'}],
        'postData': {'text': urlencode({'f.req': json.dumps(call)})}}}]}}


class ImportTests(unittest.TestCase):
    def test_cookie_only_helper_code_is_accepted_without_pause_context(self):
        raw = seed()
        del raw['control_context']
        result = subject.normalize_session(json.dumps(raw))
        self.assertIsNone(result['control_context'])
        self.assertEqual(len(result['cookies']), 1)

    def test_normalization_drops_unrelated_domains_cookies_and_extra_fields(self):
        raw = seed()
        raw['opaque_resume_action'] = 'do not retain'
        raw['cookies'] += [{'name': 'SID', 'value': 'other', 'domain': '.attacker.invalid'},
                           {'name': 'analytics', 'value': 'other', 'domain': '.google.com'}]
        result = subject.normalize_session(json.dumps(raw))
        self.assertEqual(len(result['cookies']), 1)
        self.assertNotIn('opaque_resume_action', result)
        self.assertTrue(result['cookies'][0]['secure'])

    def test_invalid_input_never_echoes_credentials(self):
        for raw in ['SECRET', '{}', '[]', json.dumps({**seed(), 'control_context': 'bad'}),
                    json.dumps({**seed(), 'cookies': [{'name': 'SID', 'value': 'SECRET', 'domain': 'bad'}]}),
                    json.dumps({**seed(), 'user_agent': 'SECRET\r\ninjection'})]:
            with self.assertRaisesRegex(subject.FiError, '^invalid_session$'):
                subject.normalize_session(raw)

    def test_owner_only_atomic_save(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'active.json'
            subject.save_session(path, seed())
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(path.read_text()), seed())
            self.assertEqual([p.name for p in path.parent.iterdir()], ['active.json'])

    def test_candidate_is_not_active_and_mismatch_never_replaces_active_session(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'active.json'
            path.write_text('ORIGINAL')
            class FakeClient:
                def __init__(self, candidate):
                    self.candidate = candidate
                    assert candidate != path
                    assert os.stat(candidate).st_mode & 0o777 == 0o600
                def poll(self, force, *, rotate_cookies=True):
                    assert rotate_cookies is False
                    return {'lines': {'456': {'name': 'Another line', 'enabled': True}}}
            with patch.object(subject, 'FiClient', FakeClient):
                with self.assertRaisesRegex(subject.FiError, '^account_mismatch$'):
                    subject.validate_session(path, seed(), ('123',))
            self.assertEqual(path.read_text(), 'ORIGINAL')
            self.assertEqual([p.name for p in path.parent.iterdir()], ['active.json'])

    def test_successful_validation_still_requires_separate_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'active.json'
            path.write_text('ORIGINAL')
            class FakeClient:
                def __init__(self, candidate): pass
                def poll(self, force, *, rotate_cookies=True):
                    assert rotate_cookies is False
                    return {'lines': {'123': {'name': 'A line', 'enabled': True}}}
            with patch.object(subject, 'FiClient', FakeClient):
                candidate, lines = subject.validate_session(path, seed(), ('123',))
            self.assertIn('123', lines)
            self.assertEqual(path.read_text(), 'ORIGINAL')
            subject.save_session(path, candidate)
            self.assertEqual(json.loads(path.read_text()), seed())

    def test_har_extracts_context_but_never_captured_actions_or_responses(self):
        source = har()
        source['log']['entries'][0]['response'] = {'content': {'text': 'private account data'}}
        result = har_import.from_har(source)
        self.assertNotIn('control_context', result)
        self.assertEqual(len(result['cookies']), 1)
        self.assertNotIn('irrelevant', json.dumps(result))
        self.assertNotIn('private account data', json.dumps(result))
        subject.normalize_session(json.dumps(result))

    def test_sanitized_har_is_rejected_but_no_pause_capture_is_needed(self):
        source = har()
        source['log']['entries'][0]['request']['headers'] = []
        with self.assertRaises(ValueError): har_import.from_har(source)
        source = har()
        source['log']['entries'][0]['request']['postData'] = {}
        self.assertNotIn('control_context', har_import.from_har(source))

    def test_other_hosts_cannot_supply_cookies_or_context(self):
        source = har()
        source['log']['entries'][0]['request']['url'] = 'https://fi.google.com.attacker.invalid/_/data/batchexecute'
        with self.assertRaises(ValueError): har_import.from_har(source)

    def test_cli_never_overwrites_existing_output_or_leaks_capture(self):
        import subprocess
        with tempfile.TemporaryDirectory() as directory:
            src, dst = Path(directory)/'input.har', Path(directory)/'output.json'
            src.write_text(json.dumps(har()))
            args = [sys.executable, str(ROOT/'tools/import_session.py'), str(src), '--output', str(dst)]
            run = subprocess.run(args, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertNotIn('NOT_A_REAL_CREDENTIAL', run.stdout + run.stderr)
            self.assertEqual(os.stat(dst).st_mode & 0o777, 0o600)
            original = dst.read_bytes()
            run = subprocess.run(args, capture_output=True, text=True)
            self.assertEqual(run.returncode, 1)
            self.assertEqual(dst.read_bytes(), original)
            self.assertNotIn('NOT_A_REAL_CREDENTIAL', run.stdout + run.stderr)


if __name__ == '__main__': unittest.main()
