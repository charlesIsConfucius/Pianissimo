// Pianissimo - Productivity Calendar & Distraction Blocker Client
let currentWeekStart = getMonday(new Date());
let gcalEvents = [];
let activeFeed = "";
let syncVersion = 0;
let productiveBlocks = [];
let editingBlockId = null;
let inspectedEvent = null;
let timerInterval = null;
const FOCUS_TIMER_SECONDS = 25 * 60;
let timerSeconds = FOCUS_TIMER_SECONDS;
let timerEndsAt = 0;
let shieldPollInterval = null;
let focusHistoryDays = [];
let historyAvailable = false;
let weeklyGoalHours = 0;
let blockSavePending = false;
const SHIELD_POLL_INTERVAL_MS = 3000;

const START_HOUR = 7;
const END_HOUR = 22; // 10 PM
const SLOT_HEIGHT = 52;

// Utility: get Monday of the current week
function getMonday(d) {
  const date = new Date(d);
  const day = date.getDay();
  const diff = date.getDate() - day + (day === 0 ? -6 : 1);
  date.setDate(diff);
  date.setHours(0, 0, 0, 0);
  return date;
}

function formatDate(d) {
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function readPreference(key) {
  try { return localStorage.getItem(`pianissimo.${key}`); }
  catch { return null; }
}

function savePreference(key, value) {
  try { localStorage.setItem(`pianissimo.${key}`, value); }
  catch { /* Keep changes usable for this visit. */ }
}

function showStatus(id, message = '') {
  const status = byId(id);
  status.textContent = message;
  status.hidden = !message;
}

function validStudyGoal(hours) {
  return Number.isInteger(hours * 4) && hours >= 0 && hours <= 168;
}

function studySecondsThisWeek(days, now = new Date()) {
  const monday = formatDate(getMonday(now));
  const today = formatDate(now);
  return days.reduce((total, day) => day.date >= monday && day.date <= today ? total + day.seconds : total, 0);
}

function updateStudyGoal() {
  const progress = byId('studyProgress');
  const targetSeconds = weeklyGoalHours * 3600;
  const seconds = studySecondsThisWeek(focusHistoryDays);
  byId('editStudyGoal').textContent = targetSeconds ? 'Edit goal' : 'Set goal';
  byId('studyGoalProgress').hidden = !targetSeconds || !historyAvailable;
  progress.max = targetSeconds || 1;
  progress.value = Math.min(seconds, targetSeconds);
  byId('studyElapsed').textContent = formatFocusDuration(seconds);
  byId('studyTarget').textContent = `of ${weeklyGoalHours}h`;
  const status = byId('studyGoalStatus');
  const message = !targetSeconds ? 'Set a weekly target for tracked focus.'
    : !historyAvailable ? 'Open the desktop app to see tracked focus.'
    : seconds >= targetSeconds ? 'Weekly goal reached.' : 'Tracked focus since Monday.';
  if (status.textContent !== message) status.textContent = message;
}

function setupWorkspace() {
  const toggle = byId('calendarToggle');
  function setCollapsed(collapsed) {
    byId('calendarBody').hidden = collapsed;
    byId('weekControls').hidden = collapsed;
    byId('weekRangeHeading').hidden = collapsed;
    document.querySelector('.app-layout').classList.toggle('calendar-hidden', collapsed);
    toggle.textContent = collapsed ? 'Show calendar' : 'Hide calendar';
    toggle.setAttribute('aria-expanded', String(!collapsed));
  }
  setCollapsed(readPreference('calendarHidden') === 'true');
  toggle.addEventListener('click', () => {
    const collapsed = !byId('calendarBody').hidden;
    setCollapsed(collapsed);
    savePreference('calendarHidden', collapsed);
  });

  const savedGoal = Number(readPreference('weeklyStudyHours'));
  if (validStudyGoal(savedGoal)) weeklyGoalHours = savedGoal;
  const form = byId('studyGoalForm');
  const input = byId('studyGoalHours');
  const edit = byId('editStudyGoal');
  function closeGoalEditor() {
    form.hidden = true;
    edit.hidden = false;
    edit.focus();
  }
  edit.addEventListener('click', () => {
    form.hidden = false;
    edit.hidden = true;
    input.value = weeklyGoalHours || '';
    input.focus();
  });
  byId('cancelStudyGoal').addEventListener('click', closeGoalEditor);
  form.addEventListener('submit', event => {
    event.preventDefault();
    if (!validStudyGoal(input.valueAsNumber)) return;
    weeklyGoalHours = input.valueAsNumber;
    savePreference('weeklyStudyHours', weeklyGoalHours);
    updateStudyGoal();
    closeGoalEditor();
  });
  updateStudyGoal();
}

function formatSeconds(totalSecs) {
  if (!totalSecs || totalSecs <= 0) return '00:00';
  const m = Math.floor(totalSecs / 60);
  const s = totalSecs % 60;
  if (m >= 60) {
    const h = Math.floor(m / 60);
    const remM = m % 60;
    return `${h}h ${String(remM).padStart(2, '0')}m`;
  }
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

// Initial Data Load
async function init() {
  try {
    const res = await fetch('/api/data');
    if (res.ok) {
      const data = await res.json();
      if (data.config && data.config.calendar_url) {
        document.getElementById('calendarUrl').value = data.config.calendar_url;
        // Auto sync if URL is saved
        syncCalendar(data.config.calendar_url);
      }
      if (data.blocks) {
        productiveBlocks = data.blocks;
      }
    }
  } catch (err) {
    console.warn('Backend not reachable or running in static mode, using local state.');
  }

  renderWeek();
  setupEventListeners();
  revealToday();

  // Initialize live shield status polling
  startShieldStatusPolling();
  loadFocusHistory();
  setInterval(loadFocusHistory, 60000);
}

// Actual recorded focus is supplied by the desktop backend, not the calendar timer.
async function loadFocusHistory() {
  const status = document.getElementById('focusHistoryStatus');
  const content = document.getElementById('focusHistoryContent');
  const retry = document.getElementById('focusHistoryRetry');
  try {
    const response = await fetch('/api/focus/history', { cache: 'no-store' });
    if (!response.ok) throw new Error('History unavailable');
    const data = await response.json();
    if (!data || !Array.isArray(data.days) || !data.days.every(day =>
      day && /^\d{4}-\d{2}-\d{2}$/.test(day.date) &&
      typeof day.seconds === 'number' && Number.isFinite(day.seconds) && day.seconds >= 0
    )) throw new Error('Invalid history');
    const days = data.days.slice(-7);
    historyAvailable = true;
    focusHistoryDays = days.map(({ date, seconds }) => ({ date, seconds }));
    const list = document.getElementById('focusHistoryDays');
    list.replaceChildren();
    retry.hidden = true;
    if (!days.length) {
      content.hidden = true;
      status.textContent = 'No focus history yet.';
      return;
    }
    const today = days.find(day => day.date === formatDate(new Date()));
    document.getElementById('focusHistoryToday').textContent = today ? formatFocusDuration(today.seconds) : 'No record';
    days.forEach(day => {
      const item = document.createElement('li');
      const date = document.createElement('time');
      const duration = document.createElement('strong');
      date.dateTime = day.date;
      // Parse as a local date to avoid UTC shifting the displayed day.
      const parts = day.date.split('-').map(Number);
      date.textContent = new Date(parts[0], parts[1] - 1, parts[2]).toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' });
      duration.textContent = formatFocusDuration(day.seconds);
      item.append(date, duration);
      list.appendChild(item);
    });
    status.textContent = '';
    content.hidden = false;
  } catch (err) {
    historyAvailable = false;
    focusHistoryDays = [];
    content.hidden = true;
    status.textContent = 'Focus history is unavailable. Check your connection and try again.';
    retry.hidden = false;
  } finally {
    updateStudyGoal();
  }
}

function formatFocusDuration(seconds) {
  const total = Math.floor(seconds);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const remaining = total % 60;
  return `${hours}h ${minutes}m${remaining ? ` ${remaining}s` : ''}`;
}

function downloadFocusRecap() {
  if (!focusHistoryDays.length) return;
  const canvas = document.createElement('canvas');
  canvas.width = 1000;
  canvas.height = 270 + focusHistoryDays.length * 76;
  const ctx = canvas.getContext('2d');
  if (!ctx) return;
  ctx.fillStyle = '#f5f6fb';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = '#20263a';
  ctx.font = 'bold 44px sans-serif';
  ctx.fillText('Pianissimo · Focus recap', 60, 90);
  ctx.font = '24px sans-serif';
  ctx.fillStyle = '#525c73';
  ctx.fillText('Tracked session totals · last seven days', 60, 140);
  focusHistoryDays.forEach((day, index) => {
    const y = 215 + index * 76;
    ctx.fillStyle = '#20263a';
    ctx.textAlign = 'left';
    ctx.fillText(day.date, 60, y);
    ctx.textAlign = 'right';
    ctx.fillText(formatFocusDuration(day.seconds), 940, y);
  });
  const link = document.createElement('a');
  link.download = 'pianissimo-focus-recap.png';
  link.href = canvas.toDataURL('image/png');
  link.click();
}

// Live Blocker Status Polling
async function checkShieldStatus() {
  try {
    const res = await fetch('/api/shield-status');
    if (!res.ok) {
      updateShieldUI({ online: false });
      return;
    }
    const data = await res.json();
    updateShieldUI(data);
  } catch (err) {
    updateShieldUI({ online: false });
  }
}

function startShieldStatusPolling() {
  checkShieldStatus();
  if (shieldPollInterval) clearInterval(shieldPollInterval);
  shieldPollInterval = setInterval(checkShieldStatus, SHIELD_POLL_INTERVAL_MS);
}

function updateShieldUI(data) {
  const shieldDot = document.getElementById('shieldDot');
  const shieldBadge = document.getElementById('shieldBadge');
  const shieldDesc = document.getElementById('shieldStatusDesc');
  const shieldActiveInfo = document.getElementById('shieldActiveInfo');
  const shieldActiveReason = document.getElementById('shieldActiveReason');
  const shieldTimerItem = document.getElementById('shieldTimerItem');
  const shieldTimeRemaining = document.getElementById('shieldTimeRemaining');
  const shieldOfflineAlert = document.getElementById('shieldOfflineAlert');

  const isOnline = Boolean(data && data.online);
  const isActive = Boolean(isOnline && (data.active || data.focus_active));

  if (!isOnline) {
    // Clear offline state
    if (shieldDot) shieldDot.className = 'status-indicator-dot offline';
    if (shieldBadge) {
      shieldBadge.textContent = 'Offline';
      shieldBadge.className = 'status-pill pill-offline';
    }
    if (shieldDesc) {
      shieldDesc.hidden = true;
    }
    if (shieldOfflineAlert) shieldOfflineAlert.style.display = 'flex';
    if (shieldActiveInfo) shieldActiveInfo.style.display = 'none';

  } else if (isActive) {
    // Active blocking state
    if (shieldDot) shieldDot.className = 'status-indicator-dot active';
    if (shieldBadge) {
      shieldBadge.textContent = 'Shield Active';
      shieldBadge.className = 'status-pill pill-active';
    }
    if (shieldDesc) {
      shieldDesc.hidden = false;
      shieldDesc.textContent = data.website_error ? `Website blocking failed: ${data.website_error}` : 'Focus is active. Selected apps and websites are blocked.';
    }
    if (shieldOfflineAlert) shieldOfflineAlert.style.display = 'none';
    if (shieldActiveInfo) shieldActiveInfo.style.display = 'flex';

    const reason = data.reason || data.goal || 'Productive Focus Session';
    if (shieldActiveReason) shieldActiveReason.textContent = reason;

    if (data.time_remaining_sec && data.time_remaining_sec > 0) {
      if (shieldTimerItem) shieldTimerItem.style.display = 'flex';
      if (shieldTimeRemaining) shieldTimeRemaining.textContent = formatSeconds(data.time_remaining_sec);
    } else {
      if (shieldTimerItem) shieldTimerItem.style.display = 'none';
    }

  } else {
    // Standby / Connected state
    if (shieldDot) shieldDot.className = 'status-indicator-dot standby';
    if (shieldBadge) {
      shieldBadge.textContent = 'Standby';
      shieldBadge.className = 'status-pill pill-standby';
    }
    if (shieldDesc) {
      shieldDesc.hidden = false;
      shieldDesc.textContent = data.website_error ? `Website blocking error: ${data.website_error}` : 'Pianissimo is standing by for the next scheduled block.';
    }
    if (shieldOfflineAlert) shieldOfflineAlert.style.display = 'none';
    if (shieldActiveInfo) shieldActiveInfo.style.display = 'none';

  }
}

// Setup Event Listeners
function setupEventListeners() {
  document.getElementById('focusHistoryRetry').addEventListener('click', loadFocusHistory);
  document.getElementById('focusHistoryDownload').addEventListener('click', downloadFocusRecap);
  document.getElementById('syncBtn').addEventListener('click', () => {
    const url = document.getElementById('calendarUrl').value.trim();
    if (!url) {
      alert('Please enter a Google Calendar Secret iCal URL.');
      return;
    }
    syncCalendar(url);
  });

  document.getElementById('loadSampleBtn').addEventListener('click', loadSampleEvents);
  document.getElementById('howToFindBtn').addEventListener('click', () => toggleModal('helpModal', true));
  document.getElementById('closeHelpBtn').addEventListener('click', () => toggleModal('helpModal', false));

  // Navigation
  document.getElementById('prevWeekBtn').addEventListener('click', () => {
    currentWeekStart.setDate(currentWeekStart.getDate() - 7);
    renderWeek();
    if (activeFeed) syncCalendar(activeFeed);
  });
  document.getElementById('nextWeekBtn').addEventListener('click', () => {
    currentWeekStart.setDate(currentWeekStart.getDate() + 7);
    renderWeek();
    if (activeFeed) syncCalendar(activeFeed);
  });
  document.getElementById('todayBtn').addEventListener('click', () => {
    currentWeekStart = getMonday(new Date());
    renderWeek();
    if (activeFeed) syncCalendar(activeFeed);
    revealToday();
  });

  // Auto-fill
  document.getElementById('autoFillBtn').addEventListener('click', autoFillFreeSlots);

  // Modal actions
  document.getElementById('cancelModalBtn').addEventListener('click', () => toggleModal('blockModal', false));
  document.getElementById('saveBlockBtn').addEventListener('click', saveBlockFromModal);
  document.getElementById('deleteBlockBtn').addEventListener('click', deleteCurrentBlock);
  byId('extendBlockBtn').addEventListener('click', async () => {
    const item = productiveBlocks.find(block => block.id === editingBlockId);
    if (!item || !await ripple(item, 'blockSaveStatus')) return;
    toggleModal('blockModal', false);
  });
  byId('extendEventBtn').addEventListener('click', async () => {
    if (!gcalEvents.includes(inspectedEvent) || !await ripple(inspectedEvent, 'eventActionStatus')) return;
    toggleModal('eventModal', false);
  });
  byId('closeEventBtn').addEventListener('click', () => toggleModal('eventModal', false));
  for (const id of ['blockModal', 'eventModal']) {
    byId(id).addEventListener('cancel', event => {
      if (blockSavePending) event.preventDefault();
    });
  }

  // Export
  document.getElementById('exportIcsBtn').addEventListener('click', exportProductiveBlocksIcs);

  // Timer
  document.getElementById('startTimerBtn').addEventListener('click', toggleTimer);
  document.getElementById('resetTimerBtn').addEventListener('click', resetTimer);
  byId('newFocusBtn').addEventListener('click', () => openCreateModal(forecastDate, 9));
  byId('newFocusBtn').disabled = false;
}

// Sync with Backend
async function syncCalendar(url) {
  activeFeed = url;
  const version = ++syncVersion;
  const fillButton = document.getElementById('autoFillBtn');
  fillButton.disabled = true;
  gcalEvents = [];
  renderWeek();
  const statusBadge = document.getElementById('syncStatus');
  statusBadge.textContent = 'Syncing calendar...';
  statusBadge.style.color = 'var(--info)';

  try {
    const res = await fetch('/api/sync', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, week: formatDate(currentWeekStart) })
    });
    const data = await res.json();
    if (version !== syncVersion) return;
    if (res.ok && data.success) {
      fillButton.disabled = false;
      gcalEvents = data.events;
      statusBadge.textContent = `Synced ${data.count} events!`;
      statusBadge.style.color = 'var(--success)';
      renderWeek();
    } else {
      statusBadge.textContent = data.error || 'Sync failed.';
      statusBadge.style.color = 'var(--danger)';
    }
  } catch (err) {
    if (version !== syncVersion) return;
    statusBadge.textContent = 'Sync failed. Check connection.';
    statusBadge.style.color = 'var(--danger)';
  }
}

