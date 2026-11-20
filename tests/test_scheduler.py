"""
Unit tests for FocusScheduler integration with productivity_blocks.json.
Tests coverage includes:
- Boundary conditions (exact start, before start, before end, exact end, zero duration)
- Timezone handling (UTC 'Z', offsets, naive datetimes, cross-timezone comparisons)
- Overlaps (multiple blocks, contained blocks, adjacent blocks, overlap with recurring schedules and manual sessions)
- Edits and Deletions (block removal, file deletion, time edits, name edits, late file creation)
- Malformed data robustness (invalid JSON, empty file, non-dict blocks, invalid dates, missing fields)
"""

import os
import json
import tempfile
import unittest
import datetime
from datetime import timezone, timedelta
from typing import Dict, Any

from focus_shield.core.config import ConfigManager
from focus_shield.core.scheduler import FocusScheduler


class DummyConfigManager:
    """Mock ConfigManager for testing recurring schedules and general config."""
    def __init__(self, schedules=None):
        self.data: Dict[str, Any] = {
            "schedules": schedules if schedules is not None else []
        }


class TestFocusSchedulerProductivityBlocks(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.blocks_file = os.path.join(self.temp_dir.name, "productivity_blocks.json")
        self.config_mgr = DummyConfigManager()
        self.scheduler = FocusScheduler(self.config_mgr, blocks_path=self.blocks_file, history_path=os.path.join(self.temp_dir.name, 'history.sqlite3'))

    def tearDown(self):
        self.scheduler.stop()
        self.temp_dir.cleanup()

    def _write_blocks(self, blocks):
        with open(self.blocks_file, "w", encoding="utf-8") as f:
            json.dump(blocks, f)

    # =========================================================================
    # 1. BOUNDARY TESTS
    # =========================================================================

    def test_boundary_exact_start(self):
        """At exact start time (start <= now < end), the block must be ACTIVE."""
        start_dt = datetime.datetime(2026, 11, 20, 10, 0, 0, tzinfo=timezone.utc)
        end_dt = datetime.datetime(2026, 11, 20, 11, 0, 0, tzinfo=timezone.utc)
        self._write_blocks([{
            "id": "b1",
            "name": "Boundary Start Test",
            "start": start_dt.isoformat(),
            "end": end_dt.isoformat()
        }])

        self.scheduler.evaluate(now=start_dt)
        self.assertTrue(self.scheduler.is_focus_active())
        self.assertIn("Boundary Start Test", self.scheduler.get_status()["reason"])

    def test_boundary_just_before_start(self):
        """Immediately before start time, the block must be INACTIVE."""
        start_dt = datetime.datetime(2026, 11, 20, 10, 0, 0, tzinfo=timezone.utc)
        end_dt = datetime.datetime(2026, 11, 20, 11, 0, 0, tzinfo=timezone.utc)
        self._write_blocks([{
            "id": "b1",
            "name": "Boundary Start Test",
            "start": start_dt.isoformat(),
            "end": end_dt.isoformat()
        }])

        before_start = start_dt - timedelta(microseconds=1)
        self.scheduler.evaluate(now=before_start)
        self.assertFalse(self.scheduler.is_focus_active())
        self.assertIn("Idle", self.scheduler.get_status()["reason"])

    def test_boundary_just_before_end(self):
        """Immediately before end time, the block must still be ACTIVE."""
        start_dt = datetime.datetime(2026, 11, 20, 10, 0, 0, tzinfo=timezone.utc)
        end_dt = datetime.datetime(2026, 11, 20, 11, 0, 0, tzinfo=timezone.utc)
        self._write_blocks([{
            "id": "b1",
            "name": "Boundary End Test",
            "start": start_dt.isoformat(),
            "end": end_dt.isoformat()
        }])

        before_end = end_dt - timedelta(microseconds=1)
        self.scheduler.evaluate(now=before_end)
        self.assertTrue(self.scheduler.is_focus_active())

    def test_boundary_exact_end(self):
        """At exact end time, the session is completed and must be INACTIVE."""
        start_dt = datetime.datetime(2026, 11, 20, 10, 0, 0, tzinfo=timezone.utc)
        end_dt = datetime.datetime(2026, 11, 20, 11, 0, 0, tzinfo=timezone.utc)
        self._write_blocks([{
            "id": "b1",
            "name": "Boundary End Test",
            "start": start_dt.isoformat(),
            "end": end_dt.isoformat()
        }])

        self.scheduler.evaluate(now=end_dt)
        self.assertFalse(self.scheduler.is_focus_active())

    def test_boundary_after_end(self):
        """After end time, the block must be INACTIVE."""
        start_dt = datetime.datetime(2026, 11, 20, 10, 0, 0, tzinfo=timezone.utc)
        end_dt = datetime.datetime(2026, 11, 20, 11, 0, 0, tzinfo=timezone.utc)
        self._write_blocks([{
            "id": "b1",
            "name": "Boundary End Test",
            "start": start_dt.isoformat(),
            "end": end_dt.isoformat()
        }])

        after_end = end_dt + timedelta(seconds=1)
        self.scheduler.evaluate(now=after_end)
        self.assertFalse(self.scheduler.is_focus_active())

    def test_boundary_zero_and_inverted_duration(self):
        """Blocks with start == end or end < start must be ignored."""
        t1 = datetime.datetime(2026, 11, 20, 10, 0, 0, tzinfo=timezone.utc)
        t2 = datetime.datetime(2026, 11, 20, 9, 0, 0, tzinfo=timezone.utc)
        self._write_blocks([
            {"id": "zero", "name": "Zero Duration", "start": t1.isoformat(), "end": t1.isoformat()},
            {"id": "inverted", "name": "Inverted Duration", "start": t1.isoformat(), "end": t2.isoformat()}
        ])

        self.scheduler.evaluate(now=t1)
        self.assertFalse(self.scheduler.is_focus_active())

    # =========================================================================
    # 2. TIMEZONE TESTS
    # =========================================================================

    def test_timezone_utc_with_z(self):
        """ISO strings with 'Z' suffix evaluate correctly across aware evaluate timestamps."""
        self._write_blocks([{
            "name": "UTC Block",
            "start": "2026-11-20T14:00:00Z",
            "end": "2026-11-20T16:00:00Z"
        }])

        # Evaluated at 15:00 UTC -> within block
        now_utc = datetime.datetime(2026, 11, 20, 15, 0, 0, tzinfo=timezone.utc)
        self.scheduler.evaluate(now=now_utc)
        self.assertTrue(self.scheduler.is_focus_active())

        # Evaluated at equivalent local time with offset UTC-6 (09:00 CST == 15:00 UTC)
        cst = timezone(timedelta(hours=-6))
        now_cst = datetime.datetime(2026, 11, 20, 9, 0, 0, tzinfo=cst)
        self.scheduler.evaluate(now=now_cst)
        self.assertTrue(self.scheduler.is_focus_active())

    def test_timezone_positive_offset(self):
        """Block with positive timezone offset (e.g., Tokyo UTC+9)."""
        # 10:00 to 12:00 in UTC+9 corresponds to 01:00 to 03:00 UTC
        self._write_blocks([{
            "name": "Tokyo Session",
            "start": "2026-11-20T10:00:00+09:00",
            "end": "2026-11-20T12:00:00+09:00"
        }])

        # 02:00 UTC is inside
        now_utc = datetime.datetime(2026, 11, 20, 2, 0, 0, tzinfo=timezone.utc)
        self.scheduler.evaluate(now=now_utc)
        self.assertTrue(self.scheduler.is_focus_active())
        self.assertIn("Tokyo Session", self.scheduler.get_status()["reason"])

        # 04:00 UTC is outside
        self.scheduler.evaluate(now=datetime.datetime(2026, 11, 20, 4, 0, 0, tzinfo=timezone.utc))
        self.assertFalse(self.scheduler.is_focus_active())

    def test_timezone_negative_offset(self):
        """Block with negative timezone offset (e.g., US Pacific UTC-8)."""
        # 10:00 to 12:00 in UTC-8 corresponds to 18:00 to 20:00 UTC
        self._write_blocks([{
            "name": "Pacific Session",
            "start": "2026-11-20T10:00:00-08:00",
            "end": "2026-11-20T12:00:00-08:00"
        }])

        # 19:00 UTC is inside
        now_utc = datetime.datetime(2026, 11, 20, 19, 0, 0, tzinfo=timezone.utc)
        self.scheduler.evaluate(now=now_utc)
        self.assertTrue(self.scheduler.is_focus_active())

    def test_timezone_naive_interpreted_as_local_time(self):
        """Naive block timestamps should be interpreted as local time and matched accordingly."""
        self._write_blocks([{
            "name": "Local Naive Session",
            "start": "2026-11-20T10:00:00",
            "end": "2026-11-20T11:00:00"
        }])

        # Naive current time at 10:30 matches
        naive_now = datetime.datetime(2026, 11, 20, 10, 30, 0)
        self.scheduler.evaluate(now=naive_now)
        self.assertTrue(self.scheduler.is_focus_active())

        # Naive current time at 11:30 is outside
        self.scheduler.evaluate(now=datetime.datetime(2026, 11, 20, 11, 30, 0))
        self.assertFalse(self.scheduler.is_focus_active())

    def test_timezone_cross_comparison(self):
        """Block in UTC+2 evaluated at equivalent time in UTC-5."""
        # 15:00 UTC+2 is 13:00 UTC. 17:00 UTC+2 is 15:00 UTC.
        self._write_blocks([{
            "name": "Cross TZ Session",
            "start": "2026-11-20T15:00:00+02:00",
            "end": "2026-11-20T17:00:00+02:00"
        }])

        # In UTC-5, 08:30 is 13:30 UTC -> inside the block
        tz_minus5 = timezone(timedelta(hours=-5))
        now_tz5 = datetime.datetime(2026, 11, 20, 8, 30, 0, tzinfo=tz_minus5)
        self.scheduler.evaluate(now=now_tz5)
        self.assertTrue(self.scheduler.is_focus_active())

    # =========================================================================
    # 3. OVERLAP TESTS
    # =========================================================================

    def test_overlap_multiple_blocks_partial(self):
        """Two partially overlapping blocks: active through both and reason mentions both during overlap."""
        self._write_blocks([
            {
                "name": "Block Alpha",
                "start": "2026-11-20T10:00:00Z",
                "end": "2026-11-20T11:30:00Z"
            },
            {
                "name": "Block Beta",
                "start": "2026-11-20T11:00:00Z",
                "end": "2026-11-20T12:30:00Z"
            }
        ])

        # 10:30 UTC: Only Block Alpha
        self.scheduler.evaluate(now=datetime.datetime(2026, 11, 20, 10, 30, 0, tzinfo=timezone.utc))
        self.assertTrue(self.scheduler.is_focus_active())
        status = self.scheduler.get_status()
        self.assertIn("Block Alpha", status["reason"])
        self.assertNotIn("Block Beta", status["reason"])

        # 11:15 UTC: Overlap period! Both Alpha and Beta
        self.scheduler.evaluate(now=datetime.datetime(2026, 11, 20, 11, 15, 0, tzinfo=timezone.utc))
        self.assertTrue(self.scheduler.is_focus_active())
        status = self.scheduler.get_status()
        self.assertIn("Block Alpha", status["reason"])
        self.assertIn("Block Beta", status["reason"])

        # 12:00 UTC: Only Block Beta
        self.scheduler.evaluate(now=datetime.datetime(2026, 11, 20, 12, 0, 0, tzinfo=timezone.utc))
        self.assertTrue(self.scheduler.is_focus_active())
        status = self.scheduler.get_status()
        self.assertNotIn("Block Alpha", status["reason"])
        self.assertIn("Block Beta", status["reason"])

        # 12:31 UTC: Past both blocks
        self.scheduler.evaluate(now=datetime.datetime(2026, 11, 20, 12, 31, 0, tzinfo=timezone.utc))
        self.assertFalse(self.scheduler.is_focus_active())

    def test_overlap_contained_blocks(self):
        """A larger block containing a smaller sub-block."""
        self._write_blocks([
            {
                "name": "All Day Focus",
                "start": "2026-11-20T09:00:00Z",
                "end": "2026-11-20T17:00:00Z"
            },
            {
                "name": "Deep Sprint",
                "start": "2026-11-20T13:00:00Z",
                "end": "2026-11-20T14:30:00Z"
            }
        ])

        # During sub-block
        now_utc = datetime.datetime(2026, 11, 20, 14, 0, 0, tzinfo=timezone.utc)
        self.scheduler.evaluate(now=now_utc)
        self.assertTrue(self.scheduler.is_focus_active())
        reason = self.scheduler.get_status()["reason"]
        self.assertIn("All Day Focus", reason)
        self.assertIn("Deep Sprint", reason)

    def test_overlap_adjacent_blocks_seamless_transition(self):
        """Consecutive blocks with no gap (10:00-11:00 and 11:00-12:00) transition smoothly."""
        self._write_blocks([
            {"name": "Morning", "start": "2026-11-20T10:00:00Z", "end": "2026-11-20T11:00:00Z"},
            {"name": "Midday", "start": "2026-11-20T11:00:00Z", "end": "2026-11-20T12:00:00Z"}
        ])

        # At 10:59:59 -> Morning
        self.scheduler.evaluate(now=datetime.datetime(2026, 11, 20, 10, 59, 59, tzinfo=timezone.utc))
        self.assertTrue(self.scheduler.is_focus_active())
        self.assertIn("Morning", self.scheduler.get_status()["reason"])

        # At 11:00:00 -> Midday
        self.scheduler.evaluate(now=datetime.datetime(2026, 11, 20, 11, 0, 0, tzinfo=timezone.utc))
        self.assertTrue(self.scheduler.is_focus_active())
        self.assertIn("Midday", self.scheduler.get_status()["reason"])

    def test_overlap_with_recurring_schedule(self):
        """Dated block and recurring schedule overlapping concurrently."""
        # Recurring schedule on Friday (weekday 4) from 09:00 to 12:00
        # 2026-11-20 is a Friday
        self.config_mgr.data["schedules"] = [{
            "id": "rec1",
            "name": "Recurring Work",
            "enabled": True,
            "days": [4],
            "start_time": "09:00",
            "end_time": "12:00"
        }]

        self._write_blocks([{
            "name": "Dated Sprint",
            "start": "2026-11-20T11:00:00",
            "end": "2026-11-20T13:00:00"
        }])

        # At 09:30 local time: Recurring schedule active, dated block not yet active
        t_930 = datetime.datetime(2026, 11, 20, 9, 30, 0)
        self.scheduler.evaluate(now=t_930)
        self.assertTrue(self.scheduler.is_focus_active())
        self.assertIn("Recurring Work", self.scheduler.get_status()["reason"])
        self.assertNotIn("Dated Sprint", self.scheduler.get_status()["reason"])

        # At 11:30 local time: Both recurring schedule AND dated block active!
        t_1130 = datetime.datetime(2026, 11, 20, 11, 30, 0)
        self.scheduler.evaluate(now=t_1130)
        self.assertTrue(self.scheduler.is_focus_active())
        reason = self.scheduler.get_status()["reason"]
        self.assertIn("Dated Sprint", reason)
        self.assertIn("Recurring Work", reason)

        # At 12:30 local time: Recurring schedule ended, dated block STILL active!
        t_1230 = datetime.datetime(2026, 11, 20, 12, 30, 0)
        self.scheduler.evaluate(now=t_1230)
        self.assertTrue(self.scheduler.is_focus_active())
        reason = self.scheduler.get_status()["reason"]
        self.assertIn("Dated Sprint", reason)
        self.assertNotIn("Recurring Work", reason)

        # At 13:05 local time: Both ended -> Idle
        t_1305 = datetime.datetime(2026, 11, 20, 13, 5, 0)
        self.scheduler.evaluate(now=t_1305)
        self.assertFalse(self.scheduler.is_focus_active())

    def test_overlap_with_manual_session(self):
        """Manual session takes priority over dated block; dated block resumes when manual stops."""
        now_utc = datetime.datetime.now(timezone.utc)
        self._write_blocks([{
            "name": "Calendar Deep Work",
            "start": (now_utc - datetime.timedelta(minutes=30)).isoformat(),
            "end": (now_utc + datetime.timedelta(minutes=90)).isoformat()
        }])

        # Initially, dated block is active
        self.scheduler.evaluate(now=now_utc)
        self.assertTrue(self.scheduler.is_focus_active())
        self.assertIn("Calendar Deep Work", self.scheduler.get_status()["reason"])

        # Start manual session
        self.scheduler.start_manual_session(25, goal="Emergency Firefight")
        self.assertTrue(self.scheduler.is_focus_active())
        self.assertIn("Manual Session (Emergency Firefight)", self.scheduler.get_status()["reason"])

        # Stop manual session -> dated block immediately takes back over
        self.scheduler.stop_manual_session()
        self.assertTrue(self.scheduler.is_focus_active())
        self.assertIn("Calendar Deep Work", self.scheduler.get_status()["reason"])

    # =========================================================================
    # 4. EDITS AND DELETION TESTS
    # =========================================================================

    def test_deletion_block_removed_from_file(self):
        """Removing a block from the JSON file turns focus state to inactive on next evaluation."""
        now_utc = datetime.datetime(2026, 11, 20, 10, 30, 0, tzinfo=timezone.utc)
        self._write_blocks([{
            "id": "b1",
            "name": "To Be Deleted",
            "start": "2026-11-20T10:00:00Z",
            "end": "2026-11-20T11:00:00Z"
        }])

        self.scheduler.evaluate(now=now_utc)
        self.assertTrue(self.scheduler.is_focus_active())

        # Now simulate user deleting block from file
        self._write_blocks([])
        self.scheduler.evaluate(now=now_utc)
        self.assertFalse(self.scheduler.is_focus_active())
        self.assertIn("Idle", self.scheduler.get_status()["reason"])

    def test_deletion_file_removed_from_disk(self):
        """Deleting productivity_blocks.json completely from disk turns focus to inactive without crashing."""
        now_utc = datetime.datetime(2026, 11, 20, 10, 30, 0, tzinfo=timezone.utc)
        self._write_blocks([{
            "name": "Doomed File Block",
            "start": "2026-11-20T10:00:00Z",
            "end": "2026-11-20T11:00:00Z"
        }])

        self.scheduler.evaluate(now=now_utc)
        self.assertTrue(self.scheduler.is_focus_active())

        # Remove the file entirely
        os.remove(self.blocks_file)
        self.assertFalse(os.path.exists(self.blocks_file))

        # Re-evaluate
        self.scheduler.evaluate(now=now_utc)
        self.assertFalse(self.scheduler.is_focus_active())
        self.assertIn("Idle", self.scheduler.get_status()["reason"])

    def test_edit_block_times(self):
        """Editing start/end time of a block takes effect on next evaluation."""
        now_utc = datetime.datetime(2026, 11, 20, 10, 30, 0, tzinfo=timezone.utc)
        # Block ends at 10:20 (already ended)
        self._write_blocks([{
            "name": "Extended Task",
            "start": "2026-11-20T09:00:00Z",
            "end": "2026-11-20T10:20:00Z"
        }])

        self.scheduler.evaluate(now=now_utc)
        self.assertFalse(self.scheduler.is_focus_active())

        # User extends block to 11:00
        self._write_blocks([{
            "name": "Extended Task",
            "start": "2026-11-20T09:00:00Z",
            "end": "2026-11-20T11:00:00Z"
        }])

        self.scheduler.evaluate(now=now_utc)
        self.assertTrue(self.scheduler.is_focus_active())
        self.assertIn("Extended Task", self.scheduler.get_status()["reason"])

    def test_edit_block_name(self):
        """Editing block name updates reason and goal on next evaluation."""
        now_utc = datetime.datetime(2026, 11, 20, 10, 30, 0, tzinfo=timezone.utc)
        self._write_blocks([{
            "name": "Initial Name",
            "start": "2026-11-20T10:00:00Z",
            "end": "2026-11-20T11:00:00Z"
        }])
        self.scheduler.evaluate(now=now_utc)
        self.assertIn("Initial Name", self.scheduler.get_status()["reason"])

        # Edit name
        self._write_blocks([{
            "name": "Updated Renamed Task",
            "start": "2026-11-20T10:00:00Z",
            "end": "2026-11-20T11:00:00Z"
        }])
        self.scheduler.evaluate(now=now_utc)
        self.assertIn("Updated Renamed Task", self.scheduler.get_status()["reason"])

    def test_file_created_after_scheduler_initialized(self):
        """Scheduler initialized when file does not exist; creating file activates block seamlessly."""
        if os.path.exists(self.blocks_file):
            os.remove(self.blocks_file)

        now_utc = datetime.datetime(2026, 11, 20, 10, 30, 0, tzinfo=timezone.utc)
        self.scheduler.evaluate(now=now_utc)
        self.assertFalse(self.scheduler.is_focus_active())

        # Create file now
        self._write_blocks([{
            "name": "Late Arriving Block",
            "start": "2026-11-20T10:00:00Z",
            "end": "2026-11-20T11:00:00Z"
        }])

        self.scheduler.evaluate(now=now_utc)
        self.assertTrue(self.scheduler.is_focus_active())
        self.assertIn("Late Arriving Block", self.scheduler.get_status()["reason"])

    # =========================================================================
    # 5. MALFORMED DATA TESTS
    # =========================================================================

    def test_malformed_corrupt_json_syntax(self):
        """Corrupted JSON syntax should not crash the scheduler."""
        with open(self.blocks_file, "w", encoding="utf-8") as f:
            f.write("{ invalid json [ truncated ...")

        now_utc = datetime.datetime(2026, 11, 20, 10, 30, 0, tzinfo=timezone.utc)
        self.scheduler.evaluate(now=now_utc)
        self.assertFalse(self.scheduler.is_focus_active())

    def test_malformed_empty_file(self):
        """0-byte file should not crash the scheduler."""
        with open(self.blocks_file, "w", encoding="utf-8") as f:
            f.write("")

        now_utc = datetime.datetime(2026, 11, 20, 10, 30, 0, tzinfo=timezone.utc)
        self.scheduler.evaluate(now=now_utc)
        self.assertFalse(self.scheduler.is_focus_active())

    def test_malformed_non_list_root(self):
        """JSON roots of dict, string, integer, bool, null."""
        now_utc = datetime.datetime(2026, 11, 20, 10, 30, 0, tzinfo=timezone.utc)

        for payload in ["\"just a string\"", "42", "true", "null"]:
            with open(self.blocks_file, "w", encoding="utf-8") as f:
                f.write(payload)
            self.scheduler.evaluate(now=now_utc)
            self.assertFalse(self.scheduler.is_focus_active())

    def test_malformed_blocks_wrapper_dict_supported(self):
        """JSON root of dict with 'blocks' key is also supported."""
        now_utc = datetime.datetime(2026, 11, 20, 10, 30, 0, tzinfo=timezone.utc)
        self._write_blocks({
            "blocks": [{
                "name": "Wrapped Block",
                "start": "2026-11-20T10:00:00Z",
                "end": "2026-11-20T11:00:00Z"
            }]
        })
        self.scheduler.evaluate(now=now_utc)
        self.assertTrue(self.scheduler.is_focus_active())
        self.assertIn("Wrapped Block", self.scheduler.get_status()["reason"])

    def test_malformed_invalid_items_in_list(self):
        """List containing None, numbers, strings, and partial dicts."""
        now_utc = datetime.datetime(2026, 11, 20, 10, 30, 0, tzinfo=timezone.utc)
        self._write_blocks([
            None,
            123,
            "random string",
            [],
            {},
            {"name": "No times"},
            {"start": "not-a-date", "end": "also-not-a-date"},
            {
                # Valid item alongside invalid ones
                "name": "Surviving Valid Block",
                "start": "2026-11-20T10:00:00Z",
                "end": "2026-11-20T11:00:00Z"
            }
        ])

        self.scheduler.evaluate(now=now_utc)
        self.assertTrue(self.scheduler.is_focus_active())
        self.assertIn("Surviving Valid Block", self.scheduler.get_status()["reason"])

    def test_fallback_when_name_missing(self):
        """When block name is missing or empty, a sensible default is used."""
        now_utc = datetime.datetime(2026, 11, 20, 10, 30, 0, tzinfo=timezone.utc)
        self._write_blocks([{
            "start": "2026-11-20T10:00:00Z",
            "end": "2026-11-20T11:00:00Z"
        }])

        self.scheduler.evaluate(now=now_utc)
        self.assertTrue(self.scheduler.is_focus_active())
        self.assertIn("Productivity Block", self.scheduler.get_status()["reason"])

    # =========================================================================
    # 6. STATUS AND TIME REMAINING
    # =========================================================================

    def test_status_time_remaining_and_callback(self):
        """Check time_remaining_sec countdown and on_state_change callback."""
        callback_events = []
        def on_change(active, reason):
            callback_events.append((active, reason))

        self.scheduler.on_state_change = on_change

        start_dt = datetime.datetime(2026, 11, 20, 10, 0, 0, tzinfo=timezone.utc)
        end_dt = datetime.datetime(2026, 11, 20, 10, 30, 0, tzinfo=timezone.utc)
        self._write_blocks([{
            "name": "Countdown Task",
            "start": start_dt.isoformat(),
            "end": end_dt.isoformat()
        }])

        now_eval = datetime.datetime(2026, 11, 20, 10, 10, 0, tzinfo=timezone.utc)
        self.scheduler.evaluate(now=now_eval)

        status = self.scheduler.get_status(now=now_eval)
        self.assertTrue(status["active"])
        self.assertEqual(status["goal"], "Countdown Task")
        # 20 minutes remaining = 1200 seconds
        self.assertEqual(status["time_remaining_sec"], 1200)

        # Verify callback was fired
        self.assertEqual(len(callback_events), 1)
        self.assertTrue(callback_events[0][0])
        self.assertIn("Countdown Task", callback_events[0][1])


if __name__ == "__main__":
    unittest.main()
