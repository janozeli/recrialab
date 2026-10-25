// Drives the site like a person on a phone and keeps the evidence.
// Usage: node tools/verify-site/drive.mjs [--profile budget-android|iphone|pixel] [--url https://recrialab.com] [--look 004.024] [--out dir]
// Without --url, serves site/dist/ (run `bun run build` first) on a local port.
import { createServer } from 'node:http';
import { execSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { extname, join } from 'node:path';
import { createRequire } from 'node:module';
import { SCREENS, auditFilters, auditAbout, auditStageOnDress, auditFittingRoom } from './layout.mjs';

// The project's Playwright or the global one (`npm i -g playwright`), with no new dependency on the site.
const require = createRequire(import.meta.url);
const { chromium, webkit, devices } = (() => {
  try { return require('playwright'); } catch {
    return require(join(execSync('npm root -g', { encoding: 'utf8' }).trim(), 'playwright'));
  }
})();

const arg = (name, fallback) => {
  const i = process.argv.indexOf(`--${name}`);
  return i > 0 ? process.argv[i + 1] : fallback;
};
const root = execSync('git rev-parse --show-toplevel', { encoding: 'utf8' }).trim();
const head = execSync('git rev-parse HEAD', { encoding: 'utf8' }).trim();
// Profiles in place of physical devices. Each limit is a measurement with headroom (budget-android measures about 20 s
// to the mannequin, 29 s to the whole look and 5.1 MB); raise one only with the reason in the same change.
// budget-android: Moto G4 with a 4x slower CPU and slow 4G (1.6 Mbps, 150 ms), a student's phone.
// iphone: the WebKit engine (Safari's), catches iOS incompatibilities.
const PROFILES = {
  'budget-android': { browser: 'chromium', device: 'Moto G4', cpu: 4, network: { latency: 150, downloadThroughput: 1.6e6 / 8, uploadThroughput: 750e3 / 8 },
    limits: { mannequinMs: 30_000, loadMs: 60_000, mbDownloaded: 10 } },
  iphone: { browser: 'webkit', device: 'iPhone 13', limits: { mannequinMs: 15_000, loadMs: 30_000, mbDownloaded: 20 } },
  pixel: { browser: 'chromium', device: 'Pixel 7', limits: { mannequinMs: 15_000, loadMs: 30_000, mbDownloaded: 20 } },
};
const profileName = arg('profile', 'pixel');
const profile = PROFILES[profileName];
if (!profile) throw new Error(`unknown profile: ${profileName} (${Object.keys(PROFILES).join(', ')})`);
const out = arg('out', join(root, 'site', 'verify-out', profileName));
const look = arg('look', '004.024');
mkdirSync(out, { recursive: true });

// Same behaviour as Workers static assets: /sobre serves sobre.html.
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json',
  '.glb': 'model/gltf-binary', '.webp': 'image/webp', '.png': 'image/png', '.svg': 'image/svg+xml', '.woff2': 'font/woff2' };
