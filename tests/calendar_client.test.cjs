// Run with: node --test tests/calendar_client.test.cjs
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');

function client(storage) {
  const cards = [];
  const slots = [];
  const context = vm.createContext({
    localStorage: storage,
    window: { addEventListener() {} },
    document: {
      addEventListener() {},
      getElementById() { return { value: '' }; },
      createElement() { return { style: {}, dataset: {}, addEventListener() {}, appendChild() {} }; },
      querySelector(selector) {
        slots.push(selector);
        return { appendChild(card) { cards.push(card); } };
      },
    },
  });
  for (const file of ['liquid.js', 'app.js']) {
    vm.runInContext(fs.readFileSync(path.join(root, 'static', file), 'utf8'), context);
  }
  return { context, cards, slots, run: code => vm.runInContext(code, context) };
}

test('calendar initializes and settings remain usable when storage is denied', () => {
  const app = client({
    getItem() { throw new Error('Storage denied'); },
    setItem() { throw new Error('Storage denied'); },
  });
  assert.equal(app.run('offset'), 0);
  assert.equal(app.run('reminders.length'), 0);
  assert.equal(app.run('airlocks().length'), 0);
  assert.doesNotThrow(() => app.run("remember('chronotype', 1)"));
});

test('corrupt JSON and settings with the wrong type fall back safely', () => {
  for (const value of ['{broken', 'null', 'false', '"wrong"', '42']) {
    const app = client({ getItem() { return value; }, setItem() {} });
    assert.equal(app.run('reminders.length'), 0);
    assert.equal(app.run('airlocks().length'), 0);
  }
});

test('focus blocks are clipped to each visible day without changing saved timestamps', () => {
  const app = client({ getItem() { return null; }, setItem() {} });
  app.run(`
    productiveBlocks = [{id:'overnight', name:'Study', category:'Study',
      start:'2026-11-20T06:00:00', end:'2026-11-21T09:00:00'}];
    renderEventsOnGrid([new Date(2026,10,20), new Date(2026,10,21)]);
  `);
  assert.equal(app.cards.length, 2);
  assert.match(app.slots[0], /2026-11-20.*data-hour="7"/);
  assert.match(app.slots[1], /2026-11-21.*data-hour="7"/);
  assert.equal(app.cards[0].style.height, `${15 * 52 - 4}px`);
  assert.equal(app.cards[1].style.height, `${2 * 52 - 4}px`);
  assert.equal(app.run('productiveBlocks[0].start'), '2026-11-20T06:00:00');
});

test('focus blocks outside the visible days and hours do not render', () => {
  const app = client({ getItem() { return null; }, setItem() {} });
  app.run(`
    productiveBlocks = [
      {start:'2026-11-20T01:00:00', end:'2026-11-20T07:00:00'},
      {start:'2026-11-20T22:00:00', end:'2026-11-21T06:00:00'},
      {start:'2026-11-22T09:00:00', end:'2026-11-22T10:00:00'}
    ];
    renderEventsOnGrid([new Date(2026,10,20)]);
  `);
  assert.equal(app.cards.length, 0);
});
