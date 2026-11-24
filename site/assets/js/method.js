// How it works: the model's checks, computed at build time by tepidline/verify.py.
import { CHECKS } from './data/checks.js';
import { el } from './common.js';
import { chart, ticks } from './charts.js';

const rows = CHECKS.checks.map((c) => el('div', { class: 'check-row' },
  el('span', { class: c.pass ? 'ok' : 'no', text: c.pass ? '✓' : '✗', 'aria-label': c.pass ? 'passed' : 'failed' }),
  el('strong', { text: c.name }),
  el('span', { class: 'val', text: `${c.value} ${c.unit}` }),
  el('span', { class: 'detail', text: c.detail })));
document.getElementById('checks').replaceChildren(...rows);

const curve = CHECKS.checks.find((c) => c.curve).curve;
const end = curve.t[curve.t.length - 1];
chart(document.getElementById('cool'), {
  x: { min: 0, max: end, ticks: ticks(0, end, 6), format: (h) => `${h} h` },
  y: { min: 20, max: 60, ticks: [20, 30, 40, 50, 60], format: (v) => `${v}°` },
  xLabel: 'Hours standing',
  yLabel: '°C',
  bands: [{ cls: 'cut-warm', lo: curve.t.map((t) => [t, 25]), hi: curve.t.map((t) => [t, 45]) }],
  series: [
    { kind: 'line', cls: 'line-sky', points: curve.t.map((t, i) => [t, curve.fine[i]]) },
    { kind: 'line', cls: 'line-ember', points: curve.t.map((t, i) => [t, curve.lumped[i]]) },
  ],
});
document.body.dataset.ready = '1';
