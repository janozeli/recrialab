// Fit showcase: dresses each garment of the collection on the build and photographs front, profile and back.
// Usage: node tools/verify-site/showcase.mjs [--pieces 016,019] [--out dir] [--crop collar]
// Serves site/dist/ (run `bun run build` first). Writes one sheet per garment and showcase.png with all of them,
// to check the fit against the original photos without opening the site garment by garment.
import { createServer } from 'node:http';
import { execSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { extname, join } from 'node:path';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { chromium } = (() => {
  try { return require('playwright'); } catch {
    return require(join(execSync('npm root -g', { encoding: 'utf8' }).trim(), 'playwright'));
  }
})();
const arg = (name, fallback) => { const i = process.argv.indexOf(`--${name}`); return i > 0 ? process.argv[i + 1] : fallback; };
const root = execSync('git rev-parse --show-toplevel', { encoding: 'utf8' }).trim();
const out = arg('out', join(root, 'site', 'verify-out', 'showcase'));
const pieces = arg('pieces', Array.from({ length: 38 }, (_, i) => String(i + 1).padStart(3, '0')).join(',')).split(',');
mkdirSync(out, { recursive: true });

const dist = join(root, 'site', 'dist');
if (!existsSync(join(dist, 'index.html'))) throw new Error('site/dist/ is empty: run `bun run build` in site/');
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json',
  '.glb': 'model/gltf-binary', '.webp': 'image/webp', '.png': 'image/png', '.svg': 'image/svg+xml' };
const server = createServer((req, res) => {
  let path = decodeURIComponent(new URL(req.url, 'http://x').pathname);
  if (path === '/') path = '/index.html';
  const file = join(dist, path);
  if (!file.startsWith(dist) || !existsSync(file)) { res.writeHead(404).end(); return; }
  res.writeHead(200, { 'content-type': TYPES[extname(file)] ?? 'application/octet-stream' }).end(readFileSync(file));
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const base = `http://127.0.0.1:${server.address().port}`;

// An arrow key turns 0.2 rad: 8 presses ≈ profile (92°), 16 ≈ back.
const VIEWS = [['front', 0], ['profile', 8], ['back', 8]];
const browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
const page = await browser.newPage({ viewport: { width: 1000, height: 900 }, reducedMotion: 'reduce', deviceScaleFactor: arg('crop') === 'collar' ? 3 : 1 });
const errors = [];
page.on('pageerror', e => errors.push(String(e)));
const sheets = [];
try {
  for (const id of pieces) {
    await page.goto(`${base}/?look=${id}`);
    await page.waitForFunction(() => document.querySelector('#stage')?.getAttribute('aria-busy') === 'false', null, { timeout: 60_000 });
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(800);
    const canvas = page.locator('#stage canvas');
    await canvas.focus();
    const shots = [];
    for (const [name, presses] of VIEWS) {
      for (let i = 0; i < presses; i++) await canvas.press('ArrowLeft');
      await page.waitForTimeout(400);
      // Crop where the fit lives (top: torso to thighs; bottom: waist to feet); the stage buttons stay out.
      const box = await canvas.boundingBox();
      const top = Number(id) <= 15 ? .38 : .12;
      // --crop collar: neck and shoulders up close, to check the collar and the shoulder rest
      const clip = arg('crop') === 'collar'
        ? { x: box.x + box.width * .34, y: box.y + box.height * .17, width: box.width * .32, height: box.height * .2 }
        : { x: box.x + box.width * .3, y: box.y + box.height * top, width: box.width * .4, height: box.height * .5 };
      shots.push([name, (await page.screenshot({ clip })).toString('base64')]);
    }
    sheets.push([id, shots]);
    process.stdout.write(`${id} `);
  }
  // Lays the showcase out on a single page: one row per garment.
  const html = `<body style="margin:0;background:#f3f2ee;font:14px sans-serif">${sheets.map(([id, shots]) =>
    `<div style="display:flex;align-items:start"><b style="width:40px;padding:6px">${id}</b>${shots.map(([, b]) =>
      `<img src="data:image/png;base64,${b}" style="width:300px">`).join('')}</div>`).join('')}</body>`;
  const sheet = await browser.newPage({ viewport: { width: 940, height: 400 } });
  await sheet.setContent(html);
  await sheet.waitForTimeout(300);
  await sheet.screenshot({ path: join(out, 'showcase.png'), fullPage: true });
  for (const [id, shots] of sheets)
    shots.forEach(([name, b]) => writeFileSync(join(out, `${id}-${name}.png`), Buffer.from(b, 'base64')));
} finally {
  await browser.close();
  server.close();
}
console.log(`\n${sheets.length} garments in ${out}${errors.length ? `\nerrors:\n  ${errors.join('\n  ')}` : ''}`);
process.exit(errors.length ? 1 : 0);
