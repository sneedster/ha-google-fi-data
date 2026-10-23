"""Run the native flow/schema against real HA, with Google and storage mocked."""
import asyncio
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from custom_components.google_fi_data.config_flow import GoogleFiConfigFlow
from custom_components.google_fi_data.client import FiError


class FlowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.flow = GoogleFiConfigFlow()
        self.flow.context = {'source': 'user'}
        self.flow.handler = 'google_fi_data'
        self.flow.flow_id = 'synthetic'
        async def executor(fn, *args): return fn(*args)
        self.flow.hass = SimpleNamespace(config=SimpleNamespace(path=lambda p: self.tmp.name+'/'+p),
            async_add_executor_job=executor,
            services=SimpleNamespace(async_services=lambda: {'notify': {'mobile_app_example': {}}}))
        self.flow.async_set_unique_id = AsyncMock()
        self.flow._abort_if_unique_id_configured = Mock()
        self.flow._async_current_entries = Mock(return_value=[])

    def tearDown(self): self.tmp.cleanup()

    async def test_masked_native_input_and_fixed_error_do_not_echo_secret(self):
        form = await self.flow.async_step_user()
        schema = form['data_schema']
        key = next(k for k in schema.schema if str(k) == "session_json")
        self.assertEqual(str(key), 'session_json')
        self.assertEqual(schema.schema[key].config['type'], 'password')
        result = await self.flow.async_step_user({'session_json': 'FAKE_SECRET_DO_NOT_ECHO'})
        self.assertEqual(result['errors'], {'base': 'invalid_session'})
        self.assertNotIn('FAKE_SECRET', str(result))

    async def test_lines_are_unselected_and_session_commits_only_on_confirmation(self):
        seed = {'cookies': ['FAKE_SECRET'], 'user_agent': 'synthetic'}
        self.flow._validate = AsyncMock(return_value=(seed, {'123': {'name': 'First line'}, '456': {'name': 'Second line'}}))
        with patch('custom_components.google_fi_data.config_flow.save_session') as save:
            form = await self.flow.async_step_user({'session_json': 'fake'})
            self.assertEqual(form['step_id'], 'lines')
            save.assert_not_called()
            key = next(k for k in form['data_schema'].schema if str(k) == 'line_ids')
            self.assertEqual(key.default(), [])
            rejected = await self.flow.async_step_lines({'line_ids': ['999']})
            self.assertEqual(rejected['errors'], {'base': 'select_lines'})
            save.assert_not_called()
            result = await self.flow.async_step_lines({'line_ids': ['456'], 'notify_service': ''})
            self.assertEqual(result['type'], 'create_entry')
            self.assertEqual(result['data']['lines'], {'456': 'Second line'})
            self.assertIn('account_key', result['data'])
            self.assertIn(self.flow._account_key, result['data']['session_file'])
            self.assertNotIn('FAKE_SECRET', str(result))
            save.assert_called_once()
            self.assertIsNone(self.flow._candidate)

    async def test_wrong_account_reauthentication_keeps_active_session(self):
        entry = SimpleNamespace(data={'lines': {'123': 'First line'}}, title='Google Fi', options={})
        self.flow._get_reauth_entry = Mock(return_value=entry)
        self.flow._validate = AsyncMock(side_effect=FiError('account_mismatch'))
        with patch('custom_components.google_fi_data.config_flow.save_session') as save:
            result = await self.flow.async_step_reauth_confirm({'session_json': 'fake'})
            self.assertEqual(result['errors'], {'base': 'account_mismatch'})
            save.assert_not_called()
            self.flow._validate.assert_awaited_once_with('fake', ('123',))

    async def test_authentication_errors_are_specific_but_never_echo_unknown_details(self):
        entry = SimpleNamespace(data={'lines': {'123': 'First line'}}, title='Google Fi', options={})
        self.flow._get_reauth_entry = Mock(return_value=entry)
        for error in ('session_rejected', 'sign_in_required', 'account_identity_missing', 'http_429', 'PRIVATE_DETAIL'):
            expected = error if error != 'PRIVATE_DETAIL' else 'cannot_connect'
            self.flow._validate = AsyncMock(side_effect=FiError(error))
            with patch('custom_components.google_fi_data.config_flow.save_session') as save:
                for step in (self.flow.async_step_user, self.flow.async_step_reauth_confirm):
                    result = await step({'session_json': 'fake'})
                    self.assertEqual(result['errors'], {'base': expected})
                    self.assertNotIn('PRIVATE_DETAIL', str(result))
                save.assert_not_called()

    async def test_successful_reauthentication_saves_then_reloads(self):
        entry = SimpleNamespace(data={'lines': {'123': 'First line'}}, title='Google Fi', options={})
        self.flow._get_reauth_entry = Mock(return_value=entry)
        self.flow._validate = AsyncMock(return_value=({'cookies': ['synthetic']}, {'123': {}}))
        self.flow.async_update_reload_and_abort = Mock(return_value={'type': 'abort', 'reason': 'reauth_successful'})
        with patch('custom_components.google_fi_data.config_flow.save_session') as save:
            result = await self.flow.async_step_reauth_confirm({'session_json': 'fake'})
            self.assertEqual(result['reason'], 'reauth_successful')
            save.assert_called_once()
            self.flow.async_update_reload_and_abort.assert_called_once_with(entry, data_updates={})

    async def test_storage_failure_stays_on_lines_without_creating_entry(self):
        self.flow._candidate = {'cookies': ['synthetic']}
        self.flow._lines = {'123': {'name': 'First line'}}
        with patch('custom_components.google_fi_data.config_flow.save_session', side_effect=OSError('DO_NOT_ECHO')):
            result = await self.flow.async_step_lines({'line_ids': ['123']})
        self.assertEqual(result['step_id'], 'lines')
        self.assertEqual(result['errors'], {'base': 'storage_failed'})
        self.assertNotIn('DO_NOT_ECHO', str(result))


if __name__ == '__main__': unittest.main()
