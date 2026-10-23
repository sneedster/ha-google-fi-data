"""Real HA options/flow types with synthetic accounts; no live mutations."""
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from custom_components.google_fi_data.config_flow import GoogleFiConfigFlow, GoogleFiOptionsFlow
from custom_components.google_fi_data.const import entity_uid, scoped_key, session_file, selected_lines


def entry(key=None, entry_id='one', lines=None):
    data = {'lines': lines or {'123': 'First line'}, 'notify_service': ''}
    if key:
        data.update(account_key=key, account_line_ids=list(data['lines']),
                    session_file=f'.storage/google_fi_data.{key}.session.json')
    return SimpleNamespace(entry_id=entry_id, data=data, options={}, title='Google Fi')


class AccountTests(unittest.IsolatedAsyncioTestCase):
    async def test_duplicate_account_with_different_selected_subset_is_rejected(self):
        existing = entry(lines={'123': 'Selected'})
        flow = GoogleFiConfigFlow()
        flow.context, flow.handler, flow.flow_id = {'source':'user'}, 'google_fi_data', 'synthetic'
        flow._async_current_entries = Mock(return_value=[existing])
        flow._validate = AsyncMock(return_value=({}, {'123': {'name':'Selected'}, '456': {'name':'Other'}}))
        result = await flow.async_step_user({'session_json':'synthetic'})
        self.assertEqual(result['reason'], 'account_already_configured')

    async def test_two_accounts_have_distinct_sessions_and_entity_notification_state_ids(self):
        first, second, legacy = entry('aaa'), entry('bbb','two'), entry()
        self.assertNotEqual(session_file(first), session_file(second))
        for base in ['google_fi_data_access','google_fi_data_last_known']:
            self.assertNotEqual(scoped_key(first,base), scoped_key(second,base))
            self.assertEqual(scoped_key(legacy,base), base)
        self.assertNotEqual(entity_uid(first,'authentication'), entity_uid(second,'authentication'))
        self.assertEqual(entity_uid(legacy,'123_data'), 'google_fi_data_123_data')
        self.assertEqual(session_file(legacy), '.storage/google_fi_data.session.json')

    async def test_options_add_remove_all_lines_without_control_writes(self):
        existing = entry()
        flow = GoogleFiOptionsFlow()
        flow.handler, flow.flow_id = 'one', 'synthetic'
        async def executor(fn,*args): return fn(*args)
        flow.hass = SimpleNamespace(config=SimpleNamespace(path=lambda p:p),
            config_entries=SimpleNamespace(async_get_known_entry=lambda _:existing),
            services=SimpleNamespace(async_services=lambda:{'notify':{}}),
            async_add_executor_job=executor)
        with patch('custom_components.google_fi_data.config_flow.FiClient') as Client:
            Client.return_value.poll.return_value = {'lines': {'123':{'name':'First line'},'456':{'name':'New line'}}}
            shown = await flow.async_step_init()
            key = next(k for k in shown['data_schema'].schema if str(k)=='line_ids')
            self.assertEqual(key.default(), ['123'])
            changed = await flow.async_step_init({'line_ids':['456'],'notify_service':''})
            self.assertEqual(changed['data']['lines'], {'456':'New line'})
            cleared = await flow.async_step_init({'line_ids':[],'notify_service':''})
            self.assertEqual(cleared['data']['lines'], {})
            Client.return_value.set_enabled.assert_not_called()
        existing.options = changed['data']
        self.assertEqual(selected_lines(existing), {'456':'New line'})
        self.assertEqual(session_file(existing), '.storage/google_fi_data.session.json')

    async def test_setup_removes_only_deselected_switch_entities_in_own_entry(self):
        import custom_components.google_fi_data as integration
        existing = entry()
        existing.options = {'lines':{'456':'New line'}}
        existing.async_on_unload = Mock()
        existing.add_update_listener = Mock()
        entities = [SimpleNamespace(domain='switch',unique_id='google_fi_data_123_data',entity_id='switch.old'),
                    SimpleNamespace(domain='switch',unique_id='google_fi_data_456_data',entity_id='switch.new'),
                    SimpleNamespace(domain='sensor',unique_id='google_fi_data_authentication',entity_id='sensor.auth')]
        registry = SimpleNamespace(async_remove=Mock())
        hass = SimpleNamespace(data={},config_entries=SimpleNamespace(async_forward_entry_setups=AsyncMock()))
        with patch.object(integration.er,'async_get',return_value=registry), \
             patch.object(integration.er,'async_entries_for_config_entry',return_value=entities) as find, \
             patch.object(integration,'FiCoordinator') as Coordinator:
            Coordinator.return_value.async_initialize = AsyncMock()
            Coordinator.return_value.async_refresh = AsyncMock()
            await integration.async_setup_entry(hass,existing)
            find.assert_called_once_with(registry,'one')
            registry.async_remove.assert_called_once_with('switch.old')


if __name__=='__main__': unittest.main()