// Sample events for immediate testing
function loadSampleEvents() {
  activeFeed = "";
  syncVersion++;
  document.getElementById("autoFillBtn").disabled = false;
  const monday = new Date(currentWeekStart);
  const sample = [];
  
  // Mon: 9:00 - 11:00 Class, 14:00 - 15:30 Meeting
  sample.push(createSampleEvent(monday, 0, 9, 0, 11, 0, 'CS 301 Lecture'));
  sample.push(createSampleEvent(monday, 0, 14, 0, 15, 30, 'Team Sync'));
  
  // Tue: 10:00 - 12:00 Lab, 15:00 - 16:00 Office Hours
  sample.push(createSampleEvent(monday, 1, 10, 0, 12, 0, 'Physics Lab'));
  sample.push(createSampleEvent(monday, 1, 15, 0, 16, 0, 'Office Hours'));

  // Wed: 9:00 - 11:00 Class, 13:00 - 14:00 Group Project
  sample.push(createSampleEvent(monday, 2, 9, 0, 11, 0, 'CS 301 Lecture'));
  sample.push(createSampleEvent(monday, 2, 13, 0, 14, 0, 'Group Project'));

  // Thu: 11:00 - 12:30 Seminar
  sample.push(createSampleEvent(monday, 3, 11, 0, 12, 30, 'Guest Seminar'));

  // Fri: 9:00 - 11:00 Class, 16:00 - 17:00 Weekly Review
  sample.push(createSampleEvent(monday, 4, 9, 0, 11, 0, 'CS 301 Lecture'));
  sample.push(createSampleEvent(monday, 4, 16, 0, 17, 0, 'Weekly Review'));

  gcalEvents = sample;
  document.getElementById('syncStatus').textContent = `Loaded ${sample.length} sample events.`;
  document.getElementById('syncStatus').style.color = 'var(--success)';
  renderWeek();
}

