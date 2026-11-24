// Check a building: the example house's summer week is shown straight away (computed at build
// time); any change runs the Python model in a worker.
import { call, warm } from './engine.js';
import { HOME } from './data/home.js';
import { EXAMPLES } from './data/examples.js';
import { clock, el, hours, level, litres, saveChoice } from './common.js';
import { chart, ticks } from './charts.js';
import { createHouse, hasWebGL } from './house3d.js';
import { planView } from './planview.js';

const $ = (id) => document.getElementById(id);
const MAX_BYTES = 2 * 1024 * 1024;
const RISK_HOURS = 4;
let mine = null; // a loaded plan (parsed JSON), never inserted into the page as markup
let current = null; // { building, result }
let selected = null;
let house = null;

function setError(msg) {
  $('error').textContent = msg || '';
  $('error').hidden = !msg;
}

function choice() {
  const num = (v) => (v === '' ? undefined : Number(v));
  const plan = $('building').value === 'mine' ? mine : $('building').value;
  return {
    plan,
    settings: { season: $('season').value, roof: $('roof').value, scenario: $('scenario').value, setpoint: num($('setpoint').value), tmv_set: num($('tmv').value) },
  };
}

// ---------- Loading a plan ----------
async function readFile(file) {
  setError('');
  if (file.size > MAX_BYTES) return setError('The plan is larger than 2 MB.');
  let data;
  try {
    data = JSON.parse(await file.text());
  } catch {
    return setError('That file isn’t valid JSON.');
  }
  if (!data || typeof data !== 'object' || Array.isArray(data)) return setError('The plan must be a JSON object.');
  mine = data;
  const opt = $('building').querySelector('option[value=mine]');
  opt.disabled = false;
  $('building').value = 'mine';
  $('loaded').textContent = `Loaded ${file.name}. Checking it…`;
  run();
}
$('file').addEventListener('change', (e) => e.target.files[0] && readFile(e.target.files[0]));
const drop = $('drop');
drop.addEventListener('dragover', (e) => { e.preventDefault(); drop.classList.add('over'); });
drop.addEventListener('dragleave', () => drop.classList.remove('over'));
drop.addEventListener('drop', (e) => {
  e.preventDefault();
  drop.classList.remove('over');
  if (e.dataTransfer.files[0]) readFile(e.dataTransfer.files[0]);
});
$('template').addEventListener('click', () => {
  const blob = new Blob([JSON.stringify(EXAMPLES.house, null, 1)], { type: 'application/json' });
  const a = el('a', { href: URL.createObjectURL(blob), download: 'tepidline-plan.json' });
  document.body.append(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
});

// ---------- Running ----------
$('panel').addEventListener('submit', (e) => { e.preventDefault(); run(); });
for (const id of ['building', 'season', 'roof', 'scenario', 'setpoint', 'tmv']) $(id).addEventListener('change', () => run());
$('panel').addEventListener('focusin', () => warm(), { once: true });

let running = 0;
async function run() {
  const c = choice();
  if (!c.plan) return;
  const ticket = ++running;
  setError('');
  $('run').disabled = true;
  $('progress').hidden = false;
  $('status').textContent = 'Starting Python and following the water… (the first run loads the model, a few seconds)';
  const t0 = performance.now();
  try {
    const out = await call({ op: 'check', plan: c.plan, settings: c.settings });
    if (ticket !== running) return;
    $('status').textContent = `Followed a week of water in ${((performance.now() - t0) / 1000).toFixed(1)} s.`;
    if ($('building').value === 'mine') $('loaded').textContent = `Your plan: ${out.building.name}.`;
    show(out, c);
  } catch (err) {
    if (ticket !== running) return;
    $('status').textContent = '';
    setError(err.message);
  } finally {
    if (ticket === running) {
      $('run').disabled = false;
      $('progress').hidden = true;
    }
  }
}

// ---------- Results ----------
function show(out, c) {
  current = out;
  const { building: B, result: R } = out;
  const rows = Object.entries(R.outlets).sort((a, b) => b[1].risky_litres * b[1].weight - a[1].risky_litres * a[1].weight);
  const risky = rows.filter(([, o]) => o.risky_litres >= 0.05);
  const away = c.settings.scenario === 'away';
  $('headline').textContent = risky.length
    ? `${risky.length} of ${rows.length} outlets deliver water that had sat warm for over ${RISK_HOURS} hours${away ? ' on the first day back' : ' in a week'}. The worst is the ${B.outlets[rows[0][0]].name.toLowerCase()}: ${litres(rows[0][1].risky_litres)}.`
    : `No outlet delivers water that had sat warm for over ${RISK_HOURS} hours${away ? ' on the first day back' : ' in this week'}.`;
  selected = rows[0][0];
  if (house) house.set(B, R);
  $('to-fix').hidden = false;
  saveChoice({ plan: c.plan, settings: { season: c.settings.season, roof: c.settings.roof, scenario: c.settings.scenario } });
  drawPlan();
  outletTable(rows);
  pipeTable();
  firstDraw();
  document.body.dataset.checked = String(Number(document.body.dataset.checked || 0) + 1);
}

function drawPlan() {
  planView($('plan'), current.building, current.result, { selected, onSelect: select });
}

function select(oid) {
  selected = oid;
  for (const tr of $('outlets').children) tr.setAttribute('aria-selected', String(tr.dataset.outlet === oid));
  drawPlan();
  firstDraw();
}

function outletTable(rows) {
  const B = current.building;
  $('outlets').replaceChildren(...rows.map(([oid, o]) => {
    const lv = level(o.risky_litres);
    const tr = el('tr', { 'data-outlet': oid, 'aria-selected': String(oid === selected), tabindex: '0' },
      el('td', { text: B.outlets[oid].name }),
      el('td', { class: 'num', text: litres(o.risky_litres) }),
      el('td', { class: 'num hide-sm', text: hours(o.worst_hours) }),
      el('td', { class: 'num hide-sm', text: B.outlets[oid].hot ? litres(o.wait_litres) : '–' }),
      el('td', {}, el('span', { class: `pill ${lv.id}`, text: lv.label })));
    tr.addEventListener('click', () => select(oid));
    tr.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); select(oid); } });
    return tr;
  }));
}

