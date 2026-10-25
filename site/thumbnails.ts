// Renders the selector thumbnails from the GLBs themselves, with the light and material of the stage (fabric.ts).
// Usage (in site/): bun thumbnails.ts          redoes only the stale thumbnails (GLB, tone or renderer changed)
//                   bun thumbnails.ts --all    redoes all 38
// thumbnails.lock.json records the GLB, tone and renderer of each thumbnail; thumbnails.test.ts fails a stale one.
import { createHash } from 'node:crypto';
import { execSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync, writeFileSync, existsSync, mkdirSync } from 'node:fs';
import { createRequire } from 'node:module';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { CATALOG } from './catalog-data';
import { TONE } from './garment-tones';

const SITE = new URL('.', import.meta.url).pathname;
export const THUMBS = join(SITE, 'assets', 'thumbnails');
export const LOCK = join(SITE, 'thumbnails.lock.json');
/** What changes the rendering of every thumbnail. */
const RENDERER = ['fabric.ts', 'thumbnail-render.ts', 'thumbnail-render.html'];

export type Lock = { renderer: string; pieces: Record<string, { glb: string; tone: number }> };
const sha = (bytes: Buffer | string) => createHash('sha256').update(bytes).digest('hex');
export const glbPath = (id: string) => join(SITE, 'assets', 'garments', `${id}.glb`);
export const thumbPath = (id: string) => join(THUMBS, `${id}.webp`);

/** The lock the thumbnails would have if rendered now. */
export function currentLock(): Lock {
  const pieces: Lock['pieces'] = {};
  for (const { id } of CATALOG) pieces[id] = { glb: sha(readFileSync(glbPath(id))), tone: TONE[id] ?? 1 };
  return { renderer: sha(RENDERER.map(f => readFileSync(join(SITE, f), 'utf8')).join('\0')), pieces };
}

export function staleThumbnails(saved: Lock | null, now: Lock): string[] {
  return Object.keys(now.pieces).filter(id => !saved || saved.renderer !== now.renderer || !existsSync(thumbPath(id))
    || JSON.stringify(saved.pieces[id]) !== JSON.stringify(now.pieces[id]));
}

if (import.meta.main) {
  const now = currentLock();
  const saved: Lock | null = existsSync(LOCK) ? JSON.parse(readFileSync(LOCK, 'utf8')) : null;
  const ids = process.argv.includes('--all') ? Object.keys(now.pieces) : staleThumbnails(saved, now);
  if (!ids.length) { console.log('thumbnails up to date'); process.exit(0); }

  const build = mkdtempSync(join(tmpdir(), 'thumbnails-'));
  const result = await Bun.build({ entrypoints: [join(SITE, 'thumbnail-render.html')], outdir: build });
  if (!result.success) throw new AggregateError(result.logs, 'build of the thumbnail page failed');
  const server = Bun.serve({
    port: 0, hostname: '127.0.0.1',
    fetch(req) {
      const path = new URL(req.url).pathname;
      const glb = path.match(/^\/glb\/(\d{3})$/);
      if (glb) return new Response(Bun.file(glbPath(glb[1])));
      const file = join(build, path === '/' ? 'thumbnail-render.html' : path);
      return file.startsWith(build) && existsSync(file) ? new Response(Bun.file(file)) : new Response(null, { status: 404 });
    },
  });
  // The project's Playwright or the global one, as in tools/verify-site/drive.mjs.
  const require = createRequire(import.meta.url);
  const { chromium } = (() => {
    try { return require('playwright'); } catch {
      return require(join(execSync('npm root -g', { encoding: 'utf8' }).trim(), 'playwright'));
    }
  })();
  const browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  try {
    const page = await browser.newPage();
    const errors: string[] = [];
    page.on('pageerror', (e: Error) => errors.push(String(e)));
    await page.goto(`http://127.0.0.1:${server.port}/`);
    await page.waitForFunction(() => 'renderThumbnail' in window);
    mkdirSync(THUMBS, { recursive: true });
    const lock: Lock = { renderer: now.renderer, pieces: { ...(saved?.renderer === now.renderer ? saved.pieces : {}) } };
    for (const id of ids) {
      const url: string = await page.evaluate(([id, url]: string[]) =>
        (window as unknown as { renderThumbnail: (id: string, url: string) => Promise<string> }).renderThumbnail(id, url), [id, `/glb/${id}`]);
      if (!url.startsWith('data:image/webp;base64,')) throw new Error(`${id}: the browser did not produce WebP`);
      writeFileSync(thumbPath(id), Buffer.from(url.slice(url.indexOf(',') + 1), 'base64'));
      lock.pieces[id] = now.pieces[id];
      console.log(`thumbnail ${id}`);
    }
    if (errors.length) throw new Error(errors.join('\n'));
    const sorted: Lock = { renderer: lock.renderer, pieces: Object.fromEntries(Object.entries(lock.pieces).sort()) };
    writeFileSync(LOCK, JSON.stringify(sorted, null, 1) + '\n');
  } finally {
    await browser.close();
    server.stop(true);
    rmSync(build, { recursive: true, force: true });
  }
}
