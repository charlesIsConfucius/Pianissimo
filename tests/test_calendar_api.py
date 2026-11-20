"""Calendar persistence requests must never replace a schedule with invalid data."""
import http.client
import json
import os
import tempfile
import threading
import unittest
from datetime import date
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import app


class CalendarApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.directory.name, 'blocks.json')
        self.original = [{"id": "existing", "start": "2026-11-20T09:00:00Z",
                          "end": "2026-11-20T10:00:00Z"}]
        app.save_json(self.path, self.original)
        self.patcher = patch.object(app, 'DATA_FILE', self.path)
        self.patcher.start()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), app.CalendarHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.patcher.stop()
        self.directory.cleanup()

    def post(self, body):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=3)
        try:
            connection.request('POST', '/api/blocks', body, {'Content-Type': 'application/json'})
            response = connection.getresponse()
            result = (response.status, json.loads(response.read()))
            return result
        finally:
            connection.close()

    def test_invalid_requests_preserve_existing_schedule(self):
        bad_blocks = [None, {}, [None], [{}],
                      [{**self.original[0], 'end': 'bad'}],
                      [{**self.original[0], 'end': self.original[0]['start']}],
                      [{**self.original[0], 'start': None}],
                      [self.original[0], self.original[0]],
                      [{**self.original[0], 'name': []}]]
        bodies = ['{broken', 'null', '[]', '{}']
        bodies += [json.dumps({'blocks': blocks}) for blocks in bad_blocks]
        for body in bodies:
            with self.subTest(body=body):
                status, _ = self.post(body)
                self.assertEqual(status, 400)
                self.assertEqual(app.load_json(self.path, None), self.original)

    def test_valid_save_and_explicit_clear(self):
        blocks = [{**self.original[0], 'name': 'Study', 'physics': 'rubber'}]
        for value in [blocks, []]:
            status, body = self.post(json.dumps({'blocks': value}))
            self.assertEqual(status, 200)
            self.assertTrue(body['success'])
            self.assertEqual(app.load_json(self.path, None), value)

    def test_disk_failure_is_reported_without_success(self):
        with patch.object(app, 'save_json', side_effect=OSError('disk full')):
            status, body = self.post(json.dumps({'blocks': self.original}))
        self.assertEqual(status, 500)
        self.assertIn('error', body)
        self.assertEqual(app.load_json(self.path, None), self.original)


class CalendarFeedTests(unittest.TestCase):
    def test_recurring_timezone_event_honors_exclusion_and_override_across_dst(self):
        feed = '\r\n'.join([
            'BEGIN:VCALENDAR', 'VERSION:2.0',
            'BEGIN:VEVENT', 'UID:study', 'SUMMARY:Study',
            'DTSTART;TZID=America/Chicago:20261030T090000',
            'DTEND;TZID=America/Chicago:20261030T100000',
            'RRULE:FREQ=DAILY;COUNT=4',
            'EXDATE;TZID=America/Chicago:20261031T090000', 'END:VEVENT',
            'BEGIN:VEVENT', 'UID:study', 'SUMMARY:Moved',
            'RECURRENCE-ID;TZID=America/Chicago:20261102T090000',
            'DTSTART;TZID=America/Chicago:20261102T110000',
            'DTEND;TZID=America/Chicago:20261102T120000', 'END:VEVENT',
            'END:VCALENDAR', '',
        ])
        events = app.parse_ics(feed, date(2026, 10, 26))
        self.assertEqual(len(events), 3)
        starts = {event['start'] for event in events}
        self.assertIn('2026-10-30T09:00:00-05:00', starts)
        self.assertIn('2026-11-01T09:00:00-06:00', starts)
        self.assertIn('2026-11-02T11:00:00-06:00', starts)
        self.assertFalse(any(value.startswith('2026-10-31') for value in starts))

    def test_all_day_end_is_exclusive_and_cancelled_events_are_omitted(self):
        feed = '\r\n'.join([
            'BEGIN:VCALENDAR', 'VERSION:2.0',
            'BEGIN:VEVENT', 'UID:trip', 'SUMMARY:Trip',
            'DTSTART;VALUE=DATE:20261120', 'DTEND;VALUE=DATE:20261122', 'END:VEVENT',
            'BEGIN:VEVENT', 'UID:cancelled', 'STATUS:CANCELLED',
            'DTSTART:20261120T090000Z', 'DTEND:20261120T100000Z', 'END:VEVENT',
            'END:VCALENDAR', '',
        ])
        events = app.parse_ics(feed, date(2026, 11, 16))
        self.assertEqual(len(events), 1)
        self.assertTrue(events[0]['all_day'])
        self.assertEqual(events[0]['end'], '2026-11-22T00:00:00')
