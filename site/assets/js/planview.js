// The building from above: rooms, every pipe coloured by how many hours a day its water sits warm,
// and the outlets. Pure SVG built with DOM calls; nothing from a plan is inserted as markup.
import { css, warmRGB, hours } from './common.js';

const NS = 'http://www.w3.org/2000/svg';
const node = (tag, attrs = {}, text) => {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, String(v));
  if (text !== undefined) e.textContent = text;
  return e;
};

export function planView(container, building, result, { selected, onSelect, label } = {}) {
  const pts = [];
  for (const p of Object.values(building.pipes)) for (const q of p.points) pts.push(q);
  for (const r of building.rooms) pts.push([r.box[0], 0, r.box[1]], [r.box[2], 0, r.box[3]]);
  const xs = pts.map((p) => p[0]), zs = pts.map((p) => p[2]);
  const pad = 0.8;
  const x0 = Math.min(...xs) - pad, x1 = Math.max(...xs) + pad, z0 = Math.min(...zs) - pad, z1 = Math.max(...zs) + pad;
  const svg = node('svg', { class: 'plan', viewBox: `${x0} ${z0} ${x1 - x0} ${z1 - z0}`, role: 'img', 'aria-label': label || `Plan of ${building.name} with each pipe coloured by its warm hours a day` });
  for (const r of building.rooms) {
    const [a, b, c, d] = r.box;
    svg.append(node('rect', { class: 'room', x: Math.min(a, c), y: Math.min(b, d), width: Math.abs(c - a), height: Math.abs(d - b) }));
    svg.append(node('text', { class: 'room-name', x: Math.min(a, c) + 0.2, y: Math.min(b, d) + 0.55 }, r.name));
  }
  // Warmest pipes drawn last, on top.
  const order = Object.entries(building.pipes).sort((a, b) => (result.pipes[a[0]]?.band_hours ?? 0) - (result.pipes[b[0]]?.band_hours ?? 0));
  const sel = selected ? new Set([building.outlets[selected]?.hot, building.outlets[selected]?.cold]) : null;
  for (const [pid, p] of order) {
    const h = result.pipes[pid]?.band_hours ?? 0;
    const w = (p.dn >= 20 ? 0.2 : 0.14) + (p.zone === 'roof' ? 0.04 : 0);
    const line = node('polyline', {
      class: `pipe${sel && !sel.has(pid) ? '' : ''}`,
      points: p.points.map((q) => `${q[0]},${q[2]}`).join(' '),
      stroke: css(warmRGB(h)),
      'stroke-width': w,
      'stroke-dasharray': p.kind === 'cold' ? '0.35 0.18' : 'none',
    });
    line.append(node('title', {}, `${pid}: ${p.kind} pipe in the ${p.zone === 'roof' ? 'roof space' : p.zone}, ${p.length} m, ${hours(h)} warm a day`));
    svg.append(line);
  }
  svg.append(node('rect', { class: 'heater', x: building.heater[0] - 0.3, y: building.heater[2] - 0.3, width: 0.6, height: 0.6, rx: 0.12 }));
  svg.append(node('rect', { class: 'mains', x: building.meter[0] - 0.22, y: building.meter[2] - 0.22, width: 0.44, height: 0.44 }));
  for (const t of building.tmvs) svg.append(node('circle', { class: 'valve', cx: t.at[0], cy: t.at[2], r: 0.2 }));
  for (const [oid, o] of Object.entries(building.outlets)) {
    const r = result.outlets[oid];
    const c = node('circle', {
      class: `outlet${oid === selected ? ' sel' : ''}`,
      cx: o.at[0], cy: o.at[2], r: o.kind === 'shower' || o.kind === 'bath' ? 0.32 : 0.24,
      fill: css(warmRGB(Math.min(10, r ? r.worst_hours / 2 : 0))),
      tabindex: onSelect ? 0 : -1,
      'data-outlet': oid,
    });
    c.append(node('title', {}, `${o.name}: ${r ? `water up to ${hours(r.worst_hours)} warm` : ''}`));
    if (onSelect) {
      c.addEventListener('click', () => onSelect(oid));
      c.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect(oid); } });
    }
    svg.append(c);
  }
  container.replaceChildren(svg);
  return svg;
}
