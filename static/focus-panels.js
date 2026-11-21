// Daily priorities stay in this workspace's local profile, separate from calendar data.
let dailyScore;
let nextMovementItem = null;

function loadDailyScore(now = new Date()) {
  const date = formatDate(now);
  let saved;
  try { saved = JSON.parse(readPreference('dailyScore')); } catch { /* Start fresh. */ }
  const tasks = Array.from({ length: 3 }, (_, i) => {
    const task = saved?.date === date ? saved.tasks?.[i] : null;
    return { text: typeof task?.text === 'string' ? task.text.slice(0, 120) : '', done: task?.done === true };
  });
  const selected = saved?.date === date && Number.isInteger(saved.selected)
    && tasks[saved.selected]?.text.trim() && !tasks[saved.selected].done ? saved.selected : null;
  return { date, tasks, selected };
}

function saveDailyScore() {
  savePreference('dailyScore', JSON.stringify(dailyScore));
}

function ensureScoreDay(now = new Date()) {
  if (dailyScore?.date === formatDate(now)) return false;
  dailyScore = loadDailyScore(now);
  saveDailyScore();
  renderDailyScore();
  return true;
}

function updateScoreState() {
  const selected = dailyScore.tasks[dailyScore.selected];
  const label = document.getElementById('timerPriority');
  label.hidden = !selected;
  label.textContent = selected ? `On the stand · ${selected.text}` : '';
  document.getElementById('scoreCount').textContent = `${dailyScore.tasks.filter(t => t.done && t.text.trim()).length} / 3`;
  const rows = document.querySelectorAll('.priority-row');
  rows.forEach((row, i) => {
    const task = dailyScore.tasks[i];
    row.classList.toggle('is-done', task.done);
    row.classList.toggle('is-selected', dailyScore.selected === i);
    const select = row.querySelector('.priority-select');
    select.textContent = dailyScore.selected === i ? 'On the stand' : 'Focus';
    select.setAttribute('aria-pressed', String(dailyScore.selected === i));
    select.disabled = !task.text.trim() || task.done;
    row.querySelector('input[type="checkbox"]').disabled = !task.text.trim();
  });
  document.getElementById('scoreStatus').textContent = selected
    ? 'Ready at the timer. Start when you are.' : 'Choose Focus to put a priority on the stand.';
}

function renderDailyScore() {
  const list = document.getElementById('priorityList');
  list.replaceChildren();
  dailyScore.tasks.forEach((task, i) => {
    const row = document.createElement('li');
    row.className = 'priority-row';
    const number = document.createElement('span');
    number.className = 'priority-number';
    number.textContent = `0${i + 1}`;
    number.setAttribute('aria-hidden', 'true');
    const check = document.createElement('input');
    check.type = 'checkbox';
    check.checked = task.done;
    check.setAttribute('aria-label', `Complete priority ${i + 1}`);
    const input = document.createElement('input');
    input.type = 'text';
    input.maxLength = 120;
    input.value = task.text;
    input.placeholder = ['What matters most?', 'Make space for…', 'One more small win…'][i];
    input.setAttribute('aria-label', `Priority ${i + 1}`);
    const select = document.createElement('button');
    select.type = 'button';
    select.className = 'priority-select btn-link';
    select.setAttribute('aria-label', `Focus on priority ${i + 1}`);
    input.addEventListener('input', () => {
      if (ensureScoreDay()) return;
      task.text = input.value;
      if (!task.text.trim()) {
        task.done = false;
        check.checked = false;
        if (dailyScore.selected === i) dailyScore.selected = null;
      }
      saveDailyScore();
      updateScoreState();
    });
    check.addEventListener('change', () => {
      if (ensureScoreDay()) return;
      task.done = check.checked;
      if (task.done && dailyScore.selected === i) dailyScore.selected = null;
      saveDailyScore();
      updateScoreState();
    });
    select.addEventListener('click', () => {
      if (ensureScoreDay()) return;
      dailyScore.selected = dailyScore.selected === i ? null : i;
      saveDailyScore();
      updateScoreState();
    });
    row.append(number, check, input, select);
    list.appendChild(row);
  });
  updateScoreState();
}

function upcomingMovements(now = new Date()) {
  return [
    ...(['ready', 'sample'].includes(calendarFeedState.status) ? gcalEvents : []).filter(e => !e.all_day).map(e => ({
      title: e.summary || 'Calendar event', start: +new Date(e.start),
      end: +new Date(effectiveEnd(e)), kind: 'Calendar', source: e,
    })),
    ...productiveBlocks.map(e => ({
      title: e.name || 'Focus block', start: +new Date(e.start), end: +new Date(e.end), kind: 'Focus', source: e,
    })),
  ].filter(e => Number.isFinite(e.start) && Number.isFinite(e.end) && e.end > e.start && e.end > +now)
    .sort((a, b) => a.start - b.start || a.end - b.end);
}

