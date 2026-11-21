const minute = 60000;
const byId = id => document.getElementById(id);
const readSetting = (key, fallback) => {
  try {
    const value = JSON.parse(localStorage.getItem('liquid.' + key));
    if (Array.isArray(fallback)) return Array.isArray(value) ? value : fallback;
    if (fallback && typeof fallback === 'object') return value && typeof value === 'object' && !Array.isArray(value) ? value : fallback;
    return typeof value === typeof fallback ? value : fallback;
  } catch {
    return fallback;
  }
};
const remember = (key, value) => {
  try { localStorage.setItem('liquid.' + key, JSON.stringify(value)); }
  catch { /* Keep the current session usable when storage is unavailable. */ }
};
let forecastDate;
const overruns = readSetting('overruns', {});
let reminders = readSetting('reminders', []);
let offset = readSetting('chronotype', 0);
const eventKey = event => JSON.stringify([event.start, event.end, event.summary]);
const effectiveEnd = event => overruns[eventKey(event)] || event.end;
const windows = [[9,11.5,'Peak cognitive power','rgba(83,181,125,.17)'],[13.5,15,'Post-lunch slump','rgba(221,164,76,.18)'],[16.5,18.5,'Second wind','rgba(109,150,216,.18)']];

function paintEnergy(slot, hour) {
  for (const [start,end,label,color] of windows) {
    const a = Math.max(0,start+offset-hour), b = Math.min(1,end+offset-hour);
    if (a >= b) continue;
    slot.style.setProperty('--energy-band', 'linear-gradient(to bottom, transparent '+a*100+'%, '+color+' '+a*100+'% '+b*100+'%, transparent '+b*100+'%)');
  }
}

function fixedEvents() {
  return [...gcalEvents, ...productiveBlocks.filter(b => b.physics === 'concrete')];
}

function airlocks(includeFlexible = true) {
  const fixed = fixedEvents();
  const occupied = includeFlexible ? [...gcalEvents, ...productiveBlocks] : fixed;
  const busy = occupied.map(e => ({start:+new Date(e.start), end:+new Date(effectiveEnd(e))})).sort((a,b)=>a.start-b.start);
  const meetings = fixed.filter(e=>!e.all_day).sort((a,b)=>new Date(a.start)-new Date(b.start));
  const result = [];
  let previous = 0, streak = 0;
  for (const meeting of meetings) {
    const start = +new Date(meeting.start), end = +new Date(effectiveEnd(meeting));
    streak = start-previous <= 10*minute ? streak+1 : 1;
    previous = Math.max(previous,end);
    const length = (streak >= 4 ? 15 : 5)*minute;
    // Fixed calls take precedence. Reserve recovery after the last adjacent call.
    if (meetings.some(other=>other!==meeting && +new Date(other.start)>=start && +new Date(other.start)<end+length && +new Date(effectiveEnd(other))>end)) continue;
    let recoveryStart = end;
    for (const b of [...busy, ...result].sort((a,b)=>a.start-b.start)) {
      if (b.start >= recoveryStart+length) break;
      if (b.end > recoveryStart) recoveryStart=b.end;
    }
    const cutoff=new Date(end); cutoff.setHours(END_HOUR,0,0,0);
    if (recoveryStart+length<=cutoff) result.push({start:recoveryStart,end:recoveryStart+length,storm:streak>=4});
  }
  return result;
}

function showForecast(date) {
  forecastDate = date;
  const storm = airlocks().some(a=>a.storm && formatDate(new Date(a.start))===date);
  const deep = productiveBlocks.filter(b=>formatDate(new Date(b.start))===date && ['Deep Work','Coding','Study'].includes(b.category)).length;
  byId('forecast').textContent = new Date(date+'T12:00').toLocaleDateString(undefined,{weekday:'short',month:'short',day:'numeric'})+' · '+(storm?'Thunderstorm warning · 15 min recovery':'Sunny · '+deep+' deep work block'+(deep===1?'':'s'));
  const fmt = h=>Math.floor(h+offset)+':'+(h%1?'30':'00');
  byId('windows').textContent = windows.map(([a,b,label])=>fmt(a)+'–'+fmt(b)+' '+label).join('   ·   ');
  byId('dump').value = readSetting('note.'+date,'');
  const tray = byId('tomorrow');
  tray.replaceChildren();
  for (const r of reminders.filter(r=>r.date<=date)) {
    const button = document.createElement('button');
    button.className='btn btn-secondary btn-sm';
    button.textContent='Reschedule '+r.name;
    button.onclick=()=>{
      openCreateModal(date,9);
      byId('modalBlockName').value=r.name;
      byId('modalCategory').value=r.category;
      byId('physics').value='vapor';
      byId('blockOptions').open = true;
      byId('blockModal').dataset.reminder=r.id;
    };
    tray.appendChild(button);
  }
}

