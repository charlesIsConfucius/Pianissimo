// Pianissimo - Productivity Calendar & Distraction Blocker Client
let currentWeekStart = getMonday(new Date());
let gcalEvents = [];
let activeFeed = "";
let syncVersion = 0;
let productiveBlocks = [];
let editingBlockId = null;
let timerInterval = null;
let timerSeconds = 25 * 60;
let shieldPollInterval = null;
let focusHistoryDays = [];
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
    focusHistoryDays = [];
    content.hidden = true;
    status.textContent = 'Focus history is unavailable. Check your connection and try again.';
    retry.hidden = false;
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
  const topbarShieldPill = document.getElementById('topbarShieldPill');
  const topbarShieldDot = document.getElementById('topbarShieldDot');
  const topbarShieldText = document.getElementById('topbarShieldText');

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
      shieldDesc.textContent = 'Scheduled productive blocks activate distraction blocking while the Pianissimo desktop app is running.';
    }
    if (shieldOfflineAlert) shieldOfflineAlert.style.display = 'flex';
    if (shieldActiveInfo) shieldActiveInfo.style.display = 'none';

    if (topbarShieldPill) topbarShieldPill.className = 'topbar-shield-pill pill-offline';
    if (topbarShieldDot) topbarShieldDot.className = 'status-indicator-dot offline';
    if (topbarShieldText) topbarShieldText.textContent = 'Blocker: Offline';
  } else if (isActive) {
    // Active blocking state
    if (shieldDot) shieldDot.className = 'status-indicator-dot active';
    if (shieldBadge) {
      shieldBadge.textContent = 'Shield Active';
      shieldBadge.className = 'status-pill pill-active';
    }
    if (shieldDesc) {
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

    if (topbarShieldPill) topbarShieldPill.className = 'topbar-shield-pill pill-active';
    if (topbarShieldDot) topbarShieldDot.className = 'status-indicator-dot active';
    if (topbarShieldText) topbarShieldText.textContent = `Shield Active (${reason})`;
  } else {
    // Standby / Connected state
    if (shieldDot) shieldDot.className = 'status-indicator-dot standby';
    if (shieldBadge) {
      shieldBadge.textContent = 'Standby';
      shieldBadge.className = 'status-pill pill-standby';
    }
    if (shieldDesc) {
      shieldDesc.textContent = data.website_error ? `Website blocking error: ${data.website_error}` : 'Pianissimo is standing by for the next scheduled block.';
    }
    if (shieldOfflineAlert) shieldOfflineAlert.style.display = 'none';
    if (shieldActiveInfo) shieldActiveInfo.style.display = 'none';

    if (topbarShieldPill) topbarShieldPill.className = 'topbar-shield-pill pill-standby';
    if (topbarShieldDot) topbarShieldDot.className = 'status-indicator-dot standby';
    if (topbarShieldText) topbarShieldText.textContent = 'Blocker: Standby (Ready)';
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
  });

  // Auto-fill
  document.getElementById('autoFillBtn').addEventListener('click', autoFillFreeSlots);

  // Modal actions
  document.getElementById('cancelModalBtn').addEventListener('click', () => toggleModal('blockModal', false));
  document.getElementById('saveBlockBtn').addEventListener('click', saveBlockFromModal);
  document.getElementById('deleteBlockBtn').addEventListener('click', deleteCurrentBlock);

  // Export
  document.getElementById('exportIcsBtn').addEventListener('click', exportProductiveBlocksIcs);

  // Timer
  document.getElementById('startTimerBtn').addEventListener('click', toggleTimer);
  document.getElementById('resetTimerBtn').addEventListener('click', resetTimer);
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
  document.getElementById('syncStatus').textContent = 'Loaded 8 sample events!';
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

