"""
Local HTTP/REST server for communicating with the FocusShield Chrome Extension.
Allows the extension to query current focus state, whitelisted domains, and blocked domains.
"""

import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from typing import Optional
from .config import ConfigManager
from .scheduler import FocusScheduler


class ExtensionRequestHandler(BaseHTTPRequestHandler):
    config_manager: ConfigManager
    scheduler: FocusScheduler

    def _set_cors_headers(self, status: int = 200, content_type: str = "application/json"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_OPTIONS(self):
        self._set_cors_headers(204)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/api/status":
            status_data = self.scheduler.get_status()
            response_payload = {
                "focus_active": status_data["active"],
                "reason": status_data["reason"],
                "time_remaining_sec": status_data["time_remaining_sec"],
                "goal": status_data["goal"],
                "chrome_mode": self.config_manager.data.get("chrome_mode", "whitelist"),
                "allowed_domains": self.config_manager.data.get("allowed_domains", []),
                "blocked_domains": self.config_manager.data.get("blocked_domains", []),
            }
            self._set_cors_headers(200)
            self.wfile.write(json.dumps(response_payload).encode("utf-8"))

        elif path == "/api/check_url":
            target_url = query.get("url", [""])[0]
            if not target_url:
                self._set_cors_headers(400)
                self.wfile.write(b'{"error": "Missing url parameter"}')
                return

            focus_active = self.scheduler.is_focus_active()
            if not focus_active:
                # If focus is not active, all URLs are allowed
                self._set_cors_headers(200)
                self.wfile.write(json.dumps({"allowed": True, "focus_active": False}).encode("utf-8"))
                return

            # Parse domain from target URL
            target_domain = urlparse(target_url).netloc
            allowed = self.config_manager.is_domain_allowed(target_domain)

            self._set_cors_headers(200)
            self.wfile.write(json.dumps({
                "allowed": allowed,
                "focus_active": True,
                "domain": target_domain,
                "mode": self.config_manager.data.get("chrome_mode", "whitelist")
            }).encode("utf-8"))

        elif path == "/api/ping":
            self._set_cors_headers(200)
            self.wfile.write(b'{"status": "ok", "app": "FocusShield"}')

        else:
            self._set_cors_headers(404)
            self.wfile.write(b'{"error": "Not Found"}')

    def log_message(self, format, *args):
        # Suppress noisy HTTP request logging in console
        pass


class LocalApiServer:
    def __init__(self, config_manager: ConfigManager, scheduler: FocusScheduler):
        self.config_manager = config_manager
        self.scheduler = scheduler
        self.server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        port = self.config_manager.data.get("settings", {}).get("server_port", 58234)
        
        # Inject dependencies into handler class
        handler_class = ExtensionRequestHandler
        handler_class.config_manager = self.config_manager
        handler_class.scheduler = self.scheduler

        try:
            self.server = HTTPServer(("127.0.0.1", port), handler_class)
            self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self._thread.start()
            print(f"[FocusShield] Local API server started on http://127.0.0.1:{port}")
        except Exception as e:
            print(f"[FocusShield] Failed to start local API server on port {port}: {e}")
            raise

    def stop(self) -> None:
        if self.server:
            self.server.shutdown()
            self.server.server_close()
