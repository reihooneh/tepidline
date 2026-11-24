// Home: the example house's summer week (made at build time by the same Python model) on the 3D
// house, and the headline findings.
import { HOME } from './data/home.js';
import { PLANS } from './data/plans.js';
import { clock, dollars, hours, litres } from './common.js';
import { createHouse, hasWebGL } from './house3d.js';

const { building: B, result: R } = HOME;
const $ = (id) => document.getElementById(id);
const name = (oid) => B.outlets[oid].name;

const byRisk = Object.entries(R.outlets).sort((a, b) => b[1].risky_litres * b[1].weight - a[1].risky_litres * a[1].weight);
const [topId, top] = byRisk[0];
$('t-shower').textContent = litres(top.risky_litres);
$('t-shower-what').textContent = `a week from the ${name(topId).toLowerCase()} had sat warm for over 4 hours in the pipes first`;

const [pipeId, pipe] = Object.entries(R.pipes).sort((a, b) => b[1].band_hours - a[1].band_hours)[0];
const p = B.pipes[pipeId];
$('t-pipe').textContent = hours(pipe.band_hours);
$('t-pipe-what').textContent = `a day the water in the ${p.kind} pipe ${p.zone === 'roof' ? 'across the roof space' : `in the ${p.zone}`} spends warm`;

const guest = R.outlets['guest-shower'];
$('t-guest').textContent = hours(guest.worst_hours);
$('t-guest-what').textContent = 'of warm standing time in the guest shower’s first water, used once a week';

const plan = PLANS['house-summer'];
const base = plan.baseline.score;
const value = plan.frontier
  .filter((r) => r.cost > 0 && base - r.score >= 0.3 * base)
  .sort((a, b) => (b.cost ? (base - b.score) / b.cost : 0) - (a.cost ? (base - a.score) / a.cost : 0))[0];
if (value) {
  const titles = Object.fromEntries(plan.fixes.map((f) => [f.id, f.title]));
  const paid = value.fixes.filter((f) => plan.fixes.find((x) => x.id === f).cost > 0);
  $('t-fix').textContent = `−${Math.round((1 - value.score / base) * 100)}%`;
  $('t-fix-what').textContent = `warm water at the taps for ${dollars(value.cost)}: ${paid.map((f) => titles[f].toLowerCase()).join(', ')}. Lagging alone barely helps.`;
}
const totalL = Object.values(R.outlets).reduce((s, o) => s + o.litres, 0);
$('home-sub').textContent = `Nine outlets, ${Object.keys(B.pipes).length} pipes holding ${litres(Object.values(B.pipes).reduce((s, x) => s + x.litres, 0))} between them, a family of four using ${Math.round(totalL / 7).toLocaleString('en-AU')} L a day, and a dark roof in a Sydney January.`;

// ---------- 3D ----------
const stage = $('hero-stage');
const slider = $('time');
const playBtn = $('play');
if (!hasWebGL()) {
  $('hero-fallback').hidden = false;
} else {
  const badge = $('hero-badge');
  let shown = -1;
  const house = createHouse(stage, {
    onTime(s, roof) {
      const step = Math.floor(s / 300);
      if (step === shown) return;
      shown = step;
      slider.value = String(Math.round(s / 30) * 30);
      $('clock').textContent = clock(s);
      badge.replaceChildren('Roof space ', Object.assign(document.createElement('strong'), { textContent: `${roof.toFixed(0)} °C` }));
      stage.dataset.time = String(Math.round(s));
    },
  });
  house.set(B, R);
  const setPlay = (on) => {
    const now = house.play(on);
    playBtn.textContent = now ? 'Pause' : 'Play the day';
    playBtn.setAttribute('aria-pressed', String(now));
  };
  setPlay(house.playing);
  playBtn.addEventListener('click', () => setPlay(!house.playing));
  slider.addEventListener('input', () => {
    setPlay(false);
    house.setTime(Number(slider.value));
  });
}
document.body.dataset.ready = '1';
