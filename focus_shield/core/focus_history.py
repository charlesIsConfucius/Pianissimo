"""Durable local history of intervals when the desktop focus scheduler ran."""
import datetime
import os
import sqlite3
import threading
import time

from app_paths import DATA_ROOT

DEFAULT_HISTORY_PATH = os.path.join(DATA_ROOT, "focus_history.sqlite3")
MAX_CHECKPOINT_GAP = 5.0


class FocusHistory:
    def __init__(self, path=DEFAULT_HISTORY_PATH):
        self.path = path
        self._lock = threading.Lock()
        self._connection = sqlite3.connect(path, timeout=10, check_same_thread=False)
        with self._connection:
            self._connection.execute("""CREATE TABLE IF NOT EXISTS focus_sessions (
                id INTEGER PRIMARY KEY, started_at REAL NOT NULL,
                ended_at REAL NOT NULL, reason TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('active', 'completed', 'interrupted'))
            )""")
            # The last checkpoint is the only duration we can establish after a crash.
            self._connection.execute("UPDATE focus_sessions SET status='interrupted' WHERE status='active'")
        self._active_id = None
        self._last_checkpoint = None

    def record_state(self, active, reason, timestamp=None):
        now = time.time() if timestamp is None else float(timestamp)
        with self._lock, self._connection:
            if self._active_id is not None:
                gap = now - self._last_checkpoint
                if gap < 0 or gap > MAX_CHECKPOINT_GAP:
                    self._connection.execute("UPDATE focus_sessions SET status='interrupted' WHERE id=?", (self._active_id,))
                    self._active_id = None
                else:
                    status = 'active' if active else 'completed'
                    self._connection.execute("UPDATE focus_sessions SET ended_at=?, status=? WHERE id=?", (now, status, self._active_id))
                    self._last_checkpoint = now
                    if not active:
                        self._active_id = None
            if active and self._active_id is None:
                cursor = self._connection.execute(
                    "INSERT INTO focus_sessions(started_at, ended_at, reason, status) VALUES (?, ?, ?, 'active')",
                    (now, now, str(reason)))
                self._active_id = cursor.lastrowid
                self._last_checkpoint = now

    def daily_totals(self, today=None):
        """Return seven local calendar dates, including the latest checkpoint."""
        today = today or datetime.date.today()
        first = today - datetime.timedelta(days=6)
        dates = [first + datetime.timedelta(days=i) for i in range(8)]
        # Naive local midnight timestamps account for each day's DST offset.
        boundaries = [datetime.datetime.combine(day, datetime.time.min).timestamp() for day in dates]
        with self._lock:
            rows = self._connection.execute(
                "SELECT started_at, ended_at FROM focus_sessions WHERE ended_at > ? AND started_at < ?",
                (boundaries[0], boundaries[-1])).fetchall()
        result = []
        for i, day in enumerate(dates[:-1]):
            seconds = sum(max(0.0, min(end, boundaries[i + 1]) - max(start, boundaries[i])) for start, end in rows)
            result.append({"date": day.isoformat(), "seconds": int(seconds)})
        return result

    def sessions(self):
        """Return saved focus intervals, including any currently active interval."""
        with self._lock:
            rows = self._connection.execute(
                "SELECT id, started_at, ended_at, reason, status FROM focus_sessions ORDER BY started_at, id"
            ).fetchall()
        return [dict(zip(("id", "started_at", "ended_at", "reason", "status"), row)) for row in rows]

    def close(self, timestamp=None):
        self.record_state(False, "", timestamp)
        with self._lock:
            self._connection.close()