function createSampleEvent(baseDate, dayOffset, sh, sm, eh, em, summary) {
  const st = new Date(baseDate);
  st.setDate(st.getDate() + dayOffset);
  st.setHours(sh, sm, 0, 0);

  const et = new Date(baseDate);
  et.setDate(et.getDate() + dayOffset);
  et.setHours(eh, em, 0, 0);

  return {
    summary: summary,
    start: st.toISOString(),
    end: et.toISOString(),
    all_day: false
  };
}

function revealToday() {
  const wrapper = document.querySelector('.calendar-wrapper');
  const today = wrapper.querySelector('.day-col-header.is-today');
  if (!today || wrapper.scrollWidth <= wrapper.clientWidth) return;
  const offset = today.getBoundingClientRect().left - wrapper.getBoundingClientRect().left;
  wrapper.scrollLeft += offset - (wrapper.clientWidth - today.offsetWidth) / 2;
}

// Render the 7-day Calendar Grid
function renderWeek() {
  const grid = document.getElementById('calendarGrid');
  grid.replaceChildren();
  grid.style.setProperty('--slot-height', `${SLOT_HEIGHT}px`);

  const weekEnd = new Date(currentWeekStart);
  weekEnd.setDate(weekEnd.getDate() + 6);

  document.getElementById('weekRangeHeading').textContent = 
    `${currentWeekStart.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })} – ${weekEnd.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}`;

  const todayStr = formatDate(new Date());

  // 1. Top Header Row: corner + 7 days
  const corner = document.createElement('div');
  corner.className = 'time-col-header';
  corner.textContent = 'Time';
  grid.appendChild(corner);

  const dayDates = [];
  for (let i = 0; i < 7; i++) {
    const dayDate = new Date(currentWeekStart);
    dayDate.setDate(dayDate.getDate() + i);
    dayDates.push(dayDate);

    const dStr = formatDate(dayDate);
    const dayHeader = document.createElement('button');
    dayHeader.type = 'button';
    dayHeader.className = `day-col-header ${dStr === todayStr ? 'is-today' : ''}`;
    dayHeader.innerHTML = `<span>${dayDate.toLocaleDateString('en-US', { weekday: 'short' })}</span><span class="day-number">${dayDate.getDate()}</span>`;
    dayHeader.setAttribute('aria-label', `Daily rhythm for ${dayDate.toLocaleDateString()}`);
    if (dStr === todayStr) dayHeader.setAttribute('aria-current', 'date');
    dayHeader.onclick = () => {
      byId('rhythmDetails').open = true;
      showForecast(dStr);
    };
    grid.appendChild(dayHeader);
  }

  renderAllDayEvents(grid, dayDates);

  // 2. Hour Rows
  for (let hour = START_HOUR; hour < END_HOUR; hour++) {
    // Time label on left
    const timeLabel = document.createElement('div');
    timeLabel.className = 'time-label';
    if ((hour - START_HOUR + 1) % 3 === 0) timeLabel.dataset.measure = '';
    const ampm = hour >= 12 ? 'PM' : 'AM';
    const displayHour = hour % 12 === 0 ? 12 : hour % 12;
    timeLabel.textContent = `${displayHour} ${ampm}`;
    grid.appendChild(timeLabel);

    // 7 Day Cells
    for (let dayIdx = 0; dayIdx < 7; dayIdx++) {
      const slot = document.createElement('div');
      slot.dataset.date = formatDate(dayDates[dayIdx]);
      slot.className = 'time-slot' + (slot.dataset.date === todayStr ? ' today-col' : '');
      slot.dataset.hour = hour;
      if (timeLabel.hasAttribute('data-measure')) slot.dataset.measure = '';
      paintEnergy(slot, hour);

      slot.addEventListener('click', (e) => {
        // Only open if clicking empty slot
        if (e.target === slot) {
          openCreateModal(slot.dataset.date, hour);
        }
      });

      grid.appendChild(slot);
    }
  }

  // 3. Render Events and Productive Blocks on Top
  if (!dayDates.some(d => formatDate(d) === forecastDate)) forecastDate = dayDates.some(d => formatDate(d) === todayStr) ? todayStr : formatDate(dayDates[0]);
  showForecast(forecastDate);
  renderEventsOnGrid(dayDates);
  for (const recovery of airlocks()) {
    renderBlockCard(new Date(recovery.start), new Date(recovery.end), 'Recovery', 'airlock', () => {
      byId('rhythmDetails').open = true;
      showForecast(formatDate(new Date(recovery.start)));
      byId('breathe').focus();
      startBreathing();
    });
  }
  updateStats();
}

