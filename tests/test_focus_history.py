import datetime
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from focus_shield.core.focus_history import FocusHistory
from focus_shield.core.scheduler import FocusScheduler


class FocusHistoryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.directory.name, 'history.sqlite3')

    def tearDown(self):
        self.directory.cleanup()

    def test_daily_totals_include_seven_days_and_split_midnight(self):
        history = FocusHistory(self.path)
        day = datetime.date(2026, 3, 9)
        midnight = datetime.datetime.combine(day, datetime.time.min).timestamp()
        history.record_state(True, 'Writing', midnight - 2)
        history.record_state(True, 'Writing', midnight)
        history.record_state(False, '', midnight + 2)
        days = history.daily_totals(day)
        self.assertEqual(len(days), 7)
        self.assertEqual(days[0]['date'], '2026-03-03')
        self.assertEqual(days[-2], {'date': '2026-03-08', 'seconds': 2})
        self.assertEqual(days[-1], {'date': '2026-03-09', 'seconds': 2})
        history.close(midnight + 2)

    def test_crash_recovery_excludes_downtime_and_gap(self):
        history = FocusHistory(self.path)
        day = datetime.date(2026, 6, 10)
        now = datetime.datetime.combine(day, datetime.time(12)).timestamp()
        history.record_state(True, 'Focus', now - 20)
        history.record_state(True, 'Focus', now - 18)
        history._connection.close()  # Simulate a process lost without a clean shutdown.
        recovered = FocusHistory(self.path)
        recovered.record_state(True, 'Focus', now - 4)
        recovered.record_state(True, 'Focus', now - 2)
        recovered.record_state(False, '', now - 1)
        self.assertEqual(recovered.daily_totals(day)[-1]['seconds'], 5)
        statuses = recovered._connection.execute('SELECT status FROM focus_sessions ORDER BY id').fetchall()
        self.assertEqual(statuses, [('interrupted',), ('completed',)])
        recovered.close(now)

    def test_long_gap_and_clock_reversal_not_counted(self):
        history = FocusHistory(self.path)
        day = datetime.date(2026, 6, 10)
        now = datetime.datetime.combine(day, datetime.time(12)).timestamp()
        history.record_state(True, 'Focus', now - 20)
        history.record_state(True, 'Focus', now - 18)
        history.record_state(True, 'Focus', now - 5)
        history.record_state(True, 'Focus', now - 6)
        history.record_state(False, '', now - 4)
        self.assertEqual(history.daily_totals(day)[-1]['seconds'], 4)
        history.close(now)

    def test_scheduler_tracks_continuous_overlap_and_stops(self):
        import json
        now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
        blockfile = os.path.join(self.directory.name, 'blocks.json')
        block = {'name': 'Scheduled', 'start': (now - datetime.timedelta(seconds=1)).isoformat(),
                 'end': (now + datetime.timedelta(seconds=10)).isoformat()}
        with open(blockfile, 'w', encoding='utf-8') as f:
            json.dump([block], f)
        scheduler = FocusScheduler(SimpleNamespace(data={'schedules': []}), blocks_path=blockfile, history_path=self.path)
        scheduler.evaluate(now)
        scheduler.evaluate(now + datetime.timedelta(seconds=2))
        with open(blockfile, 'w', encoding='utf-8') as f:
            json.dump([], f)
        scheduler.evaluate(now + datetime.timedelta(seconds=4))
        self.assertEqual(scheduler.focus_history.daily_totals()[-1]['seconds'], 4)
        scheduler.stop()

    def test_manual_session_overlapping_schedule_counts_once(self):
        import json
        base = datetime.datetime.now().timestamp()
        day = datetime.datetime.fromtimestamp(base).date()
        blockfile = os.path.join(self.directory.name, 'blocks.json')
        block = {'name': 'Scheduled', 'start': datetime.datetime.fromtimestamp(base - 10).isoformat(),
                 'end': datetime.datetime.fromtimestamp(base + 30).isoformat()}
        with open(blockfile, 'w', encoding='utf-8') as f:
            json.dump([block], f)
        scheduler = FocusScheduler(SimpleNamespace(data={'schedules': []}), blocks_path=blockfile, history_path=self.path)
        with patch('focus_shield.core.scheduler.time.time', return_value=base):
            scheduler.evaluate(datetime.datetime.fromtimestamp(base))
            scheduler.start_manual_session(25, 'Manual')
        with patch('focus_shield.core.scheduler.time.time', return_value=base + 2):
            scheduler.stop_manual_session()
            self.assertTrue(scheduler.is_focus_active())
        with open(blockfile, 'w', encoding='utf-8') as f:
            json.dump([], f)
        with patch('focus_shield.core.scheduler.time.time', return_value=base + 4):
            scheduler.evaluate(datetime.datetime.fromtimestamp(base + 4))
            self.assertEqual(scheduler.focus_history.daily_totals(day)[-1]['seconds'], 4)
            self.assertEqual(len(scheduler.focus_history.sessions()), 1)
            scheduler.stop()


if __name__ == '__main__':
    unittest.main()
