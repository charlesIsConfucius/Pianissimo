(() => {
  const element = id => document.getElementById(id);
  const dialog = element('appAccessModal');
  const view = element('appAccessView');
  const refresh = element('refreshAppAccess');
  const list = element('appAccessList');
  const form = element('appRuleForm');
  const nameInput = element('appRuleName');
  const fileInput = element('browseAppFile');
  const mode = element('appAccessMode');
  const status = element('appAccessStatus');
  let state = null;
  let busy = false;

  function renderList() {
    list.replaceChildren();
    if (!state) return;

    const running = new Set(state.running);
    const allowed = state.allowed.map(name => ({ name, allowed: false }));
    const blocked = state.blocked.map(name => ({ name, allowed: true, note: running.has(name) ? 'Running' : '' }));
    const timeFormat = new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' });
    const entries = {
      allowed: [...allowed, ...state.protected.map(name => ({ name, note: 'Always allowed' }))],
      blocked,
      running: blocked.filter(app => running.has(app.name)),
      recent: state.recent.map(app => ({ name: app.name, time: app.time })),
    }[view.value];

    if (!entries.length) {
      const messages = {
        allowed: 'No apps on the allow list.',
        blocked: 'No named or running apps are blocked.',
        running: 'No running apps need to be added to the allow list.',
        recent: 'No apps blocked since the desktop app opened.',
      };
      const empty = document.createElement('li');
      empty.className = 'card-desc';
      empty.textContent = messages[view.value];
      list.appendChild(empty);
      return;
    }

    for (const entry of entries) {
      const row = document.createElement('li');
      const name = document.createElement('span');
      name.className = 'app-access-name';
      name.textContent = entry.name;
      row.appendChild(name);
      if (entry.note || entry.time) {
        const label = document.createElement(entry.time ? 'time' : 'span');
        label.className = 'card-desc';
        if (entry.time) {
          label.dateTime = entry.time;
          label.textContent = timeFormat.format(new Date(entry.time));
        } else {
          label.textContent = entry.note;
        }
        row.appendChild(label);
      }
      if (typeof entry.allowed === 'boolean') {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'btn btn-secondary btn-sm';
        button.textContent = entry.allowed ? 'Allow' : 'Block';
        button.setAttribute('aria-label', `${button.textContent} ${entry.name}`);
        button.addEventListener('click', async () => {
          if (await updateRule(entry.name, entry.allowed)) view.focus();
        });
        row.appendChild(button);
      }
      list.appendChild(row);
    }
  }

  function renderState() {
    view.querySelector('[value=allowed]').textContent = state?.mode === 'blacklist_only' ? 'Allowed apps' : 'Allowed apps (whitelist)';
    mode.textContent = state?.mode === 'strict_whitelist'
      ? 'Only listed apps and Windows essentials are allowed during focus.'
      : 'Only apps on your block list are blocked during focus.';
    mode.hidden = !state;
    list.hidden = !state;
    element('appRuleDetails').hidden = !state;
    renderList();
  }

  function setBusy(value) {
    busy = value;
    refresh.disabled = value;
    view.disabled = value || !state;
    for (const control of [...list.querySelectorAll('button'), ...form.elements]) {
      control.disabled = value;
    }
  }

  async function requestRules(options = {}) {
    const response = await fetch('/api/shield/apps', { cache: 'no-store', ...options });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'App rules are unavailable.');
    return data;
  }

  async function loadRules() {
    if (busy) return;
    setBusy(true);
    status.textContent = 'Reading app rules…';
    try {
      state = await requestRules();
      status.textContent = '';
    } catch (error) {
      state = null;
      status.textContent = error.message === 'Failed to fetch'
        ? 'Could not reach the desktop app. Open it and refresh.'
        : error.message;
    } finally {
      renderState();
      setBusy(false);
    }
  }

  async function updateRule(name, allowed) {
    if (busy) return false;
    setBusy(true);
    status.textContent = 'Saving app rule…';
    try {
      state = await requestRules({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, allowed }),
      });
      status.textContent = allowed ? 'App allowed during focus.' : 'App blocked during focus.';
      renderState();
      return true;
    } catch (error) {
      status.textContent = error.message === 'Failed to fetch' ? 'Could not reach the desktop app. Try again.' : error.message;
      return false;
    } finally {
      setBusy(false);
    }
  }

  element('manageAppsBtn').addEventListener('click', () => {
    dialog.showModal();
    loadRules();
  });
  element('closeAppAccess').addEventListener('click', () => dialog.close());
  refresh.addEventListener('click', loadRules);
  view.addEventListener('change', () => {
    status.textContent = '';
    renderList();
  });
  element('browseAppBtn').addEventListener('click', () => fileInput.click());
  fileInput.addEventListener('change', () => {
    if (fileInput.files.length) nameInput.value = fileInput.files[0].name;
    fileInput.value = '';
    nameInput.focus();
  });
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const allowed = event.submitter?.value !== 'block';
    if (await updateRule(nameInput.value.trim(), allowed)) nameInput.value = '';
    nameInput.focus();
  });
})();
