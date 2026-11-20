"""
Scheduler and Focus Session Timer for FocusShield / Pianissimo.
Tracks manual countdown sessions, daily/weekly scheduled focus hours,
and dated productivity blocks from productivity_blocks.json.
"""

import os
import json
import time
import datetime
from datetime import timezone
import threading
from typing import Optional, Callable, Dict, Any, List, Tuple
from .config import ConfigManager
from app_paths import DATA_ROOT
from .focus_history import FocusHistory


# Default path to productivity_blocks.json located at workspace root
# (3 directories above focus_shield/core/scheduler.py)
DEFAULT_BLOCKS_PATH = os.path.join(DATA_ROOT, "productivity_blocks.json")


class FocusScheduler:
    def __init__(
        self,
        config_manager: ConfigManager,
        on_state_change: Optional[Callable[[bool, str], None]] = None,
        blocks_path: Optional[str] = None,
        history_path: Optional[str] = None
    ):
        self.config_manager = config_manager
        self.on_state_change = on_state_change
        self._custom_blocks_path = blocks_path
        self.blocks_path = blocks_path or DEFAULT_BLOCKS_PATH
        self.focus_history = FocusHistory(history_path) if history_path is not None else FocusHistory()

        # Manual timer state
        self.manual_session_active = False
        self.manual_session_end_time: Optional[float] = None
        self.manual_session_duration: int = 0
        self.manual_session_goal: str = "Focus Session"

        # Dated productivity block state
        self._active_block_names: List[str] = []
        self._active_block_end_time: Optional[datetime.datetime] = None

        # Overall state
        self._is_active = False
        self._active_reason = "Idle"

        # Background worker
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._check_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join()
        self.focus_history.close()

    def start_manual_session(self, duration_minutes: int, goal: str = "Deep Focus") -> None:
        with self._lock:
            self.manual_session_active = True
            self.manual_session_duration = duration_minutes * 60
            self.manual_session_end_time = time.time() + self.manual_session_duration
            self.manual_session_goal = goal
        self._evaluate_state()

    def stop_manual_session(self) -> None:
        with self._lock:
            self.manual_session_active = False
            self.manual_session_end_time = None
        self._evaluate_state()

    def is_focus_active(self) -> bool:
        return self._is_active

    def evaluate(self, now: Optional[datetime.datetime] = None) -> None:
        """Explicitly triggers evaluation of current state."""
        self._evaluate_state(now)

    def get_status(self, now: Optional[datetime.datetime] = None) -> Dict[str, Any]:
        with self._lock:
            time_left = 0
            goal = self.manual_session_goal
            if self.manual_session_active and self.manual_session_end_time:
                curr_t = now.timestamp() if now is not None else time.time()
                time_left = max(0, int(self.manual_session_end_time - curr_t))
            elif self._active_block_end_time:
                now_utc = self._normalize_now(now)
                time_left = max(0, int((self._active_block_end_time - now_utc).total_seconds()))
                if self._active_block_names:
                    goal = ", ".join(self._active_block_names)

            return {
                "active": self._is_active,
                "reason": self._active_reason,
                "time_remaining_sec": time_left,
                "goal": goal,
                "manual_active": self.manual_session_active,
            }

    def _get_blocks_file_path(self) -> str:
        if self._custom_blocks_path is not None:
            return self._custom_blocks_path
        return self.blocks_path

    @staticmethod
    def _parse_iso_datetime(val: Any) -> Optional[datetime.datetime]:
        """
        Parses an ISO 8601 string or numeric timestamp into an offset-aware UTC datetime.
        Returns None if parsing fails.
        """
        if val is None:
            return None

        if isinstance(val, (int, float)):
            try:
                return datetime.datetime.fromtimestamp(val, tz=timezone.utc)
            except Exception:
                return None

        if not isinstance(val, str):
            return None

        val_str = val.strip()
        if not val_str:
            return None

        dt: Optional[datetime.datetime] = None
        try:
            dt = datetime.datetime.fromisoformat(val_str)
        except Exception:
            if val_str.endswith("Z") or val_str.endswith("z"):
                try:
                    dt = datetime.datetime.fromisoformat(val_str[:-1] + "+00:00")
                except Exception:
                    pass
            if dt is None:
                clean_val = val_str.rstrip("Zz")
                if "T" in clean_val and len(clean_val.replace("T", "")) >= 14:
                    try:
                        dt = datetime.datetime.strptime(clean_val[:15], "%Y%m%dT%H%M%S")
                    except Exception:
                        pass
                elif len(clean_val) == 8 and clean_val.isdigit():
                    try:
                        dt = datetime.datetime.strptime(clean_val, "%Y%m%d")
                    except Exception:
                        pass

        if dt is None:
            return None

        # If naive, interpret as local time according to system timezone
        if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
            dt = dt.astimezone()

        # Normalize to UTC
        return dt.astimezone(timezone.utc)

    @staticmethod
    def _normalize_now(now: Optional[datetime.datetime] = None) -> datetime.datetime:
        if now is None:
            return datetime.datetime.now(timezone.utc)
        if now.tzinfo is None or now.tzinfo.utcoffset(now) is None:
            return now.astimezone().astimezone(timezone.utc)
        return now.astimezone(timezone.utc)

    def _load_blocks(self) -> List[Dict[str, Any]]:
        """
        Reads productivity_blocks.json afresh each evaluation.
        Safely handles missing file, permission errors, and malformed JSON.
        """
        path = self._get_blocks_file_path()
        if not path or not os.path.exists(path):
            return []

        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read().strip()
            if not content:
                return []
            data = json.loads(content)
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and isinstance(data.get("blocks"), list):
                return data["blocks"]
            return []
        except Exception:
            # File might be partially written, locked, or malformed JSON
            return []

    def _get_active_blocks(self, now: Optional[datetime.datetime] = None) -> List[Dict[str, Any]]:
        """
        Evaluates productivity_blocks.json and returns all blocks active at the specified time.
        Handles boundaries (start inclusive, end exclusive), timezone conversions, and invalid data.
        """
        now_utc = self._normalize_now(now)
        raw_blocks = self._load_blocks()
        active_blocks = []

        for block in raw_blocks:
            if not isinstance(block, dict):
                continue

            start_raw = block.get("start")
            end_raw = block.get("end")
            if not start_raw or not end_raw:
                continue

            start_dt = self._parse_iso_datetime(start_raw)
            end_dt = self._parse_iso_datetime(end_raw)

            if start_dt is None or end_dt is None:
                continue

            # Invalid interval: end must be strictly after start
            if end_dt <= start_dt:
                continue

            # Boundary condition: start <= now < end
            if start_dt <= now_utc < end_dt:
                name = block.get("name") or block.get("summary") or block.get("title") or "Productivity Block"
                active_blocks.append({
                    "id": block.get("id"),
                    "name": str(name).strip() or "Productivity Block",
                    "category": block.get("category", "General"),
                    "start": start_dt,
                    "end": end_dt,
                    "raw": block
                })

        return active_blocks

    def _check_blocks_match(self, now: Optional[datetime.datetime] = None) -> Optional[str]:
        """
        Checks if current time falls within any dated productivity block.
        If multiple overlapping blocks match, joins their unique names.
        """
        active_blocks = self._get_active_blocks(now)
        if not active_blocks:
            return None

        names: List[str] = []
        for b in active_blocks:
            name = b["name"]
            if name not in names:
                names.append(name)

        return ", ".join(names) if names else "Productivity Block"

    def _check_schedule_match(self, now: Optional[datetime.datetime] = None) -> Optional[str]:
        """Checks if current time falls within any enabled recurring schedule."""
        schedules = self.config_manager.data.get("schedules", [])
        if now is None:
            now_local = datetime.datetime.now()
        else:
            if now.tzinfo is not None:
                now_local = now.astimezone()
            else:
                now_local = now

        current_day = now_local.weekday()  # Monday = 0, Sunday = 6
        current_time_str = now_local.strftime("%H:%M")

        for sched in schedules:
            if not sched.get("enabled", True):
                continue
            days = sched.get("days", [])
            start_str = sched.get("start_time", "00:00")
            end_str = sched.get("end_time", "23:59")

            # Simple HH:MM comparison
            if start_str <= end_str:
                if current_day in days and start_str <= current_time_str < end_str:
                    return sched.get("name", "Scheduled Focus")
            else:
                # Spans midnight
                if (current_day in days and current_time_str >= start_str) or ((current_day - 1) % 7 in days and current_time_str < end_str):
                    return sched.get("name", "Scheduled Focus")
        return None

    def _evaluate_state(self, now: Optional[datetime.datetime] = None) -> None:
        with self._lock:
            # Check manual session expiration
            current_timestamp = now.timestamp() if now is not None else time.time()
            if self.manual_session_active:
                if self.manual_session_end_time and current_timestamp >= self.manual_session_end_time:
                    self.manual_session_active = False
                    self.manual_session_end_time = None

            matched_schedule = self._check_schedule_match(now)
            active_blocks = self._get_active_blocks(now)

            if active_blocks:
                names: List[str] = []
                for b in active_blocks:
                    name = b["name"]
                    if name not in names:
                        names.append(name)
                matched_block = ", ".join(names) if names else "Productivity Block"
                self._active_block_names = names
                self._active_block_end_time = max(b["end"] for b in active_blocks)
            else:
                matched_block = None
                self._active_block_names = []
                self._active_block_end_time = None

            if self.manual_session_active:
                new_state = True
                new_reason = f"Manual Session ({self.manual_session_goal})"
            elif matched_block and matched_schedule:
                new_state = True
                new_reason = f"Productivity Block: {matched_block} | Schedule: {matched_schedule}"
            elif matched_block:
                new_state = True
                new_reason = f"Productivity Block: {matched_block}"
            elif matched_schedule:
                new_state = True
                new_reason = f"Schedule: {matched_schedule}"
            else:
                new_state = False
                new_reason = "Idle (No active session)"

            changed = (new_state != self._is_active or new_reason != self._active_reason)
            self._is_active = new_state
            self._active_reason = new_reason
            self.focus_history.record_state(new_state, new_reason, current_timestamp)

        if changed and self.on_state_change:
            try:
                self.on_state_change(self._is_active, self._active_reason)
            except Exception as e:
                print(f"Error in on_state_change callback: {e}")

    def _check_loop(self) -> None:
        while self._running:
            self._evaluate_state()
            time.sleep(1.0)
