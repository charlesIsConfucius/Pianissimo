# Google Calendar import — implementation prompt for GPT Sol

Author: GPT Sol. The requested Gemini Flash author could not run because its quota was exhausted.

Improve Google Calendar import in the existing Pianissimo app. Inspect `app.py`, `static/app.js`, `static/index.html`, `static/liquid.js`, and the tests before editing. Keep the Python HTTP server and plain JavaScript architecture. Preserve the new neutral UI, appearance preferences, and Windows blocker integration.

Current behavior: the user pastes a secret Google Calendar iCal URL; `/api/sync` accepts `{url, week}` and returns expanded occurrences. `parse_ics` already uses `recurring_ical_events` with timezone support, exclusions, and overrides. The client has request versioning. Audit these implementations rather than replacing them with a second integration. Regression tests cover DST, exclusions, overrides, all-day end dates, and cancellations.

Deliver a reliable, understandable read-only connection flow:

- Explain where to find the secret iCal URL and make clear that importing commitments does not activate distraction blocking or write back to Google.
- Show connecting, success with last sync time and event count, empty, and actionable failure states. Add retry, refresh, and disconnect. Preserve the last successful events on temporary failures; mark stale data clearly. Disconnect must invalidate in-flight requests and remove the saved URL and imported events without deleting focus blocks.
- Keep the URL private: mask it after connection, avoid logging it or exposing it in errors, and preserve the existing HTTPS/Google host restriction. Audit redirect validation and response size/time limits. Explain local credential storage honestly.
- Fetch the visible date range when navigating. Define a bounded range API compatible with the existing week payload, since day/week/month views are planned. Keep recurrence, DST, all-day exclusive end dates, overnight events, and adjacent-day boundaries correct. Deduplicate occurrences using stable identity where available. Render imported text safely.
- Keep imported commitments separate from user-created focus blocks. Auto-fill must respect every imported occupied interval, including all-day and multi-day commitments. Never treat a failed or unfinished import as a confirmed free calendar.
- Update documentation only to match verified behavior. Do not introduce OAuth, cloud services, two-way sync, or dependencies unless necessary for this scope.

Verify recurrence exceptions/overrides, timezone and DST boundaries, all-day/multi-day events, malformed feeds, restricted URLs/redirects, failed refresh with cached events, disconnect during a pending request, navigation races, persistence, and auto-fill conflicts. Use synthetic feeds, never a real secret URL in fixtures. Report changes, checks, and remaining limitations. Complete this feature directly; do not spawn agents.