function openImportedEvent(event) {
  inspectedEvent = event;
  const title = event.summary || 'Busy';
  const start = new Date(event.start);
  const end = new Date(effectiveEnd(event));
  byId('eventTitle').textContent = title;
  byId('eventTime').textContent = event.all_day
    ? 'All day'
    : `${start.toLocaleString()} – ${end.toLocaleString()}`;
  byId('extendEventBtn').hidden = Boolean(event.all_day);
  showStatus('eventActionStatus');
  toggleModal('eventModal', true);
}

function renderAllDayEvents(grid, days) {
  const cells = days.map(day => {
    const tomorrow = new Date(day);
    tomorrow.setDate(day.getDate() + 1);
    return gcalEvents.filter(event => event.all_day && new Date(event.start) < tomorrow && new Date(event.end) > day);
  });
  if (!cells.some(events => events.length)) return;

  const label = document.createElement('div');
  label.className = 'all-day-label';
  label.textContent = 'All day';
  grid.appendChild(label);
  for (const events of cells) {
    const cell = document.createElement('div');
    cell.className = 'all-day-cell';
    for (const event of events) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'all-day-event';
      button.title = button.textContent = event.summary || 'Busy';
      button.onclick = () => openImportedEvent(event);
      cell.appendChild(button);
    }
    grid.appendChild(cell);
  }
}

