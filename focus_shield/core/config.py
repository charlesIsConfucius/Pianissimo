"""
Configuration manager for FocusShield.
Handles loading, saving, and defaults for whitelists, blacklists, and schedules.
"""

import json
import os
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
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving config: {e}")

    # App whitelist helpers
    def is_app_allowed(self, process_name: str) -> bool:
        p_lower = process_name.lower().strip()
        # System essentials are always allowed
        if p_lower in [p.lower() for p in self.data.get("system_whitelist", [])]:
            return True
        mode = self.data.get("mode", "strict_whitelist")
        if mode == "strict_whitelist":
            allowed = [p.lower() for p in self.data.get("allowed_apps", [])]
            return p_lower in allowed
        else:
            # Blacklist mode
            blocked = [p.lower() for p in self.data.get("blocked_apps", [])]
            return p_lower not in blocked

    def add_allowed_app(self, process_name: str) -> bool:
        p_lower = process_name.lower().strip()
        if not p_lower.endswith(".exe"):
            p_lower += ".exe"
        allowed = self.data.setdefault("allowed_apps", [])
        if p_lower not in [p.lower() for p in allowed]:
            allowed.append(p_lower)
            self.save()
            return True
        return False

    def remove_allowed_app(self, process_name: str) -> bool:
        p_lower = process_name.lower().strip()
        allowed = self.data.setdefault("allowed_apps", [])
        new_list = [p for p in allowed if p.lower() != p_lower]
        if len(new_list) != len(allowed):
            self.data["allowed_apps"] = new_list
            self.save()
            return True
        return False

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
