// Shared colours, formats and the hand-off between pages.

// Water temperature to colour: cold blue, near-white at 25 °C, amber through the warm band,
// pink-red at 45 and deep red for hot water.
const TEMP_RAMP = [
  [10, [40, 96, 170]], [20, [94, 150, 205]], [25, [214, 222, 224]], [30, [255, 196, 102]],
  [38, [255, 140, 60]], [45, [232, 80, 110]], [55, [192, 57, 43]], [65, [139, 30, 30]],
];
function ramp(stops, v) {
  if (v <= stops[0][0]) return stops[0][1];
  for (let i = 1; i < stops.length; i++) {
    if (v <= stops[i][0]) {
      const [a, ca] = stops[i - 1];
      const [b, cb] = stops[i];
      const f = (v - a) / (b - a);
      return ca.map((x, k) => Math.round(x + (cb[k] - x) * f));
    }
  }
  return stops[stops.length - 1][1];
}
export const tempRGB = (c) => ramp(TEMP_RAMP, c);

// Warm hours a day to colour, for the plan view.
const WARM_RAMP = [[0, [43, 63, 69]], [2, [107, 90, 58]], [5, [255, 169, 77]], [10, [255, 95, 95]]];
export const warmRGB = (h) => ramp(WARM_RAMP, h);
export const css = ([r, g, b]) => `rgb(${r}, ${g}, ${b})`;

export function level(litres) {
  if (litres < 0.05) return { id: 'low', label: 'None' };
  if (litres < 2) return { id: 'mid', label: 'Some' };
  return { id: 'high', label: 'High' };
}

export const litres = (l) => (l < 10 ? `${l.toFixed(1)} L` : `${Math.round(l)} L`);
export const hours = (h) => (h < 10 ? `${h.toFixed(1)} h` : `${Math.round(h)} h`);
export const dollars = (d) => `$${Math.round(d).toLocaleString('en-AU')}`;
export function clock(seconds) {
  const m = Math.round(((seconds % 86400) + 86400) % 86400 / 60);
  const h = Math.floor(m / 60) % 24, mm = m % 60;
  const h12 = ((h + 11) % 12) + 1;
  return `${h12}:${String(mm).padStart(2, '0')} ${h < 12 ? 'am' : 'pm'}`;
}

export const SEASONS = { summer: 'Summer', winter: 'Winter' };

// The check page leaves its choices for the fix page (this tab only).
const KEY = 'tepidline-choice';
const MAX_PLAN = 1_000_000;
export function saveChoice(choice) {
  try {
    const s = JSON.stringify(choice);
    if (s.length < MAX_PLAN) sessionStorage.setItem(KEY, s);
  } catch {
    /* storage may be off: the fix page then starts from the example house */
  }
}
export function loadChoice() {
  try {
    const raw = sessionStorage.getItem(KEY);
    if (!raw || raw.length > MAX_PLAN) return null;
    const c = JSON.parse(raw);
    if (!c || typeof c !== 'object') return null;
    const ok = (typeof c.plan === 'string' && ['house', 'care'].includes(c.plan)) || (c.plan && typeof c.plan === 'object');
    const s = c.settings;
    if (!ok || !s || !['summer', 'winter'].includes(s.season) || !['dark', 'light'].includes(s.roof) || !['normal', 'away'].includes(s.scenario)) return null;
    return { plan: c.plan, settings: { season: s.season, roof: s.roof, scenario: s.scenario } };
  } catch {
    return null;
  }
}

export function el(tag, props = {}, ...children) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === 'class') e.className = v;
    else if (k === 'text') e.textContent = v;
    else e.setAttribute(k, v);
  }
  for (const c of children) e.append(c);
  return e;
}

export const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;
