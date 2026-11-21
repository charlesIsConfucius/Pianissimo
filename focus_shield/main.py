"""
FocusShield - Main Application Entry Point.
Launches the scheduler, website blocker, window monitor, and GUI.
"""

import sys
import os
import threading
import socketserver
import ctypes
import subprocess
from contextlib import ExitStack

# Ensure package path is accessible
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

import app as calendar_app
from focus_shield.core.config import ConfigManager
from focus_shield.core.scheduler import FocusScheduler
from focus_shield.core.website_blocker import WebsiteBlocker
from focus_shield.core.monitor import WindowMonitor
from focus_shield.gui.desktop_controls import DesktopControls
from focus_shield.gui.workspace import run_workspace


def main():
    if not ctypes.windll.shell32.IsUserAnAdmin():
        raise RuntimeError("Pianissimo needs administrator approval to block websites across Windows. Run it as administrator.")
    # Reserve the calendar port before changing any website blocks.
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    address = ("127.0.0.1", calendar_app.PORT)
    with ExitStack() as cleanup:
        calendar_server = cleanup.enter_context(socketserver.ThreadingTCPServer(address, calendar_app.CalendarHandler))
        config = ConfigManager()
        scheduler = FocusScheduler(config)
        scheduler.start()
        cleanup.callback(scheduler.stop)

        # The watchdog removes this process's hosts entries if the app exits unexpectedly.
        command = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, os.path.join(parent_dir, "launch.py")]
        subprocess.Popen(command + ["--watch-parent", str(os.getpid())], creationflags=subprocess.CREATE_NO_WINDOW)
        website_blocker = WebsiteBlocker(config, scheduler)
        website_blocker.start()
        cleanup.callback(website_blocker.stop)

        controls = DesktopControls(config, scheduler, website_blocker)
        cleanup.callback(controls.stop)
        controls.start()
        monitor = WindowMonitor(config, scheduler, on_blocked_event=controls.notify)
        monitor.start()
        cleanup.callback(monitor.stop)

        calendar_server.scheduler = scheduler
        calendar_server.website_blocker = website_blocker
        calendar_server.app_monitor = monitor
        threading.Thread(target=calendar_server.serve_forever, daemon=True).start()
        cleanup.callback(calendar_server.shutdown)
        run_workspace(f"http://{address[0]}:{address[1]}", controls.show)


if __name__ == "__main__":
    main()
