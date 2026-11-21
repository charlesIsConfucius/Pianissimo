"""
Active Window & Process Monitor for FocusShield.
Detects foreground applications and window titles on Windows.
Enforces whitelist/blacklist rules during active focus sessions.
"""

import time
import os
import threading
import ctypes
import ctypes.wintypes
from collections import deque
from datetime import datetime
from typing import Optional, Callable, List, Set, Tuple
import psutil
import win32gui
import win32process
import win32con

from .config import ConfigManager
from .scheduler import FocusScheduler


class WindowMonitor:
    def __init__(
        self,
        config_manager: ConfigManager,
        scheduler: FocusScheduler,
        on_blocked_event: Optional[Callable[[str, str, str], None]] = None,
    ):
        """
        :param on_blocked_event: Callback when an app or tab is blocked.
                                 Signature: (type: 'app'|'tab', target: str, details: str)
        """
        self.config_manager = config_manager
        self.scheduler = scheduler
        self.on_blocked_event = on_blocked_event

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_alert_time = 0.0
        self._last_blocked_target = ""
        self._recent_apps = deque(maxlen=20)
        self._recent_apps_lock = threading.Lock()

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        print("[FocusShield] Window monitor started.")

    def stop(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        print("[FocusShield] Window monitor stopped.")

    @staticmethod
    def get_process_name_by_pid(pid: int) -> str:
        """Fast lookup of process name by PID using psutil with fallback."""
        try:
            return psutil.Process(pid).name()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

        # Fallback to Win32 QueryFullProcessImageNameW
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        h_process = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h_process:
            return "unknown.exe"
        try:
            buffer = ctypes.create_unicode_buffer(1024)
            size = ctypes.wintypes.DWORD(1024)
            if ctypes.windll.kernel32.QueryFullProcessImageNameW(h_process, 0, buffer, ctypes.byref(size)):
                return os.path.basename(buffer.value)
        except Exception:
            pass
        finally:
            ctypes.windll.kernel32.CloseHandle(h_process)
        return "unknown.exe"

    @staticmethod
    def get_running_user_processes() -> List[str]:
        """Returns sorted list of running user process names."""
        names: Set[str] = set()
        for p in psutil.process_iter(["name"]):
            try:
                if p.pid == os.getpid():
                    continue
                name = p.info.get("name")
                if name and name.lower().endswith(".exe"):
                    names.add(name)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return sorted(list(names), key=lambda s: s.lower())

    def recent_blocked_apps(self) -> List[dict]:
        with self._recent_apps_lock:
            return list(self._recent_apps)

    def _monitor_loop(self) -> None:
        while self._running:
            try:
                if self.scheduler.is_focus_active():
                    self._check_foreground_window()
            except Exception as e:
                # Keep monitor alive even if an unexpected Win32 error occurs
                pass
            time.sleep(0.5)

    def _check_foreground_window(self) -> None:
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return

        # Ignore desktop / shell tray windows
        class_name = win32gui.GetClassName(hwnd)
        if class_name in ("Progman", "WorkerW", "Shell_TrayWnd", "NotifyIconOverflowWindow"):
            return

        window_title = win32gui.GetWindowText(hwnd).strip()
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if pid == os.getpid():
            # Don't block FocusShield itself
            return

        process_name = self.get_process_name_by_pid(pid)
        p_lower = process_name.lower()

        # Check desktop app whitelist
        if not self.config_manager.is_app_allowed(p_lower):
            self._handle_blocked_window(hwnd, "app", process_name, f"Application '{process_name}' is restricted during focus.")
            return

        # Website decisions belong to the Chrome extension, which sees URLs.

    def _check_chrome_window_title(self, hwnd: int, title: str) -> None:
        """Inspects window title for known blocked sites (e.g. 'YouTube - Google Chrome')."""
        chrome_mode = self.config_manager.data.get("chrome_mode", "whitelist")
        title_lower = title.lower()

        # If title matches blocked entertainment sites:
        blocked_domains = self.config_manager.data.get("blocked_domains", [])
        for domain in blocked_domains:
            keyword = domain.split(".")[0].lower()
            if len(keyword) > 2 and keyword in title_lower:
                self._handle_blocked_window(
                    hwnd,
                    "tab",
                    domain,
                    f"Blocked Chrome tab detected: '{title}'. Stay focused on your goals!"
                )
                return

    def _handle_blocked_window(self, hwnd: int, block_type: str, target: str, message: str) -> None:
        # Minimize the distracting window
        settings = self.config_manager.data.get("settings", {})
        if settings.get("auto_minimize_blocked_apps", True):
            try:
                win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
            except Exception:
                pass

        # Cooldown check to prevent spamming notifications
        now = time.time()
        if target == self._last_blocked_target and (now - self._last_alert_time) < 3.0:
            return

        self._last_alert_time = now
        self._last_blocked_target = target
        if block_type == "app":
            with self._recent_apps_lock:
                self._recent_apps.appendleft({
                    "name": target.lower(),
                    "time": datetime.now().astimezone().isoformat(timespec="seconds"),
                })

        # Fire callback for GUI overlay/banner
        if self.on_blocked_event:
            try:
                self.on_blocked_event(block_type, target, message)
            except Exception as e:
                print(f"[FocusShield] Error in on_blocked_event: {e}")
