"""
Configuration manager for FocusShield.
Handles loading, saving, and defaults for whitelists, blacklists, and schedules.
"""

import json
import os
import tempfile
from threading import RLock
from typing import Dict, List, Any
from app_paths import DATA_ROOT, FROZEN

DEFAULT_CONFIG_PATH = os.path.join(DATA_ROOT, "shield_config.json") if FROZEN else os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json")

DEFAULT_SYSTEM_WHITELIST = [
    # Core Windows UI & Input
    "explorer.exe",
    "taskmgr.exe",
    "systemsettings.exe",
    "applicationframehost.exe",
    "textinputhost.exe",
    "ctfmon.exe",
    "shellexperiencehost.exe",
    "searchhost.exe",
    "dwm.exe",
    "lockapp.exe",
    "startmenuexperiencehost.exe",
    "consent.exe",
    "credentialuibroker.exe",
    "logonui.exe",
    "snipaste.exe",
    "snippingtool.exe",
    "calculator.exe",
    "calculatorapp.exe",
    # FocusShield itself
    "python.exe",
    "py.exe",
]

DEFAULT_USER_APP_WHITELIST = [
    # Development & Terminals
    "code.exe",
    "t3.exe",
    "t3 code (nightly).exe",
    "devenv.exe",
    "pycharm64.exe",
    "idea64.exe",
    "sublime_text.exe",
    "notepad.exe",
    "notepad++.exe",
    "windowsterminal.exe",
    "wt.exe",
    "powershell.exe",
    "pwsh.exe",
    "cmd.exe",
    "conhost.exe",
    "git-bash.exe",
    # Office & Documentation
    "winword.exe",
    "excel.exe",
    "powerpnt.exe",
    "onenote.exe",
    "obsidian.exe",
    "notion.exe",
    "acrobat.exe",
    "acrord32.exe",
    # Browsers (Content handled via tab blocking)
    "chrome.exe",
]

DEFAULT_ALLOWED_DOMAINS = [
    "github.com",
    "gitlab.com",
    "stackoverflow.com",
    "stackexchange.com",
    "google.com",
    "docs.google.com",
    "drive.google.com",
    "mail.google.com",
    "calendar.google.com",
    "chatgpt.com",
    "claude.ai",
    "deepseek.com",
    "gemini.google.com",
    "wikipedia.org",
    "arxiv.org",
    "notion.so",
    "python.org",
    "developer.mozilla.org",
    "w3schools.com",
    "learn.microsoft.com",
    "canvas.instructure.com",
    "blackboard.com",
]

DEFAULT_BLOCKED_DOMAINS = [
    "youtube.com",
    "reddit.com",
    "twitter.com",
    "x.com",
    "facebook.com",
    "instagram.com",
    "tiktok.com",
    "netflix.com",
    "twitch.tv",
    "hulu.com",
    "disneyplus.com",
    "primevideo.com",
    "store.steampowered.com",
    "steamcommunity.com",
    "epicgames.com",
    "roblox.com",
    "pinterest.com",
    "tumblr.com",
    "9gag.com",
    "buzzfeed.com",
    "threads.net",
    "discord.com",
]

DEFAULT_SCHEDULES = [
    {
        "id": "morning_deep_work",
        "name": "Morning Deep Work",
        "enabled": True,
        "days": [0, 1, 2, 3, 4],  # Monday = 0 ... Friday = 4
        "start_time": "09:00",
        "end_time": "12:00",
    },
    {
        "id": "afternoon_focus",
        "name": "Afternoon Sprint",
        "enabled": True,
        "days": [0, 1, 2, 3, 4],
        "start_time": "13:30",
        "end_time": "17:00",
    },
]

DEFAULT_CONFIG: Dict[str, Any] = {
    "version": "1.0.0",
    "mode": "strict_whitelist",  # "strict_whitelist" or "blacklist_only"
    "chrome_mode": "whitelist",  # "whitelist" or "blacklist"
    "system_whitelist": DEFAULT_SYSTEM_WHITELIST,
    "allowed_apps": DEFAULT_USER_APP_WHITELIST,
    "blocked_apps": ["discord.exe", "steam.exe", "spotify.exe", "epicgameslauncher.exe", "battle.net.exe"],
    "allowed_domains": DEFAULT_ALLOWED_DOMAINS,
    "blocked_domains": DEFAULT_BLOCKED_DOMAINS,
    "schedules": [],
    "settings": {
        "auto_minimize_blocked_apps": True,
        "show_reminder_overlay": True,
        "play_warning_sound": False,
        "strict_mode": False,  # If True, prevents emergency pause
        "server_port": 58234,  # Local communication port for Chrome extension
        "overlay_duration_sec": 4,
    },
}


