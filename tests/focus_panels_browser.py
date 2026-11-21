# Optional browser regression checks: py -3 -m pip install playwright; py -3 tests/focus_panels_browser.py
from pathlib import Path
from datetime import date, datetime, timedelta, timezone
from playwright.sync_api import sync_playwright
root = Path(__file__).resolve().parents[1]
with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe', headless=True)
    page = browser.new_page(viewport={'width': 1914, 'height': 1000})
    errors = []
    sync_mode = 'success'
    pending_syncs = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    def route(req):
        path = req.request.url.split('http://pianissimo.test', 1)[1].split('?')[0]
        if path == '/api/data':
            req.fulfill(json={'blocks': [], 'config': {}})
        elif path == '/api/sync':
            if sync_mode == 'pending':
                pending_syncs.append(req)
            elif sync_mode == 'failure':
                req.fulfill(status=502, json={'error': 'Feed unavailable'})
            elif sync_mode == 'network':
                req.abort()
            else:
                week = req.request.post_data_json['week']
                now = datetime.now(timezone.utc)
                monday = date.today() - timedelta(days=date.today().weekday())
                offset = date.fromisoformat(week) - monday
                req.fulfill(json={'success': True, 'count': 1, 'events': [{
                    'summary': 'Meeting for ' + week,
                    'start': (now + offset + timedelta(minutes=10)).isoformat(),
                    'end': (now + offset + timedelta(hours=1)).isoformat(),
                }]})
        elif path == '/api/shield-status':
            req.fulfill(json={'online': False})
        elif path == '/api/focus/history':
            req.fulfill(status=503, json={'error': 'Offline'})
        elif path.startswith('/api/'):
            req.fulfill(status=404, json={})
        else:
            file = root / 'static' / (path.lstrip('/') or 'index.html')
            if file.is_file(): req.fulfill(path=str(file))
            else: req.fulfill(status=404)
    page.route('http://pianissimo.test/**', route)
    page.goto('http://pianissimo.test/')
    page.wait_for_selector('.priority-row')
    page.get_by_label('Priority 1', exact=True).fill('Finish the sonata')
    page.get_by_label('Focus on priority 1', exact=True).click()
    assert page.locator('#timerPriority').inner_text() == 'On the stand · Finish the sonata'
    page.locator('#startTimerBtn').click()
    assert page.locator('#startTimerBtn').inner_text() == 'Pause'
    assert page.locator('#timerPriority').is_visible()
    page.locator('#resetTimerBtn').click()
    page.reload()
    page.wait_for_selector('.priority-row')
    assert page.get_by_label('Priority 1', exact=True).input_value() == 'Finish the sonata'
    assert page.locator('#timerPriority').is_visible()
    page.get_by_label('Complete priority 1', exact=True).check()
    assert not page.locator('#timerPriority').is_visible()
    page.reload()
    page.wait_for_selector('.priority-row')
    assert page.get_by_label('Complete priority 1', exact=True).is_checked()
    assert page.locator('#scoreCount').inner_text() == '1 / 3'
    page.evaluate("ensureScoreDay(new Date(Date.now() + 86400000))")
    assert page.get_by_label('Priority 1', exact=True).input_value() == ''
    assert not page.get_by_label('Complete priority 1', exact=True).is_checked()
    assert page.evaluate('dailyScore.selected') is None
    page.evaluate("localStorage.setItem('pianissimo.dailyScore', '{broken'); dailyScore = loadDailyScore(); renderDailyScore()")
    assert page.get_by_label('Priority 1', exact=True).input_value() == ''
    print('PASS: persistence, selection, timer, completion, and daily rollover')
    page.evaluate('''() => {
      const now = Date.now();
      calendarFeedState = {status:'ready', week:formatDate(getMonday(new Date()))};
      gcalEvents = [
        {summary:'Expired', start:new Date(now-7200000).toISOString(), end:new Date(now-3600000).toISOString()},
        {summary:'Invalid', start:'invalid', end:'invalid'},
        {summary:'All day', all_day:true, start:new Date(now).toISOString(), end:new Date(now+86400000).toISOString()},
        {summary:'Next meeting', start:new Date(now+600000).toISOString(), end:new Date(now+3600000).toISOString()},
        {summary:'Following meeting', start:new Date(now+7200000).toISOString(), end:new Date(now+10800000).toISOString()}
      ];
      productiveBlocks = [{id:'test', name:'Current focus', start:new Date(now-600000).toISOString(), end:new Date(now+300000).toISOString()}];
      renderNextMovement();
    }''')
    assert page.locator('#movementName').inner_text() == 'Current focus'
    assert page.locator('#movementCountdown').inner_text() == 'Happening now'
    assert page.locator('#movementTimeline li').count() == 2
    page.evaluate('productiveBlocks = []; renderNextMovement()')
    assert page.locator('#movementName').inner_text() == 'Next meeting'
    page.locator('#movementAction').click()
    assert page.locator('#eventModal').is_visible()
    page.locator('#closeEventBtn').click()
    # Remove the event without rendering: clicking must refresh the stale action.
    page.evaluate('gcalEvents = []')
    page.locator('#movementAction').click()
    assert page.locator('#movementAction').inner_text() == 'Plan a focus block'
    assert page.locator('#blockModal').is_visible()
    page.locator('#cancelModalBtn').click()
    page.get_by_label('Priority 1', exact=True).fill('Practice scales')
    page.get_by_label('Focus on priority 1', exact=True).click()
    page.locator('#movementAction').click()
    assert page.locator('#modalBlockName').input_value() == 'Practice scales'
    page.locator('#cancelModalBtn').click()
    print('PASS: current/upcoming ordering, expired/invalid/all-day filtering, empty state, event and planning actions')
    # Exercise the real sync/navigation hooks, rather than injecting only event data.
    page.evaluate("syncCalendar('https://calendar.test/feed.ics')")
    this_week = page.evaluate('formatDate(currentWeekStart)')
    assert page.evaluate('calendarFeedState.week') == this_week
    assert page.locator('#movementScope').inner_text() == 'Loaded week only'
    assert 'Other weeks are not checked' in page.locator('#movementSource').inner_text()
    page.locator('#nextWeekBtn').click()
    page.wait_for_function("calendarFeedState.status === 'ready' && calendarFeedState.week === formatDate(currentWeekStart)")
    next_week = page.evaluate('formatDate(currentWeekStart)')
    assert next_week != this_week
    assert page.evaluate('calendarFeedState.week') == next_week
    assert page.locator('#movementName').inner_text() == 'Meeting for ' + next_week
    assert 'nearer commitments may be missing' in page.locator('#movementSource').inner_text()
    # Check loading, then an older success arriving after the newest failure.
    sync_mode = 'pending'
    with page.expect_request('**/api/sync'):
        page.evaluate("void syncCalendar('https://calendar.test/old.ics')")
    page.wait_for_function("calendarFeedState.status === 'loading'")
    assert page.locator('#movementScope').inner_text() == 'Calendar loading'
    assert page.locator('#movementName').inner_text() == 'Checking calendar events…'
    sync_mode = 'failure'
    page.locator('#prevWeekBtn').click()
    page.wait_for_function("calendarFeedState.status === 'error'")
    assert page.locator('#movementScope').inner_text() == 'Calendar unavailable'
    assert page.locator('#movementName').inner_text() == 'Calendar events are unavailable.'
    assert page.evaluate('gcalEvents.length') == 0
    pending_syncs.pop().fulfill(json={'success': True, 'count': 1, 'events': [{
        'summary': 'Stale response', 'start': '2099-01-01T09:00:00', 'end': '2099-01-01T10:00:00',
    }]})
    page.wait_for_load_state('networkidle')
    assert page.evaluate('calendarFeedState.status') == 'error'
    assert page.evaluate('gcalEvents.length') == 0
    sync_mode = 'network'
    page.evaluate("syncCalendar('https://calendar.test/feed.ics')")
    assert page.locator('#movementScope').inner_text() == 'Calendar unavailable'
    # Saved focus remains usable but is explicitly incomplete during feed failure.
    page.evaluate('''productiveBlocks = [{id:'saved', name:'Saved focus',
        start:new Date(Date.now()+3600000).toISOString(), end:new Date(Date.now()+7200000).toISOString()}];
        renderNextMovement()''')
    assert page.locator('#movementName').inner_text() == 'Saved focus'
    assert page.locator('#movementScope').inner_text() == 'Calendar unavailable'
    assert 'Only saved focus blocks' in page.locator('#movementSource').inner_text()
    sync_mode = 'success'
    page.evaluate("syncCalendar('https://calendar.test/feed.ics')")
    assert page.locator('#movementScope').inner_text() == 'Loaded week only'
    page.locator('.workspace-tools > summary').click()
    page.locator('#loadSampleBtn').click()
    page.locator('.workspace-tools > summary').click()
    assert page.locator('#movementScope').inner_text() == 'Sample calendar'
    print('PASS: week navigation, scope labels, loading, HTTP/network failure, stale response rejection, recovery, samples')
    for width, height in [(1914,1000),(1280,860),(1024,768),(800,700),(640,460),(390,844)]:
        page.set_viewport_size({'width':width,'height':height})
        for hidden in [False, True]:
            if page.evaluate("document.querySelector('.app-layout').classList.contains('calendar-hidden')") != hidden:
                page.locator('#calendarToggle').click()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), (width, height, hidden, 'overflow')
            for selector in ['.score-card','.movement-card']:
                assert page.locator(selector).bounding_box()['width'] > 180, (width, hidden, selector)
            if hidden:
                assert page.locator('#weeklyFocus').is_visible()
        print(f'PASS: layout {width}x{height}, calendar open and hidden; weekly focus preserved')
    assert not errors, errors
    print('PASS: no browser JavaScript errors')
    browser.close()

