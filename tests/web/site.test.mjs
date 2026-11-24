// Browser tests for every page at phone, tablet and desktop widths: no errors, no sideways
// scrolling, no text on top of other text (HTML or SVG), and the main things work.
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { chromium } from 'playwright';
import { serve } from '../../scripts/serve.mjs';

const PAGES = ['index.html', 'check.html', 'fix.html', 'method.html'];
const SIZES = [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'tablet', width: 820, height: 1180 },
  { name: 'phone', width: 390, height: 844 },
];
let server, browser, base;

before(async () => {
  server = await serve(0);
  base = `http://127.0.0.1:${server.address().port}/`;
  browser = await chromium.launch({ args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader'] });
});
after(async () => {
  await browser?.close();
  server?.close();
});

async function open(path, size = SIZES[0]) {
  const context = await browser.newContext({ viewport: { width: size.width, height: size.height }, reducedMotion: 'reduce', acceptDownloads: true });
  const page = await context.newPage();
  const errors = [];
  page.on('console', (m) => {
    if (m.type() === 'error' && !/GL Driver Message|WebGL/.test(m.text())) errors.push(m.text());
  });
  page.on('pageerror', (e) => errors.push(e.message));
  await page.goto(base + path);
  await page.waitForFunction(() => document.body.dataset.ready, null, { timeout: 180000 });
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(300);
  return { page, context, errors };
}

// Every piece of visible text, HTML or SVG: no two different pieces overlap.
async function textOverlaps(page) {
  return page.evaluate(() => {
    const boxes = [];
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
      const n = walker.currentNode;
      if (!n.textContent.trim()) continue;
      const elx = n.parentElement;
      if (elx.closest('.sr, [hidden], .skip, option, title, select')) continue;
      const det = elx.closest('details');
      if (det && !det.open && !elx.closest('summary')) continue;
      const cs = getComputedStyle(elx);
      if (cs.visibility === 'hidden' || cs.display === 'none' || Number(cs.opacity) === 0) continue;
      if (elx instanceof SVGElement) {
        const r = elx.getBoundingClientRect();
        if (r.width >= 1 && r.height >= 1) boxes.push({ r, text: n.textContent.trim().slice(0, 40), node: n });
        continue;
      }
      const range = document.createRange();
      range.selectNodeContents(n);
      for (const r of range.getClientRects()) if (r.width >= 1 && r.height >= 1) boxes.push({ r, text: n.textContent.trim().slice(0, 40), node: n });
    }
    const out = [];
    for (let i = 0; i < boxes.length; i++) {
      for (let j = i + 1; j < boxes.length; j++) {
        const a = boxes[i], b = boxes[j];
        if (a.node === b.node) continue;
        const w = Math.min(a.r.right, b.r.right) - Math.max(a.r.left, b.r.left);
        const h = Math.min(a.r.bottom, b.r.bottom) - Math.max(a.r.top, b.r.top);
        if (w > 2 && h > Math.min(a.r.height, b.r.height) * 0.35) out.push(`"${a.text}" overlaps "${b.text}"`);
      }
    }
    return out;
  });
}

// Everything drawn in a chart stays inside the chart.
async function svgOutside(page) {
  return page.evaluate(() => {
    const out = [];
    for (const s of document.querySelectorAll('svg.chart')) {
      const f = s.getBoundingClientRect();
      for (const t of s.querySelectorAll('text, line, rect, path')) {
        const r = t.getBoundingClientRect();
        if (r.width === 0 && r.height === 0) continue;
        if (r.left < f.left - 1 || r.right > f.right + 1 || r.top < f.top - 1 || r.bottom > f.bottom + 1) out.push(t.textContent || t.tagName);
      }
    }
    return out;
  });
}

// Controls must not sit on top of each other.
async function boxOverlaps(page) {
  return page.evaluate(() => {
    const els = [...document.querySelectorAll('main .button, main button, main input:not([type=file]), main select, main .stage, main table, main .tile, main .chart-box, main .legend, main .pill, main .fixlist li, main .drop, main .check-row')]
      .filter((e) => e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden' && !e.closest('[hidden]'));
    const out = [];
    for (let i = 0; i < els.length; i++) {
      for (let j = i + 1; j < els.length; j++) {
        if (els[i].contains(els[j]) || els[j].contains(els[i])) continue;
        const a = els[i].getBoundingClientRect(), b = els[j].getBoundingClientRect();
        const w = Math.min(a.right, b.right) - Math.max(a.left, b.left);
        const h = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
        if (w > 1 && h > 1) out.push(`${els[i].id || els[i].className || els[i].tagName} overlaps ${els[j].id || els[j].className || els[j].tagName}`);
      }
    }
    return out;
  });
}

for (const path of PAGES) {
  for (const size of SIZES) {
    test(`${path} at ${size.name}: no errors, no sideways scroll, nothing overlapping`, async () => {
      const { page, context, errors } = await open(path, size);
      const scroll = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      assert.ok(scroll <= 0, `page scrolls sideways by ${scroll}px`);
      assert.deepEqual(await textOverlaps(page), []);
      assert.deepEqual(await svgOutside(page), []);
      assert.deepEqual(await boxOverlaps(page), []);
      assert.deepEqual(errors, []);
      await context.close();
    });
  }
}

test('every page has the strict content security policy and loads nothing from elsewhere', async () => {
  for (const path of PAGES) {
    const html = readFileSync(new URL(`../../site/${path}`, import.meta.url), 'utf8');
    assert.match(html, /default-src 'none'; script-src 'self' 'wasm-unsafe-eval'/);
    assert.doesNotMatch(html, /<script(?![^>]*src="assets\/js\/)/, 'inline script');
    assert.doesNotMatch(html, /style="/, 'inline style');
    assert.doesNotMatch(html, /src="https?:/);
  }
});

test('check: Python runs in the browser, agrees with the build, and loads nothing from elsewhere', async () => {
  const { page, context, errors } = await open('check.html');
  const outside = [];
  page.on('request', (r) => { if (!r.url().startsWith(base)) outside.push(r.url()); });
  const before = await page.textContent('#headline');
  // Change the season and back: two live runs of the Python model.
  await page.selectOption('#season', 'winter');
  await page.waitForFunction(() => Number(document.body.dataset.checked) >= 2, null, { timeout: 180000 });
  assert.match(await page.textContent('#status'), /Followed a week of water/);
  const winter = await page.textContent('#headline');
  assert.notEqual(winter, before);
  await page.selectOption('#season', 'summer');
  await page.waitForFunction(() => Number(document.body.dataset.checked) >= 3, null, { timeout: 120000 });
  assert.equal(await page.textContent('#headline'), before, 'the browser and the build give the same answer');
  assert.equal(await page.locator('#outlets tr').count(), 9);
  await page.click('#outlets tr:nth-child(4)');
  assert.match(await page.textContent('#first-title'), /guest shower/);
  assert.deepEqual(outside, []);
  assert.deepEqual(errors, []);
  await context.close();
});

test('check: a hostile plan is refused with a message and never reaches the page as markup', async () => {
  const { page, context, errors } = await open('check.html');
  const bad = [
    ['not json', 'that file', /valid JSON/],
    ['array.json', '[1,2,3]', /JSON object/],
    ['loop.json', JSON.stringify({ name: '<img src=x onerror=alert(1)>', pipes: [{ id: 'a', from: 'pipe:b', zone: 'roof', points: [[0, 0, 0], [1, 0, 0]] }, { id: 'b', from: 'pipe:a', zone: 'roof', points: [[0, 0, 0], [1, 0, 0]] }], outlets: [{ id: 'o', name: 'x', kind: 'shower', hot: 'a', at: [0, 0, 0] }] }), /loop|hot must name/],
    ['nan.json', '{"name":"x","pipes":[{"id":"a","from":"hot","zone":"roof","points":[[0,0,0],[1e400,0,0]]}],"outlets":[]}', /point|outlets/],
  ];
  for (const [name, text, message] of bad) {
    await page.setInputFiles('#file', { name, mimeType: 'application/json', buffer: Buffer.from(text) });
    await page.waitForFunction(() => !document.getElementById('error').hidden, null, { timeout: 180000 });
    assert.match(await page.textContent('#error'), message);
    await page.evaluate(() => { document.getElementById('error').hidden = true; });
  }
  assert.equal(await page.locator('main img').count(), 0);
  assert.deepEqual(errors, []);
  await context.close();
});

test('check: the example template downloads and loads back as a plan', async () => {
  const { page, context, errors } = await open('check.html');
  const [download] = await Promise.all([page.waitForEvent('download'), page.click('#template')]);
  const path = await download.path();
  await page.setInputFiles('#file', path);
  await page.waitForFunction(() => /Your plan: Family house/.test(document.getElementById('loaded').textContent), null, { timeout: 180000 });
  assert.equal(await page.locator('#outlets tr').count(), 9);
  assert.deepEqual(errors, []);
  await context.close();
});

test('fix: the budget picks the best set from every combination, and the plan view shows it', async () => {
  const { page, context, errors } = await open('fix.html');
  assert.match(await page.textContent('#tried'), /^144 combinations/);
  await page.$eval('#budget', (e) => { e.value = '0'; e.dispatchEvent(new Event('input')); });
  assert.match(await page.textContent('#chosen'), /guest bathroom/);
  await page.$eval('#budget', (e) => { e.value = '3000'; e.dispatchEvent(new Event('input')); });
  assert.match(await page.textContent('#chosen'), /Move the cold pipes out of the roof/);
  assert.equal(await page.textContent('#cut'), '70%');
  await page.click('#show-plan');
  await page.waitForFunction(() => !document.getElementById('pair').hidden, null, { timeout: 180000 });
  assert.equal(await page.locator('#pair svg.plan').count(), 2);
  assert.deepEqual(errors, []);
  await context.close();
});

test('fix: a tampered hand-off from the check page is ignored', async () => {
  const { page, context } = await open('fix.html');
  await page.evaluate(() => sessionStorage.setItem('tepidline-choice', JSON.stringify({ plan: 'house', settings: { season: '<b>', roof: 'dark', scenario: 'normal' } })));
  await page.reload();
  await page.waitForFunction(() => document.body.dataset.ready);
  assert.match(await page.textContent('#whose'), /^The example house, in a Sydney summer/);
  await context.close();
});

test('method: every model check passes', async () => {
  const { page, context, errors } = await open('method.html');
  assert.equal(await page.locator('.check-row .no').count(), 0);
  assert.ok(await page.locator('.check-row .ok').count() >= 5);
  assert.deepEqual(errors, []);
  await context.close();
});