class ConfigManager:
    def __init__(self, config_path: str = DEFAULT_CONFIG_PATH):
        self.config_path = config_path
        self.data: Dict[str, Any] = {}
        self._lock = RLock()
        self.load()

    def load(self) -> None:
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
                # Ensure all default keys exist
                for k, v in DEFAULT_CONFIG.items():
                    if k not in self.data:
                        self.data[k] = v
                return
            except Exception as e:
                print(f"Error loading config: {e}. Reverting to defaults.")
        self.data = json.loads(json.dumps(DEFAULT_CONFIG))
        self.save()

    def save(self) -> None:
        try:
            with self._lock:
                self._write_config(self.data)
        except OSError as e:
            print(f"Error saving config: {e}")

    def _write_config(self, data: Dict[str, Any]) -> None:
        directory = os.path.dirname(os.path.abspath(self.config_path))
        fd, temporary = tempfile.mkstemp(dir=directory, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                json.dump(data, file, indent=2, ensure_ascii=False)
            os.replace(temporary, self.config_path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    @staticmethod
    def normalize_app_name(process_name: str) -> str:
        if not isinstance(process_name, str):
            raise ValueError("Enter an app name such as obsidian.exe.")
        name = process_name.strip().lower()
        if not name.endswith(".exe"):
            name += ".exe"
        if (not name[:-4].strip(" .") or len(name) > 255
                or any(char in '<>:"/\\|?*' or not char.isprintable() for char in name)):
            raise ValueError("Enter an executable name such as obsidian.exe, without a folder path.")
        return name

    def app_rules(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "mode": self.data.get("mode", "strict_whitelist"),
                **{key: {name.lower() for name in self.data.get(key, [])}
                   for key in ("allowed_apps", "blocked_apps", "system_whitelist")},
            }

    def is_app_allowed(self, process_name: str) -> bool:
        return self._is_app_allowed(process_name.lower().strip(), self.app_rules())

    @staticmethod
    def _is_app_allowed(name: str, rules: Dict[str, Any]) -> bool:
        if name in rules["system_whitelist"]:
            return True
        if rules["mode"] == "strict_whitelist":
            return name in rules["allowed_apps"]
        return name not in rules["blocked_apps"]

    def app_access_status(self, running_apps: List[str]) -> Dict[str, Any]:
        rules = self.app_rules()
        running = {app.lower() for app in running_apps}
        protected = rules["system_whitelist"]
        known = (running | rules["allowed_apps"] | rules["blocked_apps"]) - protected
        blocked = {app for app in known if not self._is_app_allowed(app, rules)}
        allowed = rules["allowed_apps"] if rules["mode"] == "strict_whitelist" else running - blocked
        return {
            "mode": rules["mode"],
            "allowed": sorted(allowed - protected),
            "blocked": sorted(blocked),
            "running": sorted(running),
            "protected": sorted(protected),
        }

    def set_app_access(self, process_name: str, allowed: bool) -> bool:
        name = self.normalize_app_name(process_name)
        with self._lock:
            rules = self.app_rules()
            if name in rules["system_whitelist"]:
                if not allowed:
                    raise ValueError("Windows essentials are always allowed.")
                return False
            if rules["mode"] == "strict_whitelist":
                return self._set_app_rules(name, allowed_apps=allowed, blocked_apps=not allowed)
            return self._set_app_rules(name, blocked_apps=not allowed)

    def _set_app_rules(self, name: str, **changes: bool) -> bool:
        with self._lock:
            updates = {}
            for key, enabled in changes.items():
                apps = self.data.get(key, [])
                without_app = [app for app in apps if app.lower() != name]
                exists = len(without_app) != len(apps)
                if exists != enabled:
                    updates[key] = [*apps, name] if enabled else without_app
            if not updates:
                return False
            self._write_config({**self.data, **updates})
            self.data.update(updates)
            return True

    def add_allowed_app(self, process_name: str) -> bool:
        return self._set_app_rules(self.normalize_app_name(process_name), allowed_apps=True)

    def remove_allowed_app(self, process_name: str) -> bool:
        return self._set_app_rules(self.normalize_app_name(process_name), allowed_apps=False)

    # Chrome domain helpers
    def is_domain_allowed(self, domain: str) -> bool:
        d_lower = domain.lower().strip()
        if not d_lower:
            return True
        # Remove protocol, port and trailing slash
        if "://" in d_lower:
            d_lower = d_lower.split("://", 1)[1]
        d_lower = d_lower.split("/", 1)[0].split(":", 1)[0]

        # Always allow chrome internal pages & localhost
        if d_lower in ("localhost", "127.0.0.1", "newtab", "extensions", "settings"):
            return True

        chrome_mode = self.data.get("chrome_mode", "whitelist")
        if chrome_mode == "whitelist":
            allowed_list = self.data.get("allowed_domains", [])
            for allowed in allowed_list:
                allowed = allowed.lower().strip()
                if d_lower == allowed or d_lower.endswith("." + allowed):
                    return True
            return False
        else:
            # Blacklist mode
            blocked_list = self.data.get("blocked_domains", [])
            for blocked in blocked_list:
                blocked = blocked.lower().strip()
                if d_lower == blocked or d_lower.endswith("." + blocked):
                    return False
            return True

    def add_allowed_domain(self, domain: str) -> bool:
        d_clean = domain.lower().strip().replace("https://", "").replace("http://", "").split("/")[0]
        allowed = self.data.setdefault("allowed_domains", [])
        if d_clean and d_clean not in [x.lower() for x in allowed]:
            allowed.append(d_clean)
            self.save()
            return True
        return False

    def remove_allowed_domain(self, domain: str) -> bool:
        d_clean = domain.lower().strip().replace("https://", "").replace("http://", "").split("/")[0]
        allowed = self.data.setdefault("allowed_domains", [])
        new_list = [x for x in allowed if x.lower() != d_clean]
        if len(new_list) != len(allowed):
            self.data["allowed_domains"] = new_list
            self.save()
            return True
        return False
