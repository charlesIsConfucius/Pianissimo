"""Run the existing Tk controls on their own UI thread alongside the workspace."""

import gc
from queue import Empty, SimpleQueue
from threading import Event, Thread

from customtkinter import AppearanceModeTracker, ScalingTracker

from .app_window import FocusShieldApp


class DesktopControls:
    def __init__(self, config, scheduler, website_blocker):
        self._config = config
        self._scheduler = scheduler
        self._website_blocker = website_blocker
        self._commands = SimpleQueue()
        self._ready = Event()
        self._startup_error = None
        self._thread = Thread(target=self._run, name="Pianissimo desktop controls", daemon=True)

    def start(self):
        self._thread.start()
        if not self._ready.wait(timeout=10):
            raise RuntimeError("Pianissimo's desktop controls did not initialize.")
        if self._startup_error is not None:
            raise RuntimeError(self._startup_error)

    def show(self):
        self._commands.put(("show", ()))

    def notify(self, block_type, target, message):
        self._commands.put(("blocked", (block_type, target, message)))

    def stop(self):
        if self._thread.is_alive():
            self._commands.put(("stop", ()))
            self._thread.join(timeout=3)

    def _run(self):
        try:
            app = FocusShieldApp(self._config, self._scheduler)
        except Exception as error:
            self._startup_error = str(error)
            self._ready.set()
            return

        def process_commands():
            while True:
                try:
                    command, arguments = self._commands.get_nowait()
                except Empty:
                    break
                if command == "stop":
                    app.quit()
                    return
                if command == "show":
                    app.deiconify()
                    app.lift()
                    app.focus_force()
                else:
                    app.show_block_notification(*arguments)
            app.after(75, process_commands)

        try:
            app.website_blocker = self._website_blocker
            app.protocol("WM_DELETE_WINDOW", app.withdraw)
            app.after(0, process_commands)
            self._ready.set()
            app.mainloop()
        finally:
            app.destroy()
            # CustomTkinter retains roots in these trackers after destroy. Release them on the Tk thread.
            if app in AppearanceModeTracker.app_list:
                AppearanceModeTracker.app_list.remove(app)
            ScalingTracker.window_dpi_scaling_dict.pop(app, None)
            app = None
            gc.collect()