// Render the 7-day Calendar Grid
function renderWeek() {
  const grid = document.getElementById('calendarGrid');
  grid.innerHTML = '';

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
    const dayHeader = document.createElement('div');
    dayHeader.className = `day-col-header ${dStr === todayStr ? 'is-today' : ''}`;
    dayHeader.innerHTML = `<div>${dayDate.toLocaleDateString('en-US', { weekday: 'short' })}</div><div class="day-number">${dayDate.getDate()}</div>`;
    dayHeader.tabIndex = 0;
    dayHeader.onclick = () => showForecast(dStr);
    dayHeader.onkeydown = e => { if (e.key === "Enter") showForecast(dStr); };
    grid.appendChild(dayHeader);
  }

  // 2. Hour Rows
  for (let hour = START_HOUR; hour < END_HOUR; hour++) {
    // Time label on left
    const timeLabel = document.createElement('div');
    timeLabel.className = 'time-label';
    const ampm = hour >= 12 ? 'PM' : 'AM';
    const displayHour = hour % 12 === 0 ? 12 : hour % 12;
    timeLabel.textContent = `${displayHour} ${ampm}`;
    grid.appendChild(timeLabel);

    // 7 Day Cells
    for (let dayIdx = 0; dayIdx < 7; dayIdx++) {
      const slot = document.createElement('div');
      slot.className = 'time-slot';
      slot.dataset.date = formatDate(dayDates[dayIdx]);
      slot.dataset.hour = hour;
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
  for (const a of airlocks()) renderBlockCard(new Date(a.start), new Date(a.end), "Airlock", "airlock", startBreathing);
  updateStats();
}

function renderEventsOnGrid(dayDates) {
  const grid = document.getElementById('calendarGrid');

  // Render Google Calendar (Busy) Events
  gcalEvents.forEach(evt => {
    if (!evt.start || !evt.end) return;
    const st = new Date(evt.start);
    const et = new Date(effectiveEnd(evt));
    for (const day of dayDates) {
      const from = new Date(day);
      const until = new Date(day);
      from.setHours(START_HOUR, 0, 0, 0);
      until.setHours(END_HOUR, 0, 0, 0);
      if (st >= until || et <= from) continue;
      renderBlockCard(new Date(Math.max(st, from)), new Date(Math.min(et, until)),
        evt.summary, 'event-gcal', () => {
          const interval = evt.all_day ? 'All day' : st.toLocaleString() + ' - ' + et.toLocaleString();
          alert(evt.summary + '\n' + interval);
        }, "", evt.all_day ? null : evt);
    }
  });

  // Render Productive Blocks (Distraction Blocking Active during these blocks)
  productiveBlocks.forEach(blk => {
    const st = new Date(blk.start);
    const et = new Date(blk.end);
    const title = `${blk.category}: ${blk.name}`;
    for (const day of dayDates) {
      const from = new Date(day);
      const until = new Date(day);
      from.setHours(START_HOUR, 0, 0, 0);
      until.setHours(END_HOUR, 0, 0, 0);
      if (st >= until || et <= from) continue;
      renderBlockCard(
        new Date(Math.max(st, from)), new Date(Math.min(et, until)), title,
        'event-productive ' + (blk.physics || 'rubber'),
        () => { openEditModal(blk); },
        (blk.physics || 'rubber') + ' block', blk
      );
    }
  });
}

function renderBlockCard(st, et, title, cssClass, onClick, extraInfo = '', item = null) {
  const dStr = formatDate(st);
  const startHour = st.getHours() + (st.getMinutes() / 60);
  const endHour = et.getHours() + (et.getMinutes() / 60);

  // Check if within bounds
  if (endHour <= START_HOUR || startHour >= END_HOUR) return;

  // Find slot in DOM
  const targetSlot = document.querySelector(`.time-slot[data-date="${dStr}"][data-hour="${Math.floor(startHour)}"]`);
  if (!targetSlot) return;

  const topOffset = (startHour - Math.floor(startHour)) * SLOT_HEIGHT;
  const durationHours = Math.max(0.08, endHour - startHour);
  const height = durationHours * SLOT_HEIGHT - 4;

  const card = document.createElement('div');
  card.className = `event-card ${cssClass}`;
  card.style.top = `${topOffset}px`;
  card.style.height = `${height}px`;
  card.textContent = title;
  
  const timeRange = `${st.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})} - ${et.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}`;
  card.title = extraInfo ? `${title} (${timeRange})\n🛡️ ${extraInfo}` : `${title} (${timeRange})`;
  
  card.addEventListener('click', (e) => {
    e.stopPropagation();
    onClick();
  });

  if (item) {
    if (item.id) card.dataset.blockId = item.id;
    const extend = document.createElement('button');
    extend.className = 'extend'; extend.textContent = '+20m';
    extend.onclick = event => { event.stopPropagation(); ripple(item); };
    card.appendChild(extend);
  }
  targetSlot.appendChild(card);
}

// Modal Handlers
function toggleModal(id, show) {
  const modal = document.getElementById(id);
  if (show) { delete modal.dataset.reminder; modal.classList.add('active'); }
  else modal.classList.remove('active');
}

function openCreateModal(dateStr, hour) {
  editingBlockId = null;
  document.getElementById("physics").value = "rubber";
  document.getElementById('modalTitle').textContent = 'Schedule Productive Block';
  document.getElementById('modalBlockName').value = '';
  document.getElementById('modalDate').value = dateStr;
  document.getElementById('modalStartTime').value = `${String(hour).padStart(2, '0')}:00`;
  document.getElementById('modalEndTime').value = `${String(hour + 1).padStart(2, '0')}:30`;
  document.getElementById('deleteBlockBtn').style.display = 'none';
  toggleModal('blockModal', true);
}

function openEditModal(blk) {
  editingBlockId = blk.id;
  document.getElementById("physics").value = blk.physics || "rubber";
  document.getElementById('modalTitle').textContent = 'Edit Productive Block';
  document.getElementById('modalBlockName').value = blk.name;
  document.getElementById('modalCategory').value = blk.category;
  
  const st = new Date(blk.start);
  const et = new Date(blk.end);
  document.getElementById('modalDate').value = formatDate(st);
  document.getElementById('modalStartTime').value = `${String(st.getHours()).padStart(2, '0')}:${String(st.getMinutes()).padStart(2, '0')}`;
  document.getElementById('modalEndTime').value = `${String(et.getHours()).padStart(2, '0')}:${String(et.getMinutes()).padStart(2, '0')}`;
  document.getElementById('deleteBlockBtn').style.display = 'block';
  toggleModal('blockModal', true);
}

function saveBlockFromModal() {
  const name = document.getElementById('modalBlockName').value.trim() || 'Productive Focus Session';
  const category = document.getElementById('modalCategory').value;
  const dStr = document.getElementById('modalDate').value;
  const sTime = document.getElementById('modalStartTime').value;
  const eTime = document.getElementById('modalEndTime').value;

  const start = new Date(`${dStr}T${sTime}:00`);
  const end = new Date(`${dStr}T${eTime}:00`);

  if (!dStr || !sTime || !eTime || isNaN(start.getTime()) || isNaN(end.getTime()) || end <= start) {
    alert('Enter a valid date and times. End time must be after start time.');
    return;
  }

  if (airlocks().some(a => start < a.end && end > a.start)) { alert("This time is reserved for decompression."); return; }
  const physics = document.getElementById("physics").value;
  if (editingBlockId) {
    const idx = productiveBlocks.findIndex(b => b.id === editingBlockId);
    if (idx !== -1) {
      productiveBlocks[idx] = { id: editingBlockId, physics, name, category, start: start.toISOString(), end: end.toISOString() };
    }
  } else {
    productiveBlocks.push({
      id: 'blk_' + Date.now(), physics,
      name,
      category,
      start: start.toISOString(),
      end: end.toISOString()
    });
  }

  const reminder = byId('blockModal').dataset.reminder;
  if (reminder) { reminders = reminders.filter(r => r.id !== reminder); remember('reminders', reminders); }
  syncBlocksToBackend();
  toggleModal('blockModal', false);
  renderWeek();
  checkShieldStatus();
}

function deleteCurrentBlock() {
  if (!editingBlockId) return;
  productiveBlocks = productiveBlocks.filter(b => b.id !== editingBlockId);
  syncBlocksToBackend();
  toggleModal('blockModal', false);
  renderWeek();
  checkShieldStatus();
}

async function syncBlocksToBackend() {
  try {
    const response = await fetch('/api/blocks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ blocks: productiveBlocks })
    });
    if (!response.ok) throw new Error('Save failed');
  } catch (err) {
    alert('Could not save your blocks. They will not activate the blocker until saved.');
  }
}

