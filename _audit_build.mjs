/**
 * Real click-path audit for OrcaAppBuilder (headless Chrome).
 * Run: node _audit_build.mjs [url]
 */
import puppeteer from 'puppeteer-core';
import http from 'http';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = __dirname;
const failures = [];
const ok = [];

function pass(msg) { ok.push(msg); console.log('PASS', msg); }
function fail(msg) { failures.push(msg); console.error('FAIL', msg); }

async function serveLocal() {
  const server = http.createServer((req, res) => {
    let p = decodeURIComponent((req.url || '/').split('?')[0]);
    if (p === '/') p = '/index.html';
    const fp = path.join(ROOT, p.replace(/^\//, ''));
    if (!fp.startsWith(ROOT) || !fs.existsSync(fp) || fs.statSync(fp).isDirectory()) {
      res.writeHead(404); res.end('missing'); return;
    }
    const ext = path.extname(fp);
    const types = { '.html': 'text/html', '.js': 'application/javascript', '.css': 'text/css', '.png': 'image/png', '.json': 'application/json' };
    res.writeHead(200, { 'Content-Type': types[ext] || 'application/octet-stream' });
    fs.createReadStream(fp).pipe(res);
  });
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  const port = server.address().port;
  return { server, base: `http://127.0.0.1:${port}` };
}

async function main() {
  const argUrl = process.argv[2];
  let server, base;
  if (argUrl) {
    base = argUrl.replace(/\/$/, '');
  } else {
    ({ server, base } = await serveLocal());
  }

  const browser = await puppeteer.launch({
    executablePath: '/usr/bin/google-chrome',
    headless: 'new',
    args: ['--no-sandbox', '--disable-gpu', '--window-size=390,844']
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 390, height: 844, isMobile: true, hasTouch: true });

  // Dismiss terms if present
  await page.goto(base + '/', { waitUntil: 'domcontentloaded', timeout: 60000 });
  await new Promise(r => setTimeout(r, 800));
  const termsBtn = await page.$('#terms-close-btn, #orca-terms-overlay .btn, button');
  try {
    const closed = await page.evaluate(() => {
      const btn = document.getElementById('terms-close-btn');
      if (btn) { btn.click(); return true; }
      const overlay = document.getElementById('orca-terms-overlay');
      if (overlay) overlay.classList.remove('open');
      try { localStorage.setItem('orcaappbuilder_terms_accepted', '1'); } catch (e) {}
      return false;
    });
    if (closed) pass('terms dismissed');
  } catch (e) {}

  // Force fresh build state
  await page.evaluate(() => {
    try { localStorage.removeItem('orcaapp_build_draft'); } catch (e) {}
  });
  await page.goto(base + '/', { waitUntil: 'domcontentloaded', timeout: 60000 });
  await new Promise(r => setTimeout(r, 500));
  await page.evaluate(() => {
    try { localStorage.setItem('orcaappbuilder_terms_accepted', '1'); } catch (e) {}
    const o = document.getElementById('orca-terms-overlay');
    if (o) o.classList.remove('open');
  });

  // Open Build
  await page.evaluate(() => showSection('build'));
  await new Promise(r => setTimeout(r, 300));

  let scratchVisible = await page.evaluate(() => {
    const s = document.getElementById('bld-scratch-label');
    const e = document.getElementById('bld-existing-label');
    const bld1 = document.getElementById('bld-1');
    return !!(s && e && bld1 && bld1.classList.contains('active') &&
      s.offsetParent !== null && e.offsetParent !== null);
  });
  if (scratchVisible) pass('Build step1 shows scratch + already started');
  else fail('Build step1 missing scratch/already started visibility');

  // Select already started + audience
  await page.evaluate(() => {
    const cards = document.querySelectorAll('#bld-situation-grid .choice-card');
    if (cards[1]) cards[1].click();
    const aud = document.querySelectorAll('#bld-1 .choice-grid')[1]?.querySelectorAll('.choice-card');
    if (aud && aud[0]) aud[0].click();
  });
  await new Promise(r => setTimeout(r, 200));
  await page.evaluate(() => bldNext(1));
  await new Promise(r => setTimeout(r, 400));

  const onStep2 = await page.evaluate(() => document.getElementById('bld-2')?.classList.contains('active'));
  const panelShown = await page.evaluate(() => {
    const p = document.getElementById('bld-existing-panel');
    return p && getComputedStyle(p).display !== 'none';
  });
  if (onStep2 && panelShown) pass('Already started opens upload panel on step 2');
  else fail(`Already started step2=${onStep2} panel=${panelShown}`);

  // Help buttons
  const helpOk = await page.evaluate(() => {
    const fix = document.querySelector('[data-exist-help="fix"]');
    if (!fix) return 'no-fix-btn';
    fix.click();
    const v = document.getElementById('bld-exist-help')?.value;
    const selected = fix.classList.contains('selected-green');
    return v === 'fix' && selected ? 'ok' : `value=${v} selected=${selected}`;
  });
  if (helpOk === 'ok') pass('Fix It help tile selects');
  else fail('Fix It help tile: ' + helpOk);

  // Escape hatch back to two options
  const escaped = await page.evaluate(() => {
    if (typeof resetBuildWizard === 'function') resetBuildWizard();
    else if (typeof goBuildSituationStep === 'function') goBuildSituationStep();
    else return 'no-reset-fn';
    const bld1 = document.getElementById('bld-1');
    const scratch = document.getElementById('bld-scratch-label');
    const existing = document.getElementById('bld-existing-label');
    return (bld1?.classList.contains('active') && scratch && existing) ? 'ok' : 'still-stuck';
  });
  if (escaped === 'ok') pass('resetBuildWizard returns to two options');
  else fail('Cannot escape to situation step: ' + escaped);

  // bldBack path: go to step2 then back
  await page.evaluate(() => {
    document.querySelectorAll('#bld-situation-grid .choice-card')[0]?.click();
    document.querySelectorAll('#bld-1 .choice-grid')[1]?.querySelectorAll('.choice-card')[1]?.click();
    bldNext(1);
  });
  await new Promise(r => setTimeout(r, 200));
  await page.evaluate(() => bldBack(2));
  await new Promise(r => setTimeout(r, 200));
  const afterBack = await page.evaluate(() => document.getElementById('bld-1')?.classList.contains('active'));
  if (afterBack) pass('bldBack returns to situation step');
  else fail('bldBack did not return to situation step');

  // Sticky action bar after a fake plan (Already started path)
  await page.evaluate(() => {
    resetBuildWizard();
    document.querySelectorAll('#bld-situation-grid .choice-card')[1]?.click();
    document.querySelectorAll('#bld-1 .choice-grid')[1]?.querySelectorAll('.choice-card')[0]?.click();
    bldNext(1);
  });
  await new Promise(r => setTimeout(r, 200));
  const sticky = await page.evaluate(() => {
    const resultEl = document.getElementById('bld-result');
    const actionsEl = document.getElementById('bld-actions');
    resultEl.innerHTML = '<div class="ai-response-box"><div class="ai-response-header">Plan</div><div class="ai-response-body">' +
      ('Step one do this. '.repeat(20)) + '</div></div>';
    if (actionsEl) actionsEl.style.display = '';
    if (typeof showBuildStartHere === 'function') showBuildStartHere();
    else if (typeof revealBuildStickyBar === 'function') revealBuildStickyBar();
    else setBuildStickyBar(true);
    const bar = document.getElementById('bld-sticky-bar');
    const walk = document.getElementById('bld-sticky-walk');
    const visible = bar?.classList.contains('visible');
    const z = bar ? getComputedStyle(bar).zIndex : '';
    const navZ = getComputedStyle(document.querySelector('.mobile-nav')).zIndex;
    return { visible, z, navZ, walk: !!walk, bodyClass: document.body.classList.contains('bld-sticky-open') };
  });
  await new Promise(r => setTimeout(r, 250));
  const sticky2 = await page.evaluate(() => {
    const bar = document.getElementById('bld-sticky-bar');
    return {
      visible: bar?.classList.contains('visible'),
      display: bar ? getComputedStyle(bar).display : '',
      z: bar ? getComputedStyle(bar).zIndex : ''
    };
  });
  if (sticky2.visible && sticky2.display !== 'none' && Number(sticky2.z) >= 150)
    pass('Sticky bar visible above mobile nav after plan (z=' + sticky2.z + ')');
  else fail('Sticky bar not reliably shown: ' + JSON.stringify({ sticky, sticky2 }));

  // Nav sections exist
  for (const id of ['home','learn','brainstorm','build','launchcheck','troubleshoot','projects','links']) {
    const exists = await page.evaluate((sid) => !!document.getElementById('section-' + sid), id);
    if (exists) pass('section ' + id + ' present');
    else fail('section missing: ' + id);
  }

  // Home links sample
  const badLinks = await page.evaluate(async () => {
    const anchors = [...document.querySelectorAll('a.pod-app, a.resource-card')];
    const hrefs = anchors.map(a => a.href).filter(h => h.startsWith('http'));
    return hrefs.slice(0, 20);
  });
  for (const href of badLinks) {
    try {
      const res = await fetch(href, { method: 'GET', redirect: 'follow', signal: AbortSignal.timeout(12000) });
      if (res.status >= 400) fail(`link ${res.status} ${href}`);
      else pass(`link ${res.status} ${href.replace(/https?:\/\//,'')}`);
    } catch (e) {
      fail(`link error ${href}: ${e.message}`);
    }
  }

  // API health
  try {
    const res = await fetch('https://web-production-aaaba.up.railway.app/api/health', { signal: AbortSignal.timeout(15000) });
    const j = await res.json();
    if (j.status === 'ok') pass('API health ok aivm=' + j.aivm);
    else fail('API health unexpected ' + JSON.stringify(j));
  } catch (e) {
    fail('API health: ' + e.message);
  }

  await browser.close();
  if (server) server.close();

  console.log('\n==== SUMMARY ====');
  console.log('PASS', ok.length);
  console.log('FAIL', failures.length);
  failures.forEach(f => console.log(' -', f));
  process.exit(failures.length ? 1 : 0);
}

main().catch(e => { console.error(e); process.exit(2); });
