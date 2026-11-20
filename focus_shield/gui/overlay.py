"""
Non-intrusive floating HUD overlay for FocusShield.
Appears at the top-center of the screen when a distraction is blocked.
"""

import tkinter as tk
from typing import Optional


class FocusOverlay:
    def __init__(self, master: tk.Tk):
        self.master = master
        self.window: Optional[tk.Toplevel] = None
        self._hide_timer = None

    def show(self, title: str, message: str, duration_ms: int = 3500) -> None:
        """Displays or updates the floating overlay."""
        # Ensure executed on the main GUI thread
        self.master.after(0, self._show_on_gui_thread, title, message, duration_ms)

    def _show_on_gui_thread(self, title: str, message: str, duration_ms: int) -> None:
        if self._hide_timer:
            self.master.after_cancel(self._hide_timer)
            self._hide_timer = None

        if self.window is None or not self.window.winfo_exists():
            self.window = tk.Toplevel(self.master)
            self.window.overrideredirect(True)
            self.window.attributes("-topmost", True)
            self.window.attributes("-alpha", 0.94)

            card_background = "#f6f5ff"
            self.card = tk.Frame(
                self.window,
                bg=card_background,
                highlightthickness=2,
                highlightbackground="#a49ace",
                padx=24,
                pady=16,
            )
            self.card.pack(fill="both", expand=True)

            self.header_label = tk.Label(
                self.card,
                text="",
                font=("Segoe UI", 11, "bold"),
                fg="#494080",
                bg=card_background,
            )
            self.header_label.pack(anchor="w")

            self.msg_label = tk.Label(
                self.card,
                text="",
                font=("Segoe UI", 10),
                fg="#28263a",
                bg=card_background,
                wraplength=480,
                justify="left",
            )
            self.msg_label.pack(anchor="w", pady=(4, 0))

        # Update texts
        self.header_label.config(text=f"🛡️ {title.upper()}")
        self.msg_label.config(text=message)

        # Center top of screen
        self.window.update_idletasks()
        req_w = max(420, self.window.winfo_reqwidth())
        req_h = self.window.winfo_reqheight()
        screen_w = self.master.winfo_screenwidth()
        x = (screen_w - req_w) // 2
        y = 50

        self.window.geometry(f"{req_w}x{req_h}+{x}+{y}")
        self.window.deiconify()

        # Schedule auto-hide
        self._hide_timer = self.master.after(duration_ms, self._hide)

    def _hide(self) -> None:
        if self.window and self.window.winfo_exists():
            self.window.withdraw()
        self._hide_timer = None
