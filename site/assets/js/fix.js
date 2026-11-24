// Plan the fixes. For the examples in the usual conditions the results come from the build (every
// combination already simulated); anything else is searched live by the Python model in a worker.
import { call } from './engine.js';
import { PLANS } from './data/plans.js';
import { dollars, el, litres, loadChoice } from './common.js';
import { chart, ticks } from './charts.js';
import { planView } from './planview.js';

const $ = (id) => document.getElementById(id);
const choice = loadChoice() || { plan: 'house', settings: { season: 'summer', roof: 'dark', scenario: 'normal' } };
let res = null; // { fixes, baseline, combos, frontier }
let pick = null;
let names = {};

const isExample = typeof choice.plan === 'string';
const KEY = isExample && choice.settings.roof === 'dark' && choice.settings.scenario === 'normal' ? `${choice.plan}-${choice.settings.season}` : null;
const label = isExample ? (choice.plan === 'house' ? 'The example house' : 'The aged-care wing') : 'Your building';
$('whose').textContent = `${label}, ${choice.settings.season === 'summer' ? 'in a Sydney summer' : 'in a Sydney winter'}${choice.settings.roof === 'light' ? ' under a light roof' : ''}${choice.settings.scenario === 'away' ? ', after a week away' : ''}.${isExample && !loadChoice() ? ' Check your own building first and this page will plan for it.' : ''}`;

function setError(msg) {
  $('error').textContent = msg || '';
  $('error').hidden = !msg;
}

function start(result) {
  res = result;
  names = Object.fromEntries(res.fixes.map((f) => [f.id, f]));
  const max = Math.max(...res.frontier.map((r) => r.cost));
  $('budget').max = String(Math.ceil(max / 50) * 50 || 50);
  if (Number($('budget').value) > Number($('budget').max)) $('budget').value = $('budget').max;
  $('all').replaceChildren(...res.fixes.map((f) => fixItem(f)));
  $('tried').textContent = `${res.combos.length} combinations simulated, each for a whole week.`;
  update();
  document.body.dataset.ready = '1';
}

function fixItem(f) {
  return el('li', { class: f.habit ? 'habit' : '' },
    el('span', { text: f.title }),
    el('span', { class: 'cost', text: f.habit ? 'a habit' : dollars(f.cost) }),
    el('span', { class: 'detail', text: f.detail }));
}

function update() {
  const budget = Number($('budget').value);
  $('budget-out').textContent = dollars(budget);
  const within = res.frontier.filter((r) => r.cost <= budget + 1e-9);
  pick = within[within.length - 1];
  const base = res.baseline.score;
  const cut = base > 0 ? 1 - pick.score / base : 0;
  $('cut').textContent = base > 0 ? `${Math.round(cut * 100)}%` : '–';
  $('cut-detail').textContent = base > 0
    ? `From ${litres(base)} to ${litres(pick.score)} a week (weighted for showers), for ${dollars(pick.cost)}.`
    : 'This building has no warm water at its taps to take away.';
  $('chosen').replaceChildren(...(pick.fixes.length ? pick.fixes.map((id) => fixItem(names[id])) : [el('li', { class: 'none', text: 'Nothing within this budget helps more than doing nothing.' })]));
  drawFrontier(budget);
  taps();
  $('pair').hidden = true;
}

function drawFrontier(budget) {
  const maxCost = Math.max(...res.combos.map((r) => r.cost), 1);
  const maxScore = Math.max(...res.combos.map((r) => r.score), 1);
  const steps = [];
  for (let i = 0; i < res.frontier.length; i++) {
    const r = res.frontier[i];
    if (i) steps.push([r.cost, res.frontier[i - 1].score]);
    steps.push([r.cost, r.score]);
  }
  steps.push([maxCost, res.frontier[res.frontier.length - 1].score]);
  const yMax = Math.ceil(maxScore / 5) * 5 || 5;
  const root = chart($('frontier'), {
    x: { min: 0, max: maxCost, ticks: ticks(0, maxCost, 5), format: (v) => (v >= 1000 ? `$${(v / 1000).toFixed(v % 1000 ? 1 : 0)}k` : `$${v}`) },
    y: { min: 0, max: yMax, ticks: ticks(0, yMax, 5), format: (v) => `${v} L` },
    xLabel: 'Cost',
    yLabel: 'Warm litres a week',
    marker: { x: Math.min(budget, maxCost) },
    series: [
      { kind: 'dots', cls: 'dot-ash', r: 2.6, points: res.combos.map((r) => [r.cost, r.score]) },
      { kind: 'line', cls: 'front', points: steps },
      { kind: 'dots', cls: 'pick', r: 6, points: [[pick.cost, pick.score]] },
    ],
  });
  root.dataset.pick = pick.fixes.join(',');
}

function taps() {
  const before = res.baseline.outlets, after = pick.outlets;
  const rows = Object.keys(before).sort((a, b) => before[b] - before[a]);
  $('taps').replaceChildren(...rows.map((oid) => el('tr', {},
    el('td', { text: res.names?.[oid] || oid }),
    el('td', { class: 'num', text: litres(before[oid]) }),
    el('td', { class: 'num', text: oid in after ? litres(after[oid]) : 'removed' }))));
}

$('budget').addEventListener('input', update);

$('show-plan').addEventListener('click', async () => {
  $('show-plan').disabled = true;
  $('status').textContent = 'Starting Python and simulating the building before and after…';
  setError('');
  try {
    const settings = choice.settings;
    const [before, after] = await Promise.all([
      call({ op: 'check', plan: choice.plan, settings }),
      call({ op: 'apply', plan: choice.plan, settings, fixes: pick.fixes }),
    ]);
    planView($('plan-before'), before.building, before.result, { label: 'The building now, pipes coloured by warm hours a day' });
    planView($('plan-after'), after.building, after.result, { label: 'The building with the chosen fixes' });
    $('pair').hidden = false;
    $('status').textContent = '';
  } catch (err) {
    $('status').textContent = '';
    setError(err.message);
  } finally {
    $('show-plan').disabled = false;
  }
});

async function search() {
  $('search').disabled = true;
  $('progress').hidden = false;
  setError('');
  $('status').textContent = 'Starting Python…';
  const t0 = performance.now();
  try {
    const out = await call({ op: 'plan', plan: choice.plan, settings: choice.settings }, (f) => {
      $('progress').firstElementChild.style.width = `${Math.round(f * 100)}%`;
      $('status').textContent = `Simulating every combination of fixes: ${Math.round(f * 100)}%`;
    });
    $('status').textContent = `Done in ${Math.round((performance.now() - t0) / 1000)} s.`;
    $('search').hidden = true;
    start(out);
  } catch (err) {
    $('status').textContent = '';
    setError(err.message);
  } finally {
    $('search').disabled = false;
    $('progress').hidden = true;
  }
}
$('search').addEventListener('click', search);

if (KEY && PLANS[KEY]) {
  start(PLANS[KEY]);
} else {
  $('search').hidden = false;
  $('cut').textContent = '–';
  $('status').textContent = 'These conditions haven’t been searched yet. It simulates every combination of fixes: about a minute.';
  document.body.dataset.ready = '1';
}
