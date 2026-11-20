"""
Main Graphical User Interface for FocusShield.
Built with CustomTkinter for the Pianissimo desktop interface.
"""

import os
import sys
import time
import datetime
import winsound
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Optional, List, Dict, Any
import customtkinter as ctk
from focus_shield.core.website_blocker import normalize_domain

from ..core.config import ConfigManager
from ..core.scheduler import FocusScheduler
from ..core.monitor import WindowMonitor
from .overlay import FocusOverlay

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")


class FocusShieldApp(ctk.CTk):
    def __init__(self, config_manager: ConfigManager, scheduler: FocusScheduler):
        super().__init__()

        self.config_manager = config_manager
        self.scheduler = scheduler
        self.monitor: Optional[WindowMonitor] = None

        self.title("Pianissimo - Focus and Calendar")
        self.geometry("980x720")
        self.minsize(860, 620)

        # Overlay notification window
        self.overlay = FocusOverlay(self)

        # Statistics / session tracker
        self.blocked_count_session = 0
        self.event_logs: List[Dict[str, str]] = []

        # Build UI
        self._build_header()
        self._build_tabs()

        # Periodically refresh status (1 Hz)
        self.after(500, self._tick_timer)

    def set_monitor(self, monitor: WindowMonitor) -> None:
        self.monitor = monitor

    # -------------------------------------------------------------
    # HEADER SECTION
    # -------------------------------------------------------------
    def _build_header(self) -> None:
        self.header_frame = ctk.CTkFrame(self, height=85, corner_radius=12, fg_color="#ffffff")
        self.header_frame.pack(fill="x", padx=16, pady=(16, 8))

        # Left branding
        title_box = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        title_box.pack(side="left", padx=20, pady=12)

        logo_label = ctk.CTkLabel(
            title_box,
            text="Pianissimo",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color="#20263a",
        )
        logo_label.pack(anchor="w")

        self.sub_status_label = ctk.CTkLabel(
            title_box,
            text="Blocker ready",
            font=ctk.CTkFont(size=12),
            text_color="#525c73",
        )
        self.sub_status_label.pack(anchor="w")

        # Right status badge & quick toggle
        right_box = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        right_box.pack(side="right", padx=20, pady=12)

        self.status_badge = ctk.CTkLabel(
            right_box,
            text="IDLE",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#e5e9f4",
            text_color="#374057",
            corner_radius=8,
            width=110,
            height=32,
        )
        self.status_badge.pack(side="left", padx=(0, 14))

        self.btn_main_toggle = ctk.CTkButton(
            right_box,
            text="Start Focus Now",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#5550b4",
            hover_color="#49439e",
            width=150,
            height=36,
            command=self._on_main_toggle_clicked,
        )
        self.btn_main_toggle.pack(side="left")

    # -------------------------------------------------------------
    # TABS NAVIGATION
    # -------------------------------------------------------------
    def _build_tabs(self) -> None:
        self.tabview = ctk.CTkTabview(
            self,
            corner_radius=12,
            fg_color="#f5f6fb",
            segmented_button_fg_color="#edf0f7",
            text_color="#20263a",
            segmented_button_selected_color="#ddd7fa",
            segmented_button_selected_hover_color="#d1c8f2",
            segmented_button_unselected_color="#edf0f7",
            segmented_button_unselected_hover_color="#dfe4f2",
        )
        self.tabview.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        self.tab_dash = self.tabview.add("Focus")
        self.tab_apps = self.tabview.add("Allowed Apps")
        self.tab_chrome = self.tabview.add("Blocked Websites")
        self.tab_sched = self.tabview.add("Schedules")
        self.tab_settings = self.tabview.add("Settings")

        self._build_dashboard_tab()
        self._build_apps_tab()
        self._build_chrome_tab()
        self._build_schedules_tab()
        self._build_settings_tab()

    # -------------------------------------------------------------
    # TAB 1: DASHBOARD
    # -------------------------------------------------------------
    def _build_dashboard_tab(self) -> None:
        # Top banner card
        banner_card = ctk.CTkFrame(self.tab_dash, corner_radius=12, fg_color="#edf0f7")
        banner_card.pack(fill="x", padx=12, pady=12)

        # Countdown & Goal
        timer_col = ctk.CTkFrame(banner_card, fg_color="transparent")
        timer_col.pack(side="left", padx=24, pady=18)

        lbl_goal_title = ctk.CTkLabel(timer_col, text="Focus session", font=ctk.CTkFont(size=11, weight="bold"), text_color="#5147a8")
        lbl_goal_title.pack(anchor="w")

        self.lbl_active_goal = ctk.CTkLabel(timer_col, text="Ready for Deep Work", font=ctk.CTkFont(size=20, weight="bold"), text_color="#20263a")
        self.lbl_active_goal.pack(anchor="w", pady=(2, 4))

        self.lbl_big_timer = ctk.CTkLabel(timer_col, text="--:--", font=ctk.CTkFont(size=44, weight="bold"), text_color="#5147a8")
        self.lbl_big_timer.pack(anchor="w")

        # Quick preset buttons on right
        preset_col = ctk.CTkFrame(banner_card, fg_color="transparent")
        preset_col.pack(side="right", padx=24, pady=18)

        lbl_presets = ctk.CTkLabel(preset_col, text="Quick start", font=ctk.CTkFont(size=11, weight="bold"), text_color="#525c73")
        lbl_presets.pack(anchor="e", pady=(0, 6))

        p_btns_frame = ctk.CTkFrame(preset_col, fg_color="transparent")
        p_btns_frame.pack(anchor="e")

        for mins, label in [(25, "25m (Pomodoro)"), (45, "45m (Sprint)"), (60, "60m (Deep)"), (90, "90m (Ultra)")]:
            btn = ctk.CTkButton(
                p_btns_frame,
                text=label,
                width=110,
                height=30,
                font=ctk.CTkFont(size=11),
                fg_color="#2b2d49",
                hover_color="#3d4068",
                command=lambda m=mins: self._start_custom_session(m),
            )
            btn.pack(side="left", padx=4)

        # Goal input field
        custom_input_frame = ctk.CTkFrame(preset_col, fg_color="transparent")
        custom_input_frame.pack(anchor="e", pady=(10, 0))

        self.entry_goal = ctk.CTkEntry(custom_input_frame, placeholder_text="Goal (e.g. Coding, Writing, Study)", width=230, height=32)
        self.entry_goal.pack(side="left", padx=(0, 6))

        self.entry_custom_mins = ctk.CTkEntry(custom_input_frame, placeholder_text="Mins", width=60, height=32)
        self.entry_custom_mins.insert(0, "30")
        self.entry_custom_mins.pack(side="left", padx=(0, 6))

        btn_start_custom = ctk.CTkButton(
            custom_input_frame,
            text="Start",
            width=70,
            height=32,
            fg_color="#5550b4",
            hover_color="#49439e",
            command=self._on_start_custom_clicked,
        )
        btn_start_custom.pack(side="left")

        # Metrics Row
        stats_frame = ctk.CTkFrame(self.tab_dash, fg_color="transparent")
        stats_frame.pack(fill="x", padx=12, pady=(0, 12))

        self.card_apps_stat = self._create_stat_card(stats_frame, "ALLOWED APPS", str(len(self.config_manager.data.get("allowed_apps", []))), "#21658b")
        self.card_domains_stat = self._create_stat_card(stats_frame, "BLOCKED WEBSITES", str(len(self.config_manager.data.get("blocked_domains", []))), "#087654")
        self.card_blocks_stat = self._create_stat_card(stats_frame, "DISTRACTIONS BLOCKED", "0", "#ae3445")

        # Live Distraction Event Feed
        feed_header = ctk.CTkLabel(self.tab_dash, text="Activity", font=ctk.CTkFont(size=14, weight="bold"), text_color="#20263a")
        feed_header.pack(anchor="w", padx=16, pady=(6, 4))

        self.feed_scroll = ctk.CTkScrollableFrame(self.tab_dash, height=220, corner_radius=10, fg_color="#ffffff")
        self.feed_scroll.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        self._render_log_feed()

    def _create_stat_card(self, parent, title: str, val: str, color: str):
        card = ctk.CTkFrame(parent, corner_radius=10, fg_color="#ffffff", height=70)
        card.pack(side="left", fill="x", expand=True, padx=4)

        lbl_t = ctk.CTkLabel(card, text=title, font=ctk.CTkFont(size=10, weight="bold"), text_color="#525c73")
        lbl_t.pack(anchor="w", padx=16, pady=(10, 0))

        lbl_v = ctk.CTkLabel(card, text=val, font=ctk.CTkFont(size=22, weight="bold"), text_color=color)
        lbl_v.pack(anchor="w", padx=16, pady=(0, 8))
        return lbl_v

    # -------------------------------------------------------------
    # TAB 2: PRODUCTIVE APPS (WHITELIST)
    # -------------------------------------------------------------
    def _build_apps_tab(self) -> None:
        top_ctrl = ctk.CTkFrame(self.tab_apps, fg_color="transparent")
        top_ctrl.pack(fill="x", padx=12, pady=10)

        # Mode explanation
        mode_box = ctk.CTkFrame(top_ctrl, corner_radius=8, fg_color="#eeebfa")
        mode_box.pack(side="left", fill="x", expand=True, padx=4, pady=4)

        lbl_mode = ctk.CTkLabel(
            mode_box,
            text="Enforcement Mode: Strict Whitelist",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#5147a8",
        )
        lbl_mode.pack(anchor="w")

        lbl_mode_desc = ctk.CTkLabel(
            mode_box,
            text="During focus sessions, only programs listed below are permitted to stay open.",
            font=ctk.CTkFont(size=11),
            text_color="#525c73",
        )
        lbl_mode_desc.pack(anchor="w")

        # Add app section
        add_frame = ctk.CTkFrame(self.tab_apps, corner_radius=10, fg_color="#ffffff")
        add_frame.pack(fill="x", padx=12, pady=(0, 10))

        # Add from running apps
        lbl_running = ctk.CTkLabel(add_frame, text="Quick Add from Running Programs:", font=ctk.CTkFont(size=12, weight="bold"), text_color="#20263a")
        lbl_running.pack(anchor="w", pady=(0, 4))

        running_row = ctk.CTkFrame(add_frame, fg_color="transparent")
        running_row.pack(fill="x", pady=(0, 10))

        self.combo_running_apps = ctk.CTkComboBox(running_row, width=280, values=["Click Scan to find apps"])
        self.combo_running_apps.pack(side="left", padx=(0, 8))

        btn_scan = ctk.CTkButton(running_row, text="Scan Running Apps", width=140, fg_color="#2b2d49", hover_color="#3d4068", command=self._scan_running_apps)
        btn_scan.pack(side="left", padx=(0, 8))

        btn_add_selected = ctk.CTkButton(running_row, text="+ Whitelist Selected", width=150, fg_color="#087654", hover_color="#075f45", command=self._add_selected_from_combo)
        btn_add_selected.pack(side="left")

        # Or type manual exe / browse
        manual_row = ctk.CTkFrame(add_frame, fg_color="transparent")
        manual_row.pack(fill="x")

        self.entry_manual_app = ctk.CTkEntry(manual_row, placeholder_text="Or type process name (e.g. obsidian.exe)", width=280)
        self.entry_manual_app.pack(side="left", padx=(0, 8))

        btn_add_manual = ctk.CTkButton(manual_row, text="+ Add Name", width=100, fg_color="#5550b4", hover_color="#49439e", command=self._add_manual_app)
        btn_add_manual.pack(side="left", padx=(0, 8))

        btn_browse_exe = ctk.CTkButton(manual_row, text="Browse .exe File...", width=140, fg_color="#2b2d49", hover_color="#3d4068", command=self._browse_app_file)
        btn_browse_exe.pack(side="left")

        # Scrollable list of allowed apps
        list_hdr = ctk.CTkLabel(self.tab_apps, text="Allowed Productive Applications:", font=ctk.CTkFont(size=13, weight="bold"), text_color="#20263a")
        list_hdr.pack(anchor="w", padx=16, pady=(4, 4))

        self.apps_scroll = ctk.CTkScrollableFrame(self.tab_apps, height=260, corner_radius=10, fg_color="#ffffff")
        self.apps_scroll.pack(fill="both", expand=True, padx=12, pady=(0, 10))

        self._refresh_apps_list()

    def _refresh_apps_list(self) -> None:
        for widget in self.apps_scroll.winfo_children():
            widget.destroy()

        allowed_apps = sorted(self.config_manager.data.get("allowed_apps", []))
        for app in allowed_apps:
            row = ctk.CTkFrame(self.apps_scroll, fg_color="#edf0f7", height=38, corner_radius=6)
            row.pack(fill="x", padx=4, pady=3)

            lbl = ctk.CTkLabel(row, text=f"  💻  {app}", font=ctk.CTkFont(size=12, weight="bold"), text_color="#374057")
            lbl.pack(side="left", padx=8)

            btn_del = ctk.CTkButton(
                row,
                text="Remove",
                width=75,
                height=26,
                font=ctk.CTkFont(size=11),
                fg_color="#ae3445",
                hover_color="#922539",
                command=lambda a=app: self._remove_app(a),
            )
            btn_del.pack(side="right", padx=8)

        if hasattr(self, "card_apps_stat"):
            self.card_apps_stat.configure(text=str(len(allowed_apps)))

    def _scan_running_apps(self) -> None:
        apps = WindowMonitor.get_running_user_processes()
        allowed = [a.lower() for a in self.config_manager.data.get("allowed_apps", [])]
        sys_apps = [s.lower() for s in self.config_manager.data.get("system_whitelist", [])]

        unwhitelisted = [a for a in apps if a.lower() not in allowed and a.lower() not in sys_apps]
        if unwhitelisted:
            self.combo_running_apps.configure(values=unwhitelisted)
            self.combo_running_apps.set(unwhitelisted[0])
        else:
            self.combo_running_apps.configure(values=["All running apps already whitelisted"])
            self.combo_running_apps.set("All running apps already whitelisted")

    def _add_selected_from_combo(self) -> None:
        val = self.combo_running_apps.get()
        if val and val.endswith(".exe") and "whitelisted" not in val:
            self.config_manager.add_allowed_app(val)
            self._refresh_apps_list()
            self._scan_running_apps()

    def _add_manual_app(self) -> None:
        val = self.entry_manual_app.get().strip()
        if val:
            self.config_manager.add_allowed_app(val)
            self.entry_manual_app.delete(0, "end")
            self._refresh_apps_list()

    def _browse_app_file(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("Executable Files", "*.exe")])
        if path:
            exe_name = os.path.basename(path)
            self.config_manager.add_allowed_app(exe_name)
            self._refresh_apps_list()

    def _remove_app(self, app_name: str) -> None:
        self.config_manager.remove_allowed_app(app_name)
        self._refresh_apps_list()

    # -------------------------------------------------------------
    # TAB 3: BLOCKED WEBSITES
    # -------------------------------------------------------------
    def _build_chrome_tab(self) -> None:
        info = ctk.CTkLabel(self.tab_chrome, text="These websites are blocked across Windows during focus sessions.\nEnter a domain such as youtube.com. Existing connections and other subdomains may remain accessible.", justify="left", wraplength=760)
        info.pack(anchor="w", padx=18, pady=14)
        controls = ctk.CTkFrame(self.tab_chrome, fg_color="transparent")
        controls.pack(fill="x", padx=12, pady=6)
        self.entry_domain = ctk.CTkEntry(controls, placeholder_text="Website domain, e.g. youtube.com", width=360)
        self.entry_domain.pack(side="left", padx=(0, 8))
        ctk.CTkButton(controls, text="Add blocked website", command=self._add_domain).pack(side="left")
        self.website_status = ctk.CTkLabel(self.tab_chrome, text="Website blocking is ready.", text_color="#525c73", wraplength=760)
        self.website_status.pack(anchor="w", padx=18, pady=6)
        self.domains_scroll = ctk.CTkScrollableFrame(self.tab_chrome, height=220, corner_radius=10, fg_color="#ffffff")
        self.domains_scroll.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        self._refresh_domains_list()

    def _refresh_domains_list(self) -> None:
        for widget in self.domains_scroll.winfo_children():
            widget.destroy()
        domains = sorted(self.config_manager.data.get("blocked_domains", []))
        for dom in domains:
            row = ctk.CTkFrame(self.domains_scroll, fg_color="#edf0f7", height=38, corner_radius=6)
            row.pack(fill="x", padx=4, pady=3)
            ctk.CTkLabel(row, text=dom).pack(side="left", padx=10)
            ctk.CTkButton(row, text="Remove", width=75, command=lambda d=dom: self._remove_domain(d)).pack(side="right", padx=8, pady=3)
        if hasattr(self, "card_domains_stat"):
            self.card_domains_stat.configure(text=str(len(domains)))

    def _add_domain(self) -> None:
        domain = normalize_domain(self.entry_domain.get())
        if not domain:
            messagebox.showerror("Invalid website", "Enter a website domain such as youtube.com.")
            return
        domains = self.config_manager.data.setdefault("blocked_domains", [])
        if domain not in domains:
            domains.append(domain)
            self.config_manager.save()
        self.entry_domain.delete(0, "end")
        self._refresh_domains_list()

    def _remove_domain(self, domain: str) -> None:
        self.config_manager.data["blocked_domains"] = [d for d in self.config_manager.data.get("blocked_domains", []) if d != domain]
        self.config_manager.save()
        self._refresh_domains_list()

    # -------------------------------------------------------------
    # TAB 4: SCHEDULES
    # -------------------------------------------------------------
    def _build_schedules_tab(self) -> None:
        intro_box = ctk.CTkFrame(self.tab_sched, corner_radius=8, fg_color="#eeebfa")
        intro_box.pack(fill="x", padx=12, pady=10)

        lbl = ctk.CTkLabel(intro_box, text="Designated Focus Hours (Recurring Schedules)", font=ctk.CTkFont(size=14, weight="bold"), text_color="#5147a8")
        lbl.pack(anchor="w")

        lbl_desc = ctk.CTkLabel(
            intro_box,
            text="FocusShield automatically locks in during designated times on specified days.",
            font=ctk.CTkFont(size=11),
            text_color="#525c73",
        )
        lbl_desc.pack(anchor="w")

        # New Schedule Form
        form_frame = ctk.CTkFrame(self.tab_sched, corner_radius=10, fg_color="#ffffff")
        form_frame.pack(fill="x", padx=12, pady=(0, 10))

        lbl_new = ctk.CTkLabel(form_frame, text="Add New Focus Schedule:", font=ctk.CTkFont(size=12, weight="bold"), text_color="#20263a")
        lbl_new.pack(anchor="w", pady=(0, 6))

        inputs_row = ctk.CTkFrame(form_frame, fg_color="transparent")
        inputs_row.pack(fill="x", pady=(0, 8))

        self.entry_sched_name = ctk.CTkEntry(inputs_row, placeholder_text="Schedule Name (e.g. Study Time)", width=220)
        self.entry_sched_name.pack(side="left", padx=(0, 8))

        lbl_from = ctk.CTkLabel(inputs_row, text="From (HH:MM):", font=ctk.CTkFont(size=11), text_color="#525c73")
        lbl_from.pack(side="left", padx=(0, 4))
        self.entry_sched_start = ctk.CTkEntry(inputs_row, width=70)
        self.entry_sched_start.insert(0, "09:00")
        self.entry_sched_start.pack(side="left", padx=(0, 8))

        lbl_to = ctk.CTkLabel(inputs_row, text="To (HH:MM):", font=ctk.CTkFont(size=11), text_color="#525c73")
        lbl_to.pack(side="left", padx=(0, 4))
        self.entry_sched_end = ctk.CTkEntry(inputs_row, width=70)
        self.entry_sched_end.insert(0, "12:00")
        self.entry_sched_end.pack(side="left", padx=(0, 14))

        btn_add_sched = ctk.CTkButton(inputs_row, text="+ Save Schedule", width=140, fg_color="#5550b4", hover_color="#49439e", command=self._add_schedule)
        btn_add_sched.pack(side="left")

        # Days of week checkboxes
        days_row = ctk.CTkFrame(form_frame, fg_color="transparent")
        days_row.pack(fill="x")

        self.day_vars = []
        days_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        for idx, d_name in enumerate(days_labels):
            var = ctk.BooleanVar(value=(idx < 5))  # Default Mon-Fri
            self.day_vars.append(var)
            cb = ctk.CTkCheckBox(days_row, text=d_name, variable=var, width=65, font=ctk.CTkFont(size=11))
            cb.pack(side="left", padx=4)

        # Existing Schedules List
        list_lbl = ctk.CTkLabel(self.tab_sched, text="Active Schedules:", font=ctk.CTkFont(size=13, weight="bold"), text_color="#20263a")
        list_lbl.pack(anchor="w", padx=16, pady=(6, 4))

        self.sched_scroll = ctk.CTkScrollableFrame(self.tab_sched, height=220, corner_radius=10, fg_color="#ffffff")
        self.sched_scroll.pack(fill="both", expand=True, padx=12, pady=(0, 10))

        self._refresh_schedules_list()

    def _refresh_schedules_list(self) -> None:
        for widget in self.sched_scroll.winfo_children():
            widget.destroy()

        schedules = self.config_manager.data.get("schedules", [])
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

        for idx, sched in enumerate(schedules):
            row = ctk.CTkFrame(self.sched_scroll, fg_color="#edf0f7", corner_radius=8)
            row.pack(fill="x", padx=4, pady=4)

            # Details
            left = ctk.CTkFrame(row, fg_color="transparent")
            left.pack(side="left", padx=12, pady=10)

            name_lbl = ctk.CTkLabel(left, text=sched.get("name", "Focus Window"), font=ctk.CTkFont(size=13, weight="bold"), text_color="#20263a")
            name_lbl.pack(anchor="w")

            active_days_str = ", ".join([day_names[d] for d in sched.get("days", []) if 0 <= d < 7])
            time_str = f"{sched.get('start_time', '00:00')} - {sched.get('end_time', '00:00')} ({active_days_str})"
            time_lbl = ctk.CTkLabel(left, text=time_str, font=ctk.CTkFont(size=11), text_color="#525c73")
            time_lbl.pack(anchor="w")

            # Actions on right
            right = ctk.CTkFrame(row, fg_color="transparent")
            right.pack(side="right", padx=12)

            # Switch toggle for enabled
            enabled_var = ctk.BooleanVar(value=sched.get("enabled", True))
            sw = ctk.CTkSwitch(
                right,
                text="Enabled",
                variable=enabled_var,
                font=ctk.CTkFont(size=11),
                command=lambda i=idx, v=enabled_var: self._toggle_schedule(i, v.get()),
            )
            sw.pack(side="left", padx=(0, 12))

            btn_del = ctk.CTkButton(
                right,
                text="Delete",
                width=75,
                height=26,
                font=ctk.CTkFont(size=11),
                fg_color="#ae3445",
                hover_color="#922539",
                command=lambda i=idx: self._delete_schedule(i),
            )
            btn_del.pack(side="left")

    def _toggle_schedule(self, index: int, is_enabled: bool) -> None:
        schedules = self.config_manager.data.get("schedules", [])
        if 0 <= index < len(schedules):
            schedules[index]["enabled"] = is_enabled
            self.config_manager.save()

    def _delete_schedule(self, index: int) -> None:
        schedules = self.config_manager.data.get("schedules", [])
        if 0 <= index < len(schedules):
            del schedules[index]
            self.config_manager.save()
            self._refresh_schedules_list()

    def _add_schedule(self) -> None:
        name = self.entry_sched_name.get().strip() or "Scheduled Focus"
        start_t = self.entry_sched_start.get().strip()
        end_t = self.entry_sched_end.get().strip()
        selected_days = [idx for idx, v in enumerate(self.day_vars) if v.get()]

        if not selected_days:
            messagebox.showwarning("No Days Selected", "Please select at least one day of the week.")
            return

        new_sched = {
            "id": f"sched_{int(time.time())}",
            "name": name,
            "enabled": True,
            "days": selected_days,
            "start_time": start_t,
            "end_time": end_t,
        }
        self.config_manager.data.setdefault("schedules", []).append(new_sched)
        self.config_manager.save()
        self.entry_sched_name.delete(0, "end")
        self._refresh_schedules_list()

    # -------------------------------------------------------------
    # TAB 5: SETTINGS
    # -------------------------------------------------------------
    def _build_settings_tab(self) -> None:
        s_card = ctk.CTkFrame(self.tab_settings, corner_radius=10, fg_color="#ffffff")
        s_card.pack(fill="x", padx=12, pady=12)

        lbl = ctk.CTkLabel(s_card, text="Protection & Behavior Preferences", font=ctk.CTkFont(size=14, weight="bold"), text_color="#5147a8")
        lbl.pack(anchor="w", pady=(0, 14))

        settings = self.config_manager.data.get("settings", {})

        # Auto minimize switch
        self.var_minimize = ctk.BooleanVar(value=settings.get("auto_minimize_blocked_apps", True))
        sw1 = ctk.CTkSwitch(
            s_card,
            text="Auto-minimize distracting applications when launched",
            variable=self.var_minimize,
            command=self._save_settings,
        )
        sw1.pack(anchor="w", pady=6)

        # Overlay notification switch
        self.var_overlay = ctk.BooleanVar(value=settings.get("show_reminder_overlay", True))
        sw2 = ctk.CTkSwitch(
            s_card,
            text="Display floating HUD reminder banner on screen when a distraction is blocked",
            variable=self.var_overlay,
            command=self._save_settings,
        )
        sw2.pack(anchor="w", pady=6)

        # Sound switch
        self.var_sound = ctk.BooleanVar(value=settings.get("play_warning_sound", True))
        sw3 = ctk.CTkSwitch(
            s_card,
            text="Play subtle audio cue when a distraction is intercepted",
            variable=self.var_sound,
            command=self._save_settings,
        )
        sw3.pack(anchor="w", pady=6)

        # Strict Mode switch
        self.var_strict = ctk.BooleanVar(value=settings.get("strict_mode", False))
        sw4 = ctk.CTkSwitch(
            s_card,
            text="Strict Mode: Lock focus sessions (disables manual pause until countdown expires)",
            variable=self.var_strict,
            command=self._save_settings,
        )
        sw4.pack(anchor="w", pady=6)

        btn_test_overlay = ctk.CTkButton(
            s_card,
            text="Test HUD Reminder Overlay",
            width=200,
            fg_color="#2b2d49",
            hover_color="#3d4068",
            command=lambda: self.show_block_notification("app", "TestDistraction.exe", "This is how FocusShield gently redirects you back to your goals!"),
        )
        btn_test_overlay.pack(anchor="w", pady=(16, 0))

    def _save_settings(self) -> None:
        self.config_manager.data["settings"]["auto_minimize_blocked_apps"] = self.var_minimize.get()
        self.config_manager.data["settings"]["show_reminder_overlay"] = self.var_overlay.get()
        self.config_manager.data["settings"]["play_warning_sound"] = self.var_sound.get()
        self.config_manager.data["settings"]["strict_mode"] = self.var_strict.get()
        self.config_manager.save()

    # -------------------------------------------------------------
    # TIMER TICK & STATE HANDLING
    # -------------------------------------------------------------
    def _tick_timer(self) -> None:
        status = self.scheduler.get_status()
        is_active = status["active"]
        rem_sec = status["time_remaining_sec"]
        reason = status["reason"]

        if is_active:
            self.status_badge.configure(text="FOCUS ACTIVE", fg_color="#d5f3e7", text_color="#075a41")
            self.btn_main_toggle.configure(text="Stop Manual Session" if status["manual_active"] else "Scheduled Focus", fg_color="#ae3445", hover_color="#922539")
            self.sub_status_label.configure(text=reason, text_color="#5147a8")
            self.lbl_active_goal.configure(text=status.get("goal") or "Deep Focus")

            if rem_sec > 0:
                m = rem_sec // 60
                s = rem_sec % 60
                self.lbl_big_timer.configure(text=f"{m:02d}:{s:02d}")
            else:
                self.lbl_big_timer.configure(text="Scheduled Active")
        else:
            self.status_badge.configure(text="IDLE", fg_color="#e5e9f4", text_color="#374057")
            self.btn_main_toggle.configure(text="Start Focus Now", fg_color="#5550b4", hover_color="#49439e")
            self.sub_status_label.configure(text="Blocker ready", text_color="#525c73")
            self.lbl_active_goal.configure(text="Ready for Deep Work")
            self.lbl_big_timer.configure(text="--:--")

        if hasattr(self, "website_blocker"):
            error = self.website_blocker.error
            self.website_status.configure(text=("Website blocking error: " + error) if error else "Website blocking is ready.", text_color="#ae3445" if error else "#525c73")
        self.after(1000, self._tick_timer)

    def _on_main_toggle_clicked(self) -> None:
        status = self.scheduler.get_status()
        if status["active"]:
            if not status["manual_active"]:
                messagebox.showinfo("Scheduled Focus", "Edit or delete the active calendar block, or change your recurring schedule, to end scheduled focus.")
                return
            # Check strict mode
            if self.config_manager.data.get("settings", {}).get("strict_mode", False) and status["manual_active"]:
                messagebox.showwarning("Strict Mode Active", "Strict mode is enabled! Stay disciplined until the timer completes.")
                return
            self.scheduler.stop_manual_session()
        else:
            self.scheduler.start_manual_session(25, "Deep Focus")

    def _start_custom_session(self, minutes: int) -> None:
        goal = self.entry_goal.get().strip() or "Deep Work"
        self.scheduler.start_manual_session(minutes, goal)

    def _on_start_custom_clicked(self) -> None:
        try:
            mins = int(self.entry_custom_mins.get().strip())
        except ValueError:
            mins = 25
        goal = self.entry_goal.get().strip() or "Deep Work"
        self.scheduler.start_manual_session(mins, goal)

    # -------------------------------------------------------------
    # BLOCK EVENT & LOGGING
    # -------------------------------------------------------------
    def show_block_notification(self, block_type: str, target: str, message: str) -> None:
        self.after(0, self._handle_block_event_main_thread, block_type, target, message)

    def _handle_block_event_main_thread(self, block_type: str, target: str, message: str) -> None:
        self.blocked_count_session += 1
        if hasattr(self, "card_blocks_stat"):
            self.card_blocks_stat.configure(text=str(self.blocked_count_session))

        # Audio cue
        if self.config_manager.data.get("settings", {}).get("play_warning_sound", True):
            try:
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            except Exception:
                pass

        # Visual overlay
        if self.config_manager.data.get("settings", {}).get("show_reminder_overlay", True):
            header = f"Distraction Blocked: {target}"
            self.overlay.show(header, message)

        # Log item
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.event_logs.insert(0, {
            "time": timestamp,
            "type": block_type,
            "target": target,
            "message": message,
        })
        if len(self.event_logs) > 50:
            self.event_logs.pop()

        self._render_log_feed()

    def _render_log_feed(self) -> None:
        for widget in self.feed_scroll.winfo_children():
            widget.destroy()

        if not self.event_logs:
            lbl = ctk.CTkLabel(
                self.feed_scroll,
                text="No distractions intercepted yet. All focus shields green!",
                font=ctk.CTkFont(size=12),
                text_color="#525c73",
            )
            lbl.pack(pady=20)
            return

        for item in self.event_logs[:20]:
            row = ctk.CTkFrame(self.feed_scroll, fg_color="#edf0f7", corner_radius=6)
            row.pack(fill="x", padx=4, pady=2)

            icon = "🛑" if item["type"] == "app" else "🌐"
            lbl_time = ctk.CTkLabel(row, text=f"[{item['time']}]", font=ctk.CTkFont(size=10, family="Consolas"), text_color="#525c73")
            lbl_time.pack(side="left", padx=8)

            lbl_txt = ctk.CTkLabel(row, text=f"{icon} {item['message']}", font=ctk.CTkFont(size=11), text_color="#20263a")
            lbl_txt.pack(side="left", padx=4)
