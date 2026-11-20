# Pianissimo

Plan quiet work time in the calendar and automatically block distractions during your focus blocks. Pianissimo combines the calendar and the Windows desktop blocker in one running app.

## Start

1. Open `dist/Pianissimo` and double-click `Pianissimo.exe`. Approve the Windows administrator prompt to enable website blocking. Keep the entire folder together; Python is included and does not need to be installed.
2. The desktop window runs the blocker and opens the calendar in your browser. Keep the desktop window open during focus blocks.
3. Add blocks on the calendar. The blocker starts at each block's start time and stops at its end, unless another block, recurring schedule, or manual session is active. Manage allowed apps and blocked websites in the desktop window.

Website blocking applies to the exact domain and its `www` form across Windows through the hosts file. It does not cover other subdomains, existing connections, IP addresses, VPNs or applications that bypass the system hosts file. Pianissimo removes its own entries when focus ends or it exits; a watchdog also attempts cleanup if it crashes. After a shutdown or forced termination of both processes, restarting Pianissimo will clear stale entries. Website blocking errors appear in the app.

The packaged app stores calendar blocks and settings in `%LOCALAPPDATA%\Pianissimo`. Data from the source version and the original apps is separate and is not automatically imported. Google Calendar is read from its secret iCal URL; keep that URL private. Calendar export creates an iCal file to import separately; it does not write back to Google Calendar.

To run from source instead, install Python 3 and run `py -3 -m pip install -r requirements.txt`, then run `run.bat` as administrator. To rebuild the Windows package, install PyInstaller and run `py -3 -m PyInstaller --noconfirm Pianissimo.spec`.

Calendar feeds expand recurring events with time zones, exclusions, and moved occurrences. Review the imported commitments before using auto-fill; the calendar timeline currently displays 07:00–22:00. Calendar events are commitments, not automatically protected focus blocks. Only the blocks you create in Pianissimo activate the blocker.