// Auto-fill Algorithm: scans free slots and inserts productive blocks
function autoFillFreeSlots() {
  const durationMins = parseInt(document.getElementById('autoDuration').value, 10);
  const category = document.getElementById('autoCategory').value;
  let addedCount = 0;

  for (let i = 0; i < 7; i++) {
    const day = new Date(currentWeekStart);
    day.setDate(day.getDate() + i);
    const dStr = formatDate(day);

    // Consider working/study hours: 9 AM to 7 PM (19:00)
    let pointer = new Date(day);
    pointer.setHours(9, 0, 0, 0);

    const dayEnd = new Date(day);
    dayEnd.setHours(19, 0, 0, 0);

    // Get all busy blocks on this day (both gcal and existing productive)
    const busyIntervals = [];
    [...gcalEvents, ...airlocks(), ...productiveBlocks].forEach(evt => {
      const st = new Date(evt.start);
      const et = new Date(effectiveEnd(evt));
      if (st < dayEnd && et > new Date(day.getFullYear(), day.getMonth(), day.getDate(), 9)) {
        busyIntervals.push({ start: st, end: et });
      }
    });

    // Sort intervals
    busyIntervals.sort((a, b) => a.start - b.start);

    // Look for gaps of at least durationMins
    while (pointer.getTime() + durationMins * 60000 <= dayEnd.getTime()) {
      const candidateEnd = new Date(pointer.getTime() + durationMins * 60000);
      
      // Check collision with busy intervals
      const collision = busyIntervals.find(b => 
        (pointer < b.end && candidateEnd > b.start)
      );

      if (!collision) {
        // Schedule block!
        productiveBlocks.push({
          id: 'blk_' + Date.now() + '_' + Math.random().toString(36).substr(2, 4),
          name: `${category} Focus Block`,
          category: category,
          start: pointer.toISOString(),
          end: candidateEnd.toISOString()
        });
        addedCount++;
        // Move pointer forward past this block plus 15 min buffer
        pointer = new Date(candidateEnd.getTime() + 15 * 60000);
      } else {
        // Jump past collision
        pointer = new Date(collision.end.getTime());
      }
    }
  }

  if (addedCount > 0) {
    syncBlocksToBackend();
    renderWeek();
    checkShieldStatus();
    alert(`Successfully scheduled ${addedCount} productive blocks in your free time slots!\n\nDistraction blocking will automatically activate during these blocks while the Pianissimo desktop app is running.`);
  } else {
    alert('No open slots of sufficient duration found this week.');
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
  const btn = document.getElementById('startTimerBtn');
  if (timerInterval) {
    clearInterval(timerInterval);
    timerInterval = null;
    btn.textContent = 'Resume';
  } else {
    btn.textContent = 'Pause';
    timerInterval = setInterval(() => {
      if (timerSeconds > 0) {
        timerSeconds--;
        updateTimerDisplay();
      } else {
        clearInterval(timerInterval);
        timerInterval = null;
        btn.textContent = 'Start';
        alert('🎉 Focus block completed! Time for a short break.');
      }
    }, 1000);
  }
}

function resetTimer() {
  if (timerInterval) {
    clearInterval(timerInterval);
    timerInterval = null;
  }
  timerSeconds = 25 * 60;
  document.getElementById('startTimerBtn').textContent = 'Start';
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
  const applyTheme = () => {
    document.documentElement.dataset.theme = picker.value;
  };

  try {
    const savedTheme = localStorage.getItem('pianissimo.calendarTheme');
    if (['system', 'light', 'dark'].includes(savedTheme)) picker.value = savedTheme;
  } catch {
    // The preference still works for this page if browser storage is unavailable.
  }

  picker.addEventListener('change', () => {
    applyTheme();
    try {
      localStorage.setItem('pianissimo.calendarTheme', picker.value);
    } catch {
      // Leave the selected theme active for the current page.
    }
  });
  applyTheme();
  document.getElementById('newFocusBtn').addEventListener('click', () => {
    openCreateModal(formatDate(new Date()), 9);
  });
  init();
});