async function ripple(item, statusId) {
  if (blockSavePending) return false;
  const imported = gcalEvents.includes(item);
  const start = +new Date(item.start);
  const oldEnd = +new Date(effectiveEnd(item));
  const end = oldEnd + 20 * minute;
  const limit = new Date(start).setHours(END_HOUR, 0, 0, 0);
  const walls = fixedEvents().filter(event => event !== item).map(event => ({
    start: +new Date(event.start), end: +new Date(effectiveEnd(event)),
  }));
  if (end > limit || walls.some(wall => wall.start < end && wall.end > oldEnd)) {
    showStatus(statusId, 'The extension reaches a fixed appointment or the end of the day.');
    return false;
  }

  // Calculate recovery slots with the proposed extension, then restore current state while saving.
  const originalEnd = item.end;
  const extendedEnd = new Date(end).toISOString();
  const key = eventKey(item);
  const prior = overruns[key];
  if (imported) overruns[key] = end;
  else item.end = extendedEnd;
  try {
    walls.push(...airlocks(false));
  } finally {
    if (!imported) item.end = originalEnd;
    else if (prior === undefined) delete overruns[key];
    else overruns[key] = prior;
  }
  walls.sort((a, b) => a.start - b.start);
  walls.push({ start: limit, end: limit });

  const changes = new Map();
  if (!imported) changes.set(item, { ...item, end: extendedEnd });
  const deferred = new Set();
  let cursor = end;
  const flexible = productiveBlocks
    .filter(block => block !== item && block.physics !== 'concrete' && new Date(block.end) > oldEnd && new Date(block.start) < limit)
    .sort((a, b) => new Date(a.start) - new Date(b.start));
  for (const block of flexible) {
    const duration = new Date(block.end) - new Date(block.start);
    const optional = block.physics === 'vapor';
    let at = Math.max(cursor, +new Date(block.start));
    let length = 0;
    for (const wall of walls) {
      if (wall.end <= at && wall.start < limit) continue;
      const gap = Math.min(wall.start, limit) - at;
      if (gap >= duration || (!optional && gap >= Math.min(duration, 10 * minute))) {
        length = Math.min(duration, gap);
        break;
      }
      if (optional) break;
      at = Math.max(at, wall.end);
    }
    if (!length) {
      if (optional) {
        deferred.add(block);
        continue;
      }
      showStatus(statusId, `There is no room for ${block.name} before the day ends.`);
      return false;
    }
    cursor = at + length;
    changes.set(block, { ...block, start: new Date(at).toISOString(), end: new Date(cursor).toISOString() });
  }

  if (changes.size || deferred.size) {
    const blocks = productiveBlocks.filter(block => !deferred.has(block)).map(block => changes.get(block) || block);
    if (!await commitBlocks(blocks, statusId)) return false;
  }

  if (imported) {
    overruns[key] = end;
    remember('overruns', overruns);
  }
  if (deferred.size) {
    const tomorrow = new Date(start);
    tomorrow.setDate(tomorrow.getDate() + 1);
    reminders.push(...Array.from(deferred, block => ({ ...block, date: formatDate(tomorrow) })));
    remember('reminders', reminders);
  }
  renderWeek();
  return true;
}

let breathingTimer;
function startBreathing() {
  clearInterval(breathingTimer);
  const start=Date.now();
  function tick() {
    const elapsed=Math.floor((Date.now()-start)/1000);
    if (elapsed>=60) {
      clearInterval(breathingTimer); byId('phase').textContent='Airlock complete'; byId('phase').className=''; byId('dump').focus(); return;
    }
    byId('phase').className='breathing';
    byId('phase').textContent=['Inhale','Hold','Exhale','Hold'][Math.floor(elapsed/4)%4]+' · '+(60-elapsed)+'s';
  }
  tick(); breathingTimer=setInterval(tick,250);
}

document.addEventListener('DOMContentLoaded',()=>{
  byId('chrono').value=offset;
  byId('chrono').onchange=e=>{offset=Number(e.target.value); remember('chronotype',offset); renderWeek();};
  byId('breathe').onclick=startBreathing;
  byId('dump').oninput=e=>remember('note.'+forecastDate,e.target.value);
});
