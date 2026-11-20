"""
Productivity Time-Blocker Backend
Serves the calendar and expands iCalendar feeds for the displayed week.
"""

import http.server
import socketserver
import urllib.request
import urllib.parse
import json
import recurring_ical_events
from icalendar import Calendar
import os
import tempfile
from app_paths import DATA_ROOT, RESOURCE_ROOT
from datetime import datetime, date, time, timedelta, timezone
from typing import List, Dict, Any

PORT = 5000
BASE_DIR = DATA_ROOT
DATA_FILE = os.path.join(BASE_DIR, "productivity_blocks.json")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
STATIC_DIR = os.path.join(RESOURCE_ROOT, "static")

def parse_ics(ics_text: str, week_start: date) -> List[Dict[str, Any]]:
    """Expand recurring events with their time zones, exceptions and overrides."""
    calendar = Calendar.from_ical(ics_text)
    # Include adjacent days so UTC and calendar-local week boundaries are covered.
    events = []
    occurrences = recurring_ical_events.of(calendar).between(
        week_start - timedelta(days=1), week_start + timedelta(days=8)
    )
    for event in occurrences:
        if str(event.get("STATUS", "")).upper() == "CANCELLED":
            continue
        start = event.decoded("DTSTART")
        end = event.decoded("DTEND")
        all_day = not isinstance(start, datetime)
        if all_day:
            start = datetime.combine(start, time.min)
            end = datetime.combine(end, time.min)
        events.append({
            "summary": str(event.get("SUMMARY", "Busy")),
            "description": str(event.get("DESCRIPTION", "")),
            "location": str(event.get("LOCATION", "")),
            "start": start.isoformat(), "end": end.isoformat(), "all_day": all_day,
        })
    return events


def load_json(filepath: str, default: Any) -> Any:
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default
    return default

def save_json(filepath: str, data: Any):
    fd, temporary = tempfile.mkstemp(dir=os.path.dirname(filepath), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(temporary, filepath)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)

class CalendarHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/shield-status":
            scheduler = self.server.scheduler
            blocker = getattr(self.server, "website_blocker", None)
            self._send_json({"online": True, **scheduler.get_status(), "website_error": blocker.error if blocker else "Website blocker unavailable"} if scheduler else {"online": False})
        elif parsed.path == "/api/focus/history":
            scheduler = self.server.scheduler
            if scheduler is None:
                self._send_json({"error": "Open Pianissimo to view focus history."}, status=503)
                return
            self._send_json({"days": scheduler.focus_history.daily_totals()})
        elif parsed.path == "/api/data":
            config = load_json(CONFIG_FILE, {"calendar_url": ""})
            blocks = load_json(DATA_FILE, [])
            self._send_json({"config": config, "blocks": blocks})
        else:
            super().do_GET()

    def do_POST(self):
        origin = self.headers.get("Origin")
        if origin and origin not in (f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}"):
            self._send_json({"error": "Origin not allowed"}, status=403)
            return
        parsed = urllib.parse.urlparse(self.path)
        try:
            content_len = int(self.headers.get("Content-Length", 0))
            if content_len < 0 or content_len > 2 * 1024 * 1024:
                self._send_json({"error": "Request body is too large or invalid."}, status=400)
                return
            body = self.rfile.read(content_len).decode("utf-8") if content_len > 0 else "{}"
            payload = json.loads(body)
            if not isinstance(payload, dict):
                raise ValueError("Expected an object")
        except (ValueError, UnicodeError):
            self._send_json({"error": "Send a valid JSON object."}, status=400)
            return

        if parsed.path == "/api/sync":
            if not isinstance(payload.get("url", ""), str):
                self._send_json({"error": "Calendar URL must be text."}, status=400)
                return
            url = payload.get("url", "").strip()
            if not url:
                config = load_json(CONFIG_FILE, {})
                url = config.get("calendar_url", "")
            
            if not url:
                self._send_json({"error": "No calendar URL provided."}, status=400)
                return

            try:
                # Handle webcal:// prefix
                if url.startswith("webcal://"):
                    url = "https://" + url[9:]
                parsed_url = urllib.parse.urlparse(url)
                if parsed_url.scheme != "https" or parsed_url.hostname != "calendar.google.com":
                    self._send_json({"error": "Use a Google Calendar HTTPS iCal URL."}, status=400)
                    return
                
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "ProductivityBlocker/1.0"}
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    ics_data = resp.read().decode("utf-8", errors="ignore")
                
                week_start = date.fromisoformat(payload.get("week", date.today().isoformat()))
                events = parse_ics(ics_data, week_start)
                
                # Save config
                save_json(CONFIG_FILE, {"calendar_url": url, "last_synced": datetime.now().isoformat()})
                
                self._send_json({"success": True, "count": len(events), "events": events})
            except Exception as e:
                self._send_json({"error": "Could not read this Google Calendar feed."}, status=500)

        elif parsed.path == "/api/blocks":
            # Save or update productive blocks
            blocks = payload.get("blocks")
            try:
                if not isinstance(blocks, list):
                    raise ValueError("Blocks must be a list.")
                ids = set()
                for block in blocks:
                    if not isinstance(block, dict):
                        raise ValueError("Each block must be an object.")
                    block_id = block.get("id")
                    if not isinstance(block_id, str) or not block_id or block_id in ids:
                        raise ValueError("Each block needs a unique text ID.")
                    ids.add(block_id)
                    for field in ("name", "category", "physics"):
                        if field in block and not isinstance(block[field], str):
                            raise ValueError(f"Block {field} must be text.")
                    start = datetime.fromisoformat(block["start"].replace("Z", "+00:00"))
                    end = datetime.fromisoformat(block["end"].replace("Z", "+00:00"))
                    if end <= start:
                        raise ValueError("Block end must be after its start.")
            except (ValueError, TypeError, KeyError, AttributeError) as error:
                self._send_json({"error": "Invalid focus blocks. Check IDs, dates and times."}, status=400)
                return
            try:
                save_json(DATA_FILE, blocks)
            except OSError:
                self._send_json({"error": "Could not save focus blocks. Please try again."}, status=500)
                return
            self._send_json({"success": True, "blocks": blocks})
        else:
            self._send_json({"error": "Not Found"}, status=404)

    def _send_json(self, data: Any, status: int = 200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

if __name__ == "__main__":
    os.makedirs(STATIC_DIR, exist_ok=True)
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("127.0.0.1", PORT), CalendarHandler) as httpd:
        httpd.scheduler = None
        print(f"Productivity Calendar Server running at http://localhost:{PORT}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server.")
