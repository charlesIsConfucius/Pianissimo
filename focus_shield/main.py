"""
FocusShield - Main Application Entry Point.
Launches the scheduler, website blocker, window monitor, and GUI.
"""

import sys
import os
import threading
import webbrowser
import socketserver
import ctypes
import subprocess

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
from focus_shield.gui.app_window import FocusShieldApp


def main():
    if not ctypes.windll.shell32.IsUserAnAdmin():
        raise RuntimeError("Pianissimo needs administrator approval to block websites across Windows. Run it as administrator.")
    print("=" * 60)
    print("🛡️  FocusShield - Distraction Blocker & Focus Suite")
    print("=" * 60)

    # 1. Initialize configuration
    config_mgr = ConfigManager()

    # Reserve the calendar port before changing any website blocks.
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    calendar_server = socketserver.ThreadingTCPServer(("127.0.0.1", calendar_app.PORT), calendar_app.CalendarHandler)

    # 2. Initialize scheduler
    scheduler = FocusScheduler(config_mgr)
    scheduler.start()

    # An independent watchdog removes our entries if this process crashes.
    command = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, os.path.join(parent_dir, "launch.py")]
    subprocess.Popen(command + ["--watch-parent", str(os.getpid())], creationflags=subprocess.CREATE_NO_WINDOW)
    website_blocker = WebsiteBlocker(config_mgr, scheduler)
    website_blocker.start()
    calendar_server.scheduler = scheduler
    calendar_server.website_blocker = website_blocker
    threading.Thread(target=calendar_server.serve_forever, daemon=True).start()
    if not os.environ.get("PIANISSIMO_NO_BROWSER"):
        webbrowser.open(f"http://127.0.0.1:{calendar_app.PORT}")

    # 4. Initialize Desktop GUI
    app = FocusShieldApp(config_mgr, scheduler)
    app.website_blocker = website_blocker

    # 5. Initialize Window Monitor with callback to GUI
    def on_blocked(block_type: str, target: str, message: str):
        app.show_block_notification(block_type, target, message)

    monitor = WindowMonitor(config_mgr, scheduler, on_blocked_event=on_blocked)
    monitor.start()
    app.set_monitor(monitor)

    # 6. Run GUI loop
    try:
        app.mainloop()
    finally:
        print("[FocusShield] Shutting down services...")
        monitor.stop()
        scheduler.stop()
        website_blocker.stop()
        calendar_server.shutdown()
        calendar_server.server_close()
        print("[FocusShield] Goodbye! Stay productive.")


if __name__ == "__main__":
    main()