let server;
let base = arg('url');
if (!base) {
  const dist = join(root, 'site', 'dist');
  if (!existsSync(join(dist, 'index.html'))) throw new Error('site/dist/ is empty: run `bun run build` in site/');
  server = createServer((req, res) => {
    let path = decodeURIComponent(new URL(req.url, 'http://x').pathname);
    if (path === '/') path = '/index.html';
    if (!extname(path)) path += '.html';
    const file = join(dist, path);
    if (!file.startsWith(dist) || !existsSync(file)) { res.writeHead(404).end(); return; }
    res.writeHead(200, { 'content-type': TYPES[extname(file)] ?? 'application/octet-stream' }).end(readFileSync(file));
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  base = `http://127.0.0.1:${server.address().port}`;
}

const failures = [];
const check = (ok, message) => { if (!ok) failures.push(message); return ok; };
const browser = profile.browser === 'webkit' ? await webkit.launch()
  : await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
const context = await browser.newContext({ ...devices[profile.device] });
const page = await context.newPage();
if (profile.cpu || profile.network) {
  const cdp = await context.newCDPSession(page);
  if (profile.cpu) await cdp.send('Emulation.setCPUThrottlingRate', { rate: profile.cpu });
  if (profile.network) { await cdp.send('Network.enable'); await cdp.send('Network.emulateNetworkConditions', { offline: false, ...profile.network }); }
}
const measures = {};
// Long tasks (> 50 ms) freeze touch; WebKit does not expose this API.
await page.addInitScript(() => {
  window.__longTasks = [];
  try { new PerformanceObserver(l => window.__longTasks.push(...l.getEntries().map(e => ({ t: e.startTime, d: e.duration }))))
    .observe({ type: 'longtask', buffered: true }); } catch {}
});
const errors = [];
page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
page.on('pageerror', e => errors.push(String(e)));
page.on('requestfailed', r => errors.push(`failed ${r.url()}`));
page.on('response', r => { if (r.status() >= 400) errors.push(`${r.status()} ${r.url()}`); });

try {
  // 1. Is the build being served this commit?
  const build = await (await context.request.get(`${base}/build.json`)).json();
  check(build.commit === head, `build.json is ${build.commit?.slice(0, 7)}, HEAD is ${head.slice(0, 7)}`);
  check(build.dirty === false, 'build.json marks local changes (dirty: true)');

  // 2. Look link: opens the fitting room already dressed.
  const start = Date.now();
  await page.goto(`${base}/?look=${look}`);
  await page.waitForFunction(() => document.querySelector('#stage')?.getAttribute('aria-busy') === 'false', null,
    { timeout: profile.limits.loadMs + 30_000 });
  measures.mannequinMs = Date.now() - start;
  // The look's garments already dressed: the 3D has meshes besides the body.
  await page.waitForLoadState('networkidle', { timeout: profile.limits.loadMs }).catch(() => {});
  measures.loadMs = Date.now() - start;
  check(measures.mannequinMs <= profile.limits.mannequinMs,
    `mannequin showed in ${measures.mannequinMs} ms (limit ${profile.limits.mannequinMs} ms on ${profileName})`);
  check(measures.loadMs <= profile.limits.loadMs,
    `load ${measures.loadMs} ms (limit ${profile.limits.loadMs} ms on ${profileName})`);
  // Frames per second with the mannequin turning (drag), measured with requestAnimationFrame.
  const box = await page.locator('#stage canvas').boundingBox();
  const spinStart = await page.evaluate(() => performance.now());
  const frames = page.evaluate(() => new Promise(resolve => {
    let n = 0; const t0 = performance.now();
    const tick = () => { n++; performance.now() - t0 < 3000 ? requestAnimationFrame(tick) : resolve(n / ((performance.now() - t0) / 1000)); };
    requestAnimationFrame(tick);
  }));
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  for (let i = 0; i < 30; i++) { await page.mouse.move(box.x + box.width / 2 + (i % 10) * 15, box.y + box.height / 2); await page.waitForTimeout(90); }
  await page.mouse.up();
  // FPS and long tasks are informative only: CI draws WebGL in software (SwiftShader), without the phone's GPU,
  // and the longest task varies from 0 to about 800 ms between identical runs. Failing on that would be noise.
  measures.fpsSoftware = Math.round(await frames);
  const longTasks = await page.evaluate(t0 => window.__longTasks.filter(e => e.t >= t0), spinStart);
  measures.longestSpinTaskMs = profile.browser === 'webkit' ? null : Math.round(Math.max(0, ...longTasks.map(e => e.d)));
  measures.mbDownloaded = +(await page.evaluate(() => performance.getEntriesByType('resource')
    .reduce((s, r) => s + (r.transferSize || r.encodedBodySize || 0), 0)) / 1048576).toFixed(1);
  check(measures.mbDownloaded <= profile.limits.mbDownloaded, `${measures.mbDownloaded} MB to open a look (limit ${profile.limits.mbDownloaded} MB)`);
  // The collection shows one tab at a time (EM CIMA / EMBAIXO): adds up the dressed garments of both.
  await page.waitForTimeout(3000);
  const worn = [];
  for (const slot of ['top', 'bottom']) {
    await page.locator(`#chips [data-slot="${slot}"]`).click();
    worn.push(...await page.$$eval('#clothes-grid [data-piece][aria-pressed="true"]', els => els.map(e => e.dataset.piece)));
  }
  await page.locator('#chips [data-slot="top"]').click();
  worn.sort();
  check(worn.join('.') === look.split('.').sort().join('.'), `?look=${look} dressed [${worn}]`);
  check(await page.locator('#stage canvas').count() === 1, 'stage without <canvas>');
  check(await page.locator('#stage-status').textContent() === '', `notice on the stage: ${await page.locator('#stage-status').textContent()}`);
  await page.waitForTimeout(1500);
  await page.screenshot({ path: join(out, '1-look.png') });
  for (const p of await auditFittingRoom(page)) check(false, `layout on ${profileName}: ${p}`);
  for (const p of await auditFilters(page)) check(false, `filters on ${profileName}: ${p}`);

  // 3. Swapping the top through the collection updates the address.
  const other = page.locator('#clothes-grid [data-piece][data-slot="top"][aria-pressed="false"]').first();
  const otherId = await other.getAttribute('data-piece');
  await other.click();
  await page.waitForFunction(id => new URLSearchParams(location.search).get('look')?.split('.').includes(id), otherId, { timeout: 30_000 })
    .catch(() => check(false, `dressing ${otherId} did not update ?look= (${page.url()})`));
  await page.waitForTimeout(400);
  for (const p of await auditStageOnDress(page)) check(false, `${profileName}: ${p}`);
  await page.waitForTimeout(1500);
  await page.screenshot({ path: join(out, '2-swap.png') });

  // 4. The about page opens without three.js and with content.
  await page.goto(`${base}/sobre`);
  check(await page.locator('h1').textContent() === 'Sobre', 'about page without <h1>Sobre</h1>');
  await page.screenshot({ path: join(out, '3-about.png'), fullPage: true });
  for (const p of await auditAbout(page)) check(false, `about page on ${profileName}: ${p}`);

  // Other screens (small and landscape phone, tablet, desktop): only on the profile without CPU and network throttling.
  if (profileName === 'pixel') for (const [screen, device] of Object.entries(SCREENS)) {
    const ctx = await browser.newContext(device);
    const p = await ctx.newPage();
    p.on('pageerror', e => errors.push(`${screen}: ${e}`));
    await p.goto(`${base}/?look=${look}`);
    await p.waitForFunction(() => document.querySelector('#stage')?.getAttribute('aria-busy') === 'false', null, { timeout: 60_000 });
    await p.waitForFunction(() => !document.querySelector('.card.loading') && !document.querySelector('#export-look').disabled, null, { timeout: 60_000 });
    await p.waitForTimeout(800);
    await p.screenshot({ path: join(out, `screen-${screen}.png`) });
    for (const x of await auditFittingRoom(p)) check(false, `layout on ${screen}: ${x}`);
    for (const x of await auditFilters(p)) check(false, `filters on ${screen}: ${x}`);
    await p.locator('#export-look').click();
    await p.waitForSelector('#look-export-dialog[open] img[src]');
    await p.waitForTimeout(500);
    await p.screenshot({ path: join(out, `screen-${screen}-save.png`) });
    const save = await p.evaluate(() => {
      const d = document.querySelector('#look-export-dialog').getBoundingClientRect();
      const b = document.querySelector('#save-look').getBoundingClientRect();
      return { fits: d.top >= 0 && d.bottom <= innerHeight + 1, button: b.bottom <= innerHeight + 1 && b.top >= 0 };
    });
    check(save.fits && save.button, `the save dialog does not fit on ${screen}: ${JSON.stringify(save)}`);
    await p.locator('#export-close').click();
    await p.goto(`${base}/sobre`);
    for (const x of await auditAbout(p)) check(false, `about page on ${screen}: ${x}`);
    await ctx.close();
  }

  // 5. Garment colour close to the thrift-shop photo: a light that was too strong washed the orange of 015 into peach
  // (saturation on stage 0.55 with ACES at exposure 1, 0.85 with Neutral at 0.55; photo 0.94, texture 0.81).
  await page.goto(`${base}/?look=015`);
  await page.waitForFunction(() => document.querySelector('#stage')?.getAttribute('aria-busy') === 'false', null,
    { timeout: profile.limits.loadMs + 30_000 });
  await page.waitForLoadState('networkidle', { timeout: profile.limits.loadMs }).catch(() => {});
  // aria-busy only follows the body: waits for the shorts to show on stage before measuring (slow phone).
  const reader = await context.newPage();
  const measureOrange = async () => reader.evaluate(async b64 => {
    const bmp = await createImageBitmap(await (await fetch(`data:image/png;base64,${b64}`)).blob());
    const canvas = new OffscreenCanvas(bmp.width, bmp.height).getContext('2d');
    canvas.drawImage(bmp, 0, 0);
    const d = canvas.getImageData(0, 0, bmp.width, bmp.height).data; const sat = [];
    for (let i = 0; i < d.length; i += 4) {
      const [r, g, b] = [d[i], d[i + 1], d[i + 2]]; const max = Math.max(r, g, b), min = Math.min(r, g, b);
      if (max === min || max !== r || g < b) continue;   // orange: red highest, green above blue
      const hue = (g - b) / (max - min) / 6;
      if (hue > .02 && hue < .12 && (max - min) / max > .3) sat.push((max - min) / max);
    }
    sat.sort((a, b) => a - b);
    return { pixels: sat.length, saturation: +(sat[sat.length >> 1] ?? 0).toFixed(2) };
  }, (await page.locator('#stage canvas').screenshot()).toString('base64'));
  for (let i = 0; i < 20; i++) {
    await page.waitForTimeout(1500);
    measures.orange015 = await measureOrange();
    if (measures.orange015.pixels > 1000) break;
  }
  await reader.close();
  check(measures.orange015.pixels > 1000 && measures.orange015.saturation >= .68,
    `orange of 015 washed out on stage: saturation ${measures.orange015.saturation} over ${measures.orange015.pixels} px (minimum 0.68)`);

  check(errors.length === 0, `console/network errors:\n  ${errors.join('\n  ')}`);
} catch (error) {
  failures.push(String(error));
  await page.screenshot({ path: join(out, 'error.png') }).catch(() => {});
} finally {
  await browser.close();
  server?.close();
}

const report = { profile: profileName, base, head: head.slice(0, 7), look, measures, limits: profile.limits, ok: failures.length === 0, failures, evidence: out };
writeFileSync(join(out, 'report.json'), JSON.stringify(report, null, 2) + '\n');
console.log(JSON.stringify(report, null, 2));
process.exit(report.ok ? 0 : 1);