function movementTime(item, now = new Date()) {
  const start = new Date(item.start);
  const day = formatDate(start) === formatDate(now) ? 'Today'
    : start.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' });
  const time = value => new Date(value).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' });
  const endDay = formatDate(new Date(item.end)) === formatDate(start) ? ''
    : `${new Date(item.end).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })} `;
  return `${day} · ${time(item.start)} – ${endDay}${time(item.end)}`;
}

function renderNextMovement(now = new Date()) {
  const panel = document.getElementById('movementName');
  if (!panel) return;
  const items = upcomingMovements(now);
  nextMovementItem = items[0] || null;
  const item = nextMovementItem;
  const minutes = item ? Math.max(1, Math.ceil((item.start - now) / 60000)) : 0;
  const scope = movementScope();
  document.getElementById('movementScope').textContent = scope.label;
  document.getElementById('movementSource').textContent = scope.description;
  document.getElementById('movementCountdown').textContent = !item ? scope.label
    : item.start <= now ? 'Happening now'
    : minutes < 60 ? `In ${minutes} min` : `In ${Math.floor(minutes / 60)}h ${minutes % 60}m`;
  panel.textContent = item?.title || scope.empty;
  document.getElementById('movementTime').textContent = item ? `${item.kind} · ${movementTime(item, now)}` : 'You can still plan a focus block.';
  document.getElementById('movementAction').textContent = item ? (item.kind === 'Focus' ? 'View focus block' : 'View event') : 'Plan a focus block';
  const timeline = document.getElementById('movementTimeline');
  timeline.replaceChildren();
  items.slice(1, 3).forEach(event => {
    const li = document.createElement('li');
    const title = document.createElement('strong');
    title.textContent = event.title;
    const time = document.createElement('span');
    time.textContent = movementTime(event, now);
    li.append(title, time);
    timeline.appendChild(li);
  });
}

function movementScope() {
  const { status, week } = calendarFeedState;
  if (status === 'loading') return {
    label: 'Calendar loading', empty: 'Checking calendar events…',
    description: 'Calendar sync is in progress. Only saved focus blocks are shown until it finishes; nearer commitments may be missing.',
  };
  if (status === 'error') return {
    label: 'Calendar unavailable', empty: 'Calendar events are unavailable.',
    description: 'Calendar sync failed. Only saved focus blocks are shown; nearer commitments may be missing. Retry Sync Feed in Workspace tools.',
  };
  if (status === 'ready' || status === 'sample') {
    const start = new Date(`${week}T12:00:00`);
    const end = new Date(start);
    end.setDate(end.getDate() + 6);
    const date = d => d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
    return {
      label: status === 'sample' ? 'Sample calendar' : 'Loaded week only',
      empty: 'No loaded items ahead.',
      description: `${status === 'sample' ? 'Sample events' : 'Calendar events'}: ${date(start)} – ${date(end)}, plus saved focus blocks. Other weeks are not checked; nearer commitments may be missing.`,
    };
  }
  return {
    label: 'Focus blocks only', empty: 'No saved focus blocks ahead.',
    description: 'Calendar is not connected. Only saved focus blocks are shown; other commitments may be missing.',
  };
}

function setupFocusPanels() {
  ensureScoreDay();
  renderNextMovement();
  document.getElementById('movementAction').addEventListener('click', () => {
    // Refresh before opening so an expired or deleted event cannot be acted on.
    renderNextMovement();
    if (nextMovementItem) {
      if (nextMovementItem.kind === 'Focus') openEditModal(nextMovementItem.source);
      else openImportedEvent(nextMovementItem.source);
    } else {
      const now = new Date();
      const date = new Date(now);
      let hour = now.getHours() + 1;
      if (hour >= 22) { date.setDate(date.getDate() + 1); hour = 9; }
      openCreateModal(formatDate(date), Math.max(7, hour));
      const priority = dailyScore.tasks[dailyScore.selected];
      if (priority) document.getElementById('modalBlockName').value = priority.text;
    }
  });
  const refresh = () => { ensureScoreDay(); renderNextMovement(); };
  setInterval(refresh, 30000);
  document.addEventListener('visibilitychange', refresh);
  window.addEventListener('focus', refresh);
  window.addEventListener('storage', event => {
    if (event.key !== 'pianissimo.dailyScore') return;
    dailyScore = loadDailyScore();
    renderDailyScore();
  });
}