const PLACES = { roof: 'roof space', wall: 'a wall', underfloor: 'under the floor', outdoor: 'outside', indoor: 'indoors' };
function pipeTable() {
  const { building: B, result: R } = current;
  const top = Object.entries(R.pipes).sort((a, b) => b[1].band_hours - a[1].band_hours).slice(0, 8);
  $('pipes').replaceChildren(...top.map(([pid, p]) => el('tr', {},
    el('td', { text: pid }),
    el('td', { text: `${B.pipes[pid].kind} water` }),
    el('td', { class: 'hide-sm', text: `${PLACES[B.pipes[pid].zone]}${B.pipes[pid].insulation ? ', lagged' : ''}` }),
    el('td', { class: 'num', text: `${B.pipes[pid].length} m` }),
    el('td', { class: 'num', text: hours(p.band_hours) }))));
}

function firstDraw() {
  const { building: B, result: R } = current;
  const o = R.outlets[selected];
  const name = B.outlets[selected].name;
  $('first-title').textContent = `The first water of the day: ${name.toLowerCase()}`;
  const box = $('first');
  const pts = o.first_draw;
  if (!pts || pts.length < 2) {
    box.replaceChildren(el('p', { class: 'muted small', text: `The ${name.toLowerCase()} isn't used on the day shown.` }));
    $('first-note').textContent = '';
    return;
  }
  const end = pts[pts.length - 1][0];
  const spans = [];
  let start = null;
  for (let i = 0; i < pts.length; i++) {
    const warmish = pts[i][2] >= RISK_HOURS;
    if (warmish && start === null) start = i === 0 ? 0 : pts[i - 1][0];
    if (!warmish && start !== null) { spans.push({ cls: 'cut-warm', from: start, to: pts[i][0] }); start = null; }
  }
  if (start !== null) spans.push({ cls: 'cut-warm', from: start, to: end });
  const temps = pts.map((p) => p[1]);
  const yMin = Math.floor(Math.min(15, ...temps) / 5) * 5, yMax = Math.ceil(Math.max(50, ...temps) / 5) * 5;
  chart(box, {
    x: { min: 0, max: end, ticks: ticks(0, end, 6), format: (s) => (s < 120 ? `${s} s` : `${Math.round(s / 60)} min`) },
    y: { min: yMin, max: yMax, ticks: ticks(yMin, yMax, 5), format: (v) => `${v}°` },
    xLabel: 'Since the tap was turned on',
    yLabel: '°C',
    spans,
    hlines: [{ cls: 'limit', y: 45 }, { cls: 'limit', y: 25 }],
    series: [{ kind: 'line', cls: 'line-ember', points: pts.map((p) => [p[0], p[1]]) }],
  });
  const warmMax = Math.max(...pts.map((p) => p[2]));
  $('first-note').textContent = warmMax >= RISK_HOURS
    ? `The first water out had spent up to ${hours(warmMax)} warm in the pipes. Dashed lines: 25 and 45 °C.`
    : `None of this water had sat warm for ${RISK_HOURS} hours. Dashed lines: 25 and 45 °C.`;
}

// ---------- 3D ----------
if (hasWebGL()) {
  const stage = $('stage');
  let shown = -1;
  house = createHouse(stage, {
    onTime(s, roof) {
      const step = Math.floor(s / 300);
      if (step === shown) return;
      shown = step;
      $('time').value = String(Math.round(s / 30) * 30);
      $('clock').textContent = clock(s);
      $('badge').replaceChildren('Roof space ', el('strong', { text: `${roof.toFixed(0)} °C` }));
    },
  });
  const setPlay = (on) => {
    const now = house.play(on);
    $('play').textContent = now ? 'Pause' : 'Play the day';
    $('play').setAttribute('aria-pressed', String(now));
  };
  setPlay(house.playing);
  $('play').addEventListener('click', () => setPlay(!house.playing));
  $('time').addEventListener('input', () => { setPlay(false); house.setTime(Number($('time').value)); });
} else {
  $('fallback').hidden = false;
  $('play').disabled = true;
  $('time').disabled = true;
}

show(HOME, { plan: 'house', settings: { season: 'summer', roof: 'dark', scenario: 'normal' } });
$('status').textContent = 'Showing the example house in summer. Change anything to run the model.';
document.body.dataset.ready = '1';
