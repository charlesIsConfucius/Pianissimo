import http.client
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from app import APP_ACCESS_PATH, CalendarHandler
from focus_shield.core.config import ConfigManager


class TestAppAccess(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / 'shield_config.json'
        self.config = ConfigManager(str(self.path))
        self.config.data.update(
            allowed_apps=['Code.EXE'], blocked_apps=['Games.exe'], system_whitelist=['Explorer.EXE'],
        )
        self.config.save()

        class Monitor:
            config_manager = self.config

            def get_running_user_processes(self):
                return ['IDE.exe', 'ide.exe', 'Code.exe', 'Explorer.exe']

            def recent_blocked_apps(self):
                return [{'name': 'games.exe', 'time': '2026-11-20T10:00:00-06:00'}]

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), CalendarHandler)
        self.server.app_monitor = Monitor()
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': 0.05}, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, payload=None, headers=None):
        host, port = self.server.server_address
        connection = http.client.HTTPConnection(host, port, timeout=2)
        try:
            if payload is None:
                connection.request('GET', APP_ACCESS_PATH, headers=headers or {})
            else:
                if headers is None:
                    headers = {'Content-Type': 'application/json', 'Origin': f'http://{host}:{port}'}
                connection.request('POST', APP_ACCESS_PATH, json.dumps(payload), headers)
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_lists_match_enforcement_and_whitelist_changes_persist(self):
        status, model = self.request()
        self.assertEqual(status, 200)
        self.assertEqual(model['blocked'], ['games.exe', 'ide.exe'])
        self.assertEqual(model['allowed'], ['code.exe'])
        self.assertEqual(model['protected'], ['explorer.exe'])
        self.assertEqual(model['recent'][0]['name'], 'games.exe')
        self.assertFalse(self.config.is_app_allowed('IDE.exe'))

        status, model = self.request({'name': ' IDE ', 'allowed': True})
        self.assertEqual(status, 200)
        self.assertEqual(model['allowed'], ['code.exe', 'ide.exe'])
        self.assertTrue(self.config.is_app_allowed('IDE.exe'))
        self.assertTrue(ConfigManager(str(self.path)).is_app_allowed('IDE.exe'))

        status, model = self.request({'name': 'IDE.EXE', 'allowed': False})
        self.assertEqual(status, 200)
        self.assertIn('ide.exe', model['blocked'])
        self.assertFalse(ConfigManager(str(self.path)).is_app_allowed('IDE.exe'))

    def test_block_list_mode_allows_everything_not_on_the_block_list(self):
        self.config.data['mode'] = 'blacklist_only'
        self.config.save()
        self.assertIn('ide.exe', self.request()[1]['allowed'])
        self.assertTrue(self.config.is_app_allowed('ide.exe'))
        status, model = self.request({'name': 'games.exe', 'allowed': True})
        self.assertEqual(status, 200)
        self.assertNotIn('games.exe', model['blocked'])
        self.assertTrue(self.config.is_app_allowed('Games.exe'))

    def test_bad_names_protected_apps_and_failed_writes_leave_rules_intact(self):
        self.assertEqual(self.request({'name': 'C:\\Apps\\IDE.exe', 'allowed': True})[0], 400)
        self.assertEqual(self.request({'name': 'Explorer.exe', 'allowed': False})[0], 400)
        self.assertEqual(self.request({'name': 'IDE.exe', 'allowed': 'true'})[0], 400)
        with patch.object(self.config, '_write_config', side_effect=OSError('disk full')):
            self.assertEqual(self.request({'name': 'IDE.exe', 'allowed': True})[0], 500)
        self.assertFalse(self.config.is_app_allowed('IDE.exe'))
        self.assertFalse(ConfigManager(str(self.path)).is_app_allowed('IDE.exe'))

    def test_only_the_local_browser_origin_can_change_rules(self):
        payload = {'name': 'IDE.exe', 'allowed': True}
        for headers in [
            {'Content-Type': 'application/json'},
            {'Content-Type': 'application/json', 'Origin': 'https://example.com'},
        ]:
            self.assertEqual(self.request(payload, headers)[0], 403)
        self.assertEqual(self.request(headers={'Host': 'example.com'})[0], 403)
        self.assertFalse(self.config.is_app_allowed('IDE.exe'))

    def test_standalone_calendar_explains_that_the_blocker_is_offline(self):
        self.server.app_monitor = None
        status, body = self.request()
        self.assertEqual(status, 503)
        self.assertIn('desktop app', body['error'])
