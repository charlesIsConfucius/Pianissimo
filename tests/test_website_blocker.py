import os
import tempfile
import unittest
import subprocess
import sys
import time
from types import SimpleNamespace

from focus_shield.core.website_blocker import WebsiteBlocker, normalize_domain, replace_managed_block, write_hosts


class WebsiteBlockerTests(unittest.TestCase):
    def test_domain_validation(self):
        self.assertEqual(normalize_domain('https://YouTube.com/watch?v=1'), 'youtube.com')
        for bad in ('localhost', '127.0.0.1', 'youtube.com\nexample.com', '*.example.com', 'bad name.com'):
            self.assertIsNone(normalize_domain(bad))

    def test_preserves_other_entries_and_removes_own(self):
        original = b'# existing\r\n127.0.0.1 example.test\r\n'
        blocked = replace_managed_block(original, ['youtube.com'])
        self.assertIn(b'0.0.0.0 youtube.com', blocked)
        self.assertIn(b'0.0.0.0 www.youtube.com', blocked)
        self.assertEqual(replace_managed_block(blocked, []), original)
        self.assertEqual(replace_managed_block(blocked, [], expected_owner=os.getpid() + 1), blocked)
        self.assertEqual(replace_managed_block(blocked, [], expected_owner=os.getpid()), original)

    def test_refuses_broken_markers(self):
        with self.assertRaises(ValueError):
            replace_managed_block(b'# BEGIN PIANISSIMO MANAGED BLOCKS\nother data\n', [])

    def test_focus_start_change_and_end(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'hosts')
            with open(path, 'wb') as f:
                f.write(b'# hosts\r\n')
            state = SimpleNamespace(active=False)
            scheduler = SimpleNamespace(is_focus_active=lambda: state.active)
            config = SimpleNamespace(data={'blocked_domains': ['reddit.com']})
            blocker = WebsiteBlocker(config, scheduler, path)
            state.active = True
            blocker.sync()
            self.assertIsNone(blocker.error)
            with open(path, 'rb') as f:
                self.assertIn(b'reddit.com', f.read())
            config.data['blocked_domains'] = ['youtube.com']
            blocker.sync()
            with open(path, 'rb') as f:
                data = f.read()
            self.assertIn(b'youtube.com', data)
            self.assertNotIn(b'reddit.com', data)
            state.active = False
            blocker.sync()
            with open(path, 'rb') as f:
                self.assertEqual(f.read(), b'# hosts\r\n')

    @unittest.skipUnless(os.name == 'nt', 'Windows process watcher')
    def test_watchdog_cleans_after_parent_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, 'hosts')
            parent = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'], creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                data = replace_managed_block(b'# hosts\r\n', ['reddit.com'])
                data = data.replace(str(os.getpid()).encode(), str(parent.pid).encode(), 1)
                with open(path, 'wb') as f:
                    f.write(data)
                code = 'import sys; from focus_shield.core.website_blocker import watch_parent; watch_parent(int(sys.argv[1]), sys.argv[2])'
                watcher = subprocess.Popen([sys.executable, '-c', code, str(parent.pid), path], creationflags=subprocess.CREATE_NO_WINDOW)
                parent.terminate()
                parent.wait(timeout=5)
                self.assertEqual(watcher.wait(timeout=10), 0)
                with open(path, 'rb') as f:
                    self.assertEqual(f.read(), b'# hosts\r\n')
            finally:
                if parent.poll() is None:
                    parent.terminate()
                    parent.wait(timeout=5)


if __name__ == '__main__':
    unittest.main()