const blockFlexibility = { rubber: 'Flexible', concrete: 'Fixed', vapor: 'Optional' };

function blockMode(block) {
  return Object.hasOwn(blockFlexibility, block.physics) ? block.physics : 'rubber';
}

function renderEventsOnGrid(dayDates) {
  const events = gcalEvents
    .filter(event => !event.all_day)
    .map(event => ({
      start: new Date(event.start),
      end: new Date(effectiveEnd(event)),
      title: event.summary || 'Busy',
      cssClass: 'event-gcal',
      open: () => openImportedEvent(event),
    }));
  for (const block of productiveBlocks) {
    const mode = blockMode(block);
    events.push({
      start: new Date(block.start),
      end: new Date(block.end),
      title: block.name || 'Focus block',
      cssClass: `event-productive ${mode}`,
      open: () => openEditModal(block),
      details: [block.category, blockFlexibility[mode]].filter(Boolean).join(' · '),
      blockId: block.id,
    });
  }

  for (const day of dayDates) {
    const from = new Date(day).setHours(START_HOUR, 0, 0, 0);
    const until = new Date(day).setHours(END_HOUR, 0, 0, 0);
    const segments = [];
    for (const event of events) {
      const start = Math.max(event.start, from);
      const end = Math.min(event.end, until);
      if (start < end) segments.push({ ...event, start, end });
    }
    segments.sort((a, b) => a.start - b.start || b.end - a.end);
    renderDaySegments(segments);
  }
}

