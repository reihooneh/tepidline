// SVG charts, built with DOM calls (never from HTML strings).
const NS = 'http://www.w3.org/2000/svg';

export function svg(tag, attrs = {}, text) {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, String(v));
  if (text !== undefined) e.textContent = text;
  return e;
}

// A line or scatter chart with tidy axes. series: [{ points: [[x, y]], kind: 'line'|'dots', cls }].
export function chart(target, { series, x, y, width = 560, height = 300, xLabel, yLabel, marker, area, bands = [], spans = [], hlines = [] }) {
  const pad = { l: 58, r: 16, t: 14, b: 46 };
  const W = width - pad.l - pad.r, H = height - pad.t - pad.b;
  const sx = (v) => pad.l + ((v - x.min) / (x.max - x.min)) * W;
  const sy = (v) => pad.t + H - ((v - y.min) / (y.max - y.min)) * H;
  const root = svg('svg', { class: 'chart', viewBox: `0 0 ${width} ${height}`, role: 'img', 'aria-label': target.dataset.label || yLabel });
  for (const t of y.ticks) {
    root.append(svg('line', { class: 'grid', x1: pad.l, x2: pad.l + W, y1: sy(t), y2: sy(t) }));
    root.append(svg('text', { x: pad.l - 8, y: sy(t) + 4, 'text-anchor': 'end' }, y.format(t)));
  }
  for (const t of x.ticks) root.append(svg('text', { x: sx(t), y: pad.t + H + 18, 'text-anchor': 'middle' }, x.format(t)));
  root.append(svg('line', { class: 'axis', x1: pad.l, x2: pad.l + W, y1: pad.t + H, y2: pad.t + H }));
  root.append(svg('line', { class: 'axis', x1: pad.l, x2: pad.l, y1: pad.t, y2: pad.t + H }));
  if (xLabel) root.append(svg('text', { x: pad.l + W / 2, y: height - 6, 'text-anchor': 'middle' }, xLabel));
  if (yLabel) root.append(svg('text', { x: 14, y: pad.t + H / 2, 'text-anchor': 'middle', transform: `rotate(-90 14 ${pad.t + H / 2})` }, yLabel));
  for (const sp of spans) {
    root.append(svg('rect', { class: sp.cls, x: sx(sp.from), y: pad.t, width: Math.max(0, sx(sp.to) - sx(sp.from)), height: H }));
  }
  for (const b of bands) {
    const top = b.hi.map(([a, v]) => `${sx(a).toFixed(1)},${sy(v).toFixed(1)}`);
    const bottom = b.lo.slice().reverse().map(([a, v]) => `${sx(a).toFixed(1)},${sy(v).toFixed(1)}`);
    root.append(svg('polygon', { class: b.cls, points: [...top, ...bottom].join(' ') }));
  }
  for (const hl of hlines) root.append(svg('line', { class: hl.cls, x1: pad.l, x2: pad.l + W, y1: sy(hl.y), y2: sy(hl.y) }));
  if (area) {
    const pts = area.map(([a, b]) => `${sx(a)},${sy(b)}`).join(' ');
    root.append(svg('polygon', { class: 'area', points: `${sx(area[0][0])},${sy(y.min)} ${pts} ${sx(area[area.length - 1][0])},${sy(y.min)}` }));
  }
  for (const s of series) {
    if (s.kind === 'line') {
      const d = s.points.map(([a, b], i) => `${i ? 'L' : 'M'}${sx(a).toFixed(1)},${sy(b).toFixed(1)}`).join('');
      root.append(svg('path', { class: s.cls, d }));
    } else {
      for (const [a, b] of s.points) root.append(svg('circle', { class: s.cls, cx: sx(a).toFixed(1), cy: sy(b).toFixed(1), r: s.r || 3.2 }));
    }
  }
  if (marker) {
    root.append(svg('line', { class: 'marker', x1: sx(marker.x), x2: sx(marker.x), y1: pad.t, y2: pad.t + H }));
    if (marker.y !== undefined) root.append(svg('circle', { class: 'dot-ember', cx: sx(marker.x), cy: sy(marker.y), r: 5.5 }));
  }
  target.replaceChildren(root);
  return root;
}

export function ticks(min, max, n = 5) {
  const span = max - min || 1;
  const raw = span / n;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => span / s <= n) || 10 * mag;
  const out = [];
  for (let v = Math.ceil(min / step) * step; v <= max + 1e-9; v += step) out.push(Number(v.toFixed(10)));
  return out;
}