function renderDaySegments(segments) {
  let laneEnds = [];
  let group = [];
  let groupEnd = -Infinity;
  function renderGroup() {
    for (const item of group) {
      renderBlockCard(new Date(item.start), new Date(item.end),
        item.title, item.cssClass, item.open, item.details, item.blockId, item.lane, laneEnds.length);
    }
  }
  for (const item of segments) {
    if (item.start >= groupEnd) {
      renderGroup();
      laneEnds = [];
      group = [];
    }
    const freeLane = laneEnds.findIndex(end => end <= item.start);
    item.lane = freeLane === -1 ? laneEnds.length : freeLane;
    laneEnds[item.lane] = item.end;
    group.push(item);
    groupEnd = Math.max(groupEnd, item.end);
  }
  renderGroup();
}

function renderBlockCard(start, end, title, cssClass, onClick, details = '', blockId = null, lane = 0, lanes = 1) {
  const startHour = start.getHours() + start.getMinutes() / 60 + start.getSeconds() / 3600;
  const endHour = end.getHours() + end.getMinutes() / 60 + end.getSeconds() / 3600;
  if (endHour <= START_HOUR || startHour >= END_HOUR || end <= start) return;

  const hour = Math.floor(startHour);
  const date = formatDate(start);
  const slot = document.querySelector(`.time-slot[data-date="${date}"][data-hour="${hour}"]`);
  if (!slot) return;

  const timeFormat = { hour: 'numeric', minute: '2-digit' };
  const timeRange = `${start.toLocaleTimeString([], timeFormat)} – ${end.toLocaleTimeString([], timeFormat)}`;
  const height = Math.max(4, (endHour - startHour) * SLOT_HEIGHT - 4);
  const card = document.createElement('button');
  card.type = 'button';
  card.className = `event-card ${cssClass}`;
  card.style.top = `${(startHour - hour) * SLOT_HEIGHT}px`;
  card.style.height = `${height}px`;
  card.style.left = `calc(${lane * 100 / lanes}% + 2px)`;
  card.style.right = `calc(${(lanes - lane - 1) * 100 / lanes}% + 2px)`;
  if (blockId) card.dataset.blockId = blockId;
  if (height < 34) card.dataset.compact = '';
  card.title = details ? `${title} · ${timeRange}\n${details}` : `${title} · ${timeRange}`;
  card.setAttribute('aria-label', card.title);
  card.onclick = onClick;

  const label = document.createElement('span');
  label.className = 'ev-title';
  label.textContent = title;
  const time = document.createElement('span');
  time.className = 'ev-time';
  time.textContent = timeRange;
  card.appendChild(label);
  card.appendChild(time);
  slot.appendChild(card);
}


// Modal Handlers
function toggleModal(id, show) {
  const modal = document.getElementById(id);
  if (show && !modal.open) {
    delete modal.dataset.reminder;
    modal.showModal();
  } else if (!show && !blockSavePending) {
    modal.close();
  }
}

function openCreateModal(dateStr, hour) {
  editingBlockId = null;
  byId('physics').value = 'rubber';
  byId('blockOptions').open = false;
  byId('modalTitle').textContent = 'Schedule focus';
  byId('modalBlockName').value = '';
  byId('modalCategory').selectedIndex = 0;
  byId('modalDate').value = dateStr;
  byId('modalEndDate').value = '';
  byId('modalStartTime').value = `${String(hour).padStart(2, '0')}:00`;
  byId('modalEndTime').value = `${String(hour + 1).padStart(2, '0')}:30`;
  byId('deleteBlockBtn').hidden = true;
  byId('extendBlockBtn').hidden = true;
  showStatus('blockSaveStatus');
  toggleModal('blockModal', true);
}

function openEditModal(block) {
  editingBlockId = block.id;
  const mode = blockMode(block);
  const start = new Date(block.start);
  const end = new Date(block.end);
  const startDate = formatDate(start);
  const endDate = formatDate(end);
  const timeInput = date => `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
  byId('physics').value = mode;
  byId('blockOptions').open = mode !== 'rubber' || startDate !== endDate;
  byId('modalTitle').textContent = 'Edit focus block';
  byId('modalBlockName').value = block.name || '';
  byId('modalCategory').value = block.category || '';
  if (byId('modalCategory').selectedIndex === -1) byId('modalCategory').selectedIndex = 0;
  byId('modalDate').value = startDate;
  byId('modalEndDate').value = endDate === startDate ? '' : endDate;
  byId('modalStartTime').value = timeInput(start);
  byId('modalEndTime').value = timeInput(end);
  byId('deleteBlockBtn').hidden = false;
  byId('extendBlockBtn').hidden = false;
  showStatus('blockSaveStatus');
  toggleModal('blockModal', true);
}

async function saveBlockFromModal() {
  if (blockSavePending) return;
  const date = byId('modalDate').value;
  const endDate = byId('modalEndDate').value || date;
  const start = new Date(`${date}T${byId('modalStartTime').value}`);
  const end = new Date(`${endDate}T${byId('modalEndTime').value}`);
  if (!(end > start)) {
    showStatus('blockSaveStatus', 'Choose a valid end time after the start. For overnight blocks, set the end date in Scheduling options.');
    return;
  }
  if (airlocks().some(a => start < a.end && end > a.start)) {
    showStatus('blockSaveStatus', 'This time is reserved for recovery. Choose another time.');
    return;
  }
  const block = {
    id: editingBlockId || crypto.randomUUID(),
    name: byId('modalBlockName').value.trim() || 'Focus block',
    category: byId('modalCategory').value,
    physics: byId('physics').value,
    start: start.toISOString(),
    end: end.toISOString(),
  };
  const blocks = editingBlockId
    ? productiveBlocks.map(existing => existing.id === editingBlockId ? { ...existing, ...block } : existing)
    : [...productiveBlocks, block];
  if (!await commitBlocks(blocks, 'blockSaveStatus')) return;

  const reminder = byId('blockModal').dataset.reminder;
  if (reminder) { reminders = reminders.filter(r => r.id !== reminder); remember('reminders', reminders); }
  toggleModal('blockModal', false);
  renderWeek();
}

async function deleteCurrentBlock() {
  if (blockSavePending || !editingBlockId) return;
  const blocks = productiveBlocks.filter(block => block.id !== editingBlockId);
  if (!await commitBlocks(blocks, 'blockSaveStatus')) return;
  toggleModal('blockModal', false);
  renderWeek();
}

async function commitBlocks(blocks, statusId) {
  if (blockSavePending) return false;
  blockSavePending = true;
  showStatus(statusId, 'Saving…');
  try {
    const response = await fetch('/api/blocks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ blocks }),
    });
    if (!response.ok) throw new Error('Save failed');
    productiveBlocks = blocks;
    showStatus(statusId);
    checkShieldStatus();
    return true;
  } catch (err) {
    showStatus(statusId, 'Could not save focus blocks. Try again.');
    return false;
  } finally {
    blockSavePending = false;
  }
}

// Auto-fill Algorithm: scans free slots and inserts productive blocks
async function autoFillFreeSlots() {
  if (blockSavePending) return;
  const durationMins = parseInt(document.getElementById('autoDuration').value, 10);
  const category = document.getElementById('autoCategory').value;
  const additions = [];
  const occupied = [...gcalEvents, ...airlocks(), ...productiveBlocks].map(event => ({
    start: new Date(event.start), end: new Date(effectiveEnd(event)),
  })).sort((a, b) => a.start - b.start);

  for (let i = 0; i < 7; i++) {
    const day = new Date(currentWeekStart);
    day.setDate(day.getDate() + i);

    // Consider working/study hours: 9 AM to 7 PM (19:00)
    let pointer = new Date(day);
    pointer.setHours(9, 0, 0, 0);

    const dayEnd = new Date(day);
    dayEnd.setHours(19, 0, 0, 0);

    // Get all busy blocks on this day (both gcal and existing productive)
    const busyIntervals = occupied.filter(interval => interval.start < dayEnd && interval.end > pointer);

    // Look for gaps of at least durationMins
    while (pointer.getTime() + durationMins * 60000 <= dayEnd.getTime()) {
      const candidateEnd = new Date(pointer.getTime() + durationMins * 60000);
      
      // Check collision with busy intervals
      const collision = busyIntervals.find(b => 
        (pointer < b.end && candidateEnd > b.start)
      );

      if (!collision) {
        // Schedule block!
        additions.push({
          id: crypto.randomUUID(),
          name: `${category} Focus Block`,
          category: category,
          start: pointer.toISOString(),
          end: candidateEnd.toISOString()
        });
        // Move pointer forward past this block plus 15 min buffer
        pointer = new Date(candidateEnd.getTime() + 15 * 60000);
      } else {
        // Jump past collision
        pointer = new Date(collision.end.getTime());
      }
    }
  }

  if (additions.length) {
    if (!await commitBlocks([...productiveBlocks, ...additions], 'autoFillStatus')) return;
    renderWeek();
    showStatus('autoFillStatus', `Scheduled ${additions.length} focus blocks.`);
  } else {
    showStatus('autoFillStatus', 'No open slots fit the selected duration this week.');
  }
}

// Update Stats
function updateStats() {
  let busyHours = 0;
  let productiveHours = 0;

  const wStart = new Date(currentWeekStart);
  const wEnd = new Date(currentWeekStart);
  wEnd.setDate(wEnd.getDate() + 7);

  gcalEvents.forEach(evt => {
    const st = new Date(evt.start);
    const et = new Date(effectiveEnd(evt));
    if (st >= wStart && et <= wEnd) {
      busyHours += (et - st) / (1000 * 60 * 60);
    }
  });

  productiveBlocks.forEach(blk => {
    const st = new Date(blk.start);
    const et = new Date(blk.end);
    if (st >= wStart && et <= wEnd) {
      productiveHours += (et - st) / (1000 * 60 * 60);
    }
  });

  document.getElementById('statBusy').textContent = `${busyHours.toFixed(1)}h`;
  document.getElementById('statProductive').textContent = `${productiveHours.toFixed(1)}h`;
}

// Export Productive Blocks to .ics
function exportProductiveBlocksIcs() {
  if (productiveBlocks.length === 0) {
    alert('No productive blocks scheduled to export.');
    return;
  }

  let ics = "BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//Pianissimo//EN\n";
  productiveBlocks.forEach(b => {
    const st = new Date(b.start).toISOString().replace(/[-:]/g, '').split('.')[0] + 'Z';
    const et = new Date(b.end).toISOString().replace(/[-:]/g, '').split('.')[0] + 'Z';
    ics += `BEGIN:VEVENT\nSUMMARY:[Productive] ${b.category}: ${b.name}\nDTSTART:${st}\nDTEND:${et}\nDESCRIPTION:Pianissimo productive focus block (distraction blocking enabled)\nSTATUS:CONFIRMED\nEND:VEVENT\n`;
  });
  ics += "END:VCALENDAR";

  const blob = new Blob([ics], { type: 'text/calendar;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'pianissimo-productive-blocks.ics';
  a.click();
  URL.revokeObjectURL(url);
}

// Focus Timer
function toggleTimer() {
  const button = byId('startTimerBtn');
  if (timerInterval) {
    tickTimer();
    if (!timerInterval) return;
    clearInterval(timerInterval);
    timerInterval = null;
    button.textContent = 'Resume';
    return;
  }

  if (!timerSeconds) timerSeconds = FOCUS_TIMER_SECONDS;
  timerEndsAt = Date.now() + timerSeconds * 1000;
  showStatus('timerStatus');
  updateTimerDisplay();
  button.textContent = 'Pause';
  timerInterval = setInterval(tickTimer, 250);
}

function tickTimer() {
  const secondsLeft = Math.max(0, Math.ceil((timerEndsAt - Date.now()) / 1000));
  if (secondsLeft !== timerSeconds) {
    timerSeconds = secondsLeft;
    updateTimerDisplay();
  }
  if (secondsLeft) return;
  clearInterval(timerInterval);
  timerInterval = null;
  byId('startTimerBtn').textContent = 'Start';
  showStatus('timerStatus', 'Session complete. Time for a short break.');
}

function resetTimer() {
  if (timerInterval) {
    clearInterval(timerInterval);
    timerInterval = null;
  }
  timerSeconds = FOCUS_TIMER_SECONDS;
  document.getElementById('startTimerBtn').textContent = 'Start';
  showStatus('timerStatus');
  updateTimerDisplay();
}

function updateTimerDisplay() {
  const m = String(Math.floor(timerSeconds / 60)).padStart(2, '0');
  const s = String(timerSeconds % 60).padStart(2, '0');
  document.getElementById('timerDisplay').textContent = `${m}:${s}`;
}

// Boot
window.addEventListener('DOMContentLoaded', () => {
  const picker = document.getElementById('calendarTheme');
  picker.value = document.documentElement.dataset.theme;
  picker.addEventListener('change', () => {
    document.documentElement.dataset.theme = picker.value;
    savePreference('calendarTheme', picker.value);
  });
  setupWorkspace();
  init();
});
