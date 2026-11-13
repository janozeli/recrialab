// Engine sheet: every garment as published next to the same garment rebuilt by the fit engine, from the front,
// in profile and from the back, with the thrift-store photo, on one self-contained page.
// Usage: node tools/verify-site/engine-sheet.mjs WORK [--pieces 016,019] [--out dir]
// WORK is the folder written by `python3 tools/fit/engine.py WORK`. Reads WORK/final/NNN-*.glb, WORK/low-B.glb,
// WORK/low-C.glb and WORK/report.json; writes OUT/index.html (engine-sheet.html with the data in it) and
// OUT/sheet.json (the numbers alone). Nothing is written to site/.
//
// Both sides are drawn by the same camera (orthographic, framed on the two garments together) and the same light,
// so a difference between the pictures is a difference between the garments. Per view the page also measures:
// - silhouette: area covered by only one of the two garments, as % of the area covered by either;
// - print: mean colour difference, 5 px blocks, texture without light, where both garments are;
// and draws the difference picture: cloth lost, cloth gained and print that changed.
// The published body is drawn with its triangle mask only (the site also clips waist, neck and sleeve per pixel),
// so the body may show at those lines on the published side; the two measures look at the garment alone.
import { createServer } from 'node:http';
import { execSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { extname, join, resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { chromium } = (() => {
  try { return require('playwright'); } catch {
    return require(join(execSync('npm root -g', { encoding: 'utf8' }).trim(), 'playwright'));
  }
})();
const arg = (name, fallback) => { const i = process.argv.indexOf(`--${name}`); return i > 0 ? process.argv[i + 1] : fallback; };
const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '..', '..');
if (!process.argv[2] || process.argv[2].startsWith('--')) throw new Error('usage: node tools/verify-site/engine-sheet.mjs WORK [--pieces 016,019] [--out dir]');
const work = resolve(process.argv[2]);
const out = resolve(arg('out', join(work, 'sheet')));
const pieces = arg('pieces', Array.from({ length: 38 }, (_, i) => String(i + 1).padStart(3, '0')).join(',')).split(',');
if (!existsSync(join(root, 'site', 'node_modules', 'three'))) throw new Error('three is missing: run `bun install --frozen-lockfile` in site/');
if (!existsSync(join(work, 'final'))) throw new Error(`${work}/final is missing: run \`python3 tools/fit/engine.py ${process.argv[2]}\` first`);
mkdirSync(out, { recursive: true });

// Picture size on the page, and the limits above which the page flags a view. They are the sheet's own, for
// pointing the eye; the engine's limits live in tools/fit.
const W = 300, H = 400, BLOCK = 5;
const FLAG = { silhouette: 18, print: 7, crossing: 2 };
const VIEWS = [['front', 0], ['profile', 90], ['back', 180]];

const catalog = readFileSync(join(root, 'site', 'catalog-data.ts'), 'utf8');
const names = Object.fromEntries([...catalog.matchAll(/id: "(\d{3})", name: "([^"]+)", slot: "(\w+)"/g)].map(m => [m[1], { name: m[2], slot: m[3] }]));
const poseC = new Set(JSON.parse(readFileSync(join(root, 'site', 'assets', 'body', 'poses.json'), 'utf8')).poseCBottomIds);
const report = existsSync(join(work, 'report.json')) ? JSON.parse(readFileSync(join(work, 'report.json'), 'utf8')) : { garments: {} };
const finals = readdirSync(join(work, 'final'));

const RENDER = `<!doctype html><meta charset="utf-8"><body style="margin:0">
<script type="importmap">{"imports":{"three":"/repo/site/node_modules/three/build/three.module.js","three/addons/":"/repo/site/node_modules/three/examples/jsm/"}}</script>
<script type="module">
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
const W = ${W}, H = ${H}, BLOCK = ${BLOCK};
const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(1); renderer.setSize(W * 2, H * 2);
renderer.outputColorSpace = THREE.SRGBColorSpace;
const loader = new GLTFLoader();
const flat = document.createElement('canvas'); flat.width = W; flat.height = H;
const ctx = flat.getContext('2d', { willReadFrequently: true }); ctx.imageSmoothingQuality = 'high';
const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, .01, 20);

async function load(url) { return (await loader.loadAsync(url)).scene; }
function matte(model) {
  model.traverse(n => { if (!n.isMesh) return;
    if (!n.geometry.attributes.normal) n.geometry.computeVertexNormals();
    for (const m of [n.material].flat()) { m.roughnessMap = null; m.metalnessMap = null; m.roughness = .9; m.metalness = 0; } });
}
function bodyMaterial(model, mask) {
  model.traverse(n => { if (!n.isMesh) return;
    n.material = new THREE.MeshStandardMaterial({ color: '#cbc5c0', roughness: 1, metalness: 0 });
    const entry = mask?.meshes.find(m => m.triangle_count === n.geometry.index.count / 3);
    if (!entry) return;
    // hidden_ranges are inclusive [start, end] triangle ranges (tools/fit/mask_io.py)
    const hidden = new Uint8Array(entry.triangle_count);
    for (const [a, b] of entry.hidden_ranges) hidden.fill(1, a, b + 1);
    const src = n.geometry.index.array, keep = [];
    for (let t = 0; t < entry.triangle_count; t++) if (!hidden[t]) keep.push(src[3 * t], src[3 * t + 1], src[3 * t + 2]);
    n.geometry.setIndex(keep);
  });
}
function scene(body, garments) {
  const s = new THREE.Scene();
  s.add(new THREE.HemisphereLight('#ffffff', '#667', 1.5));
  const key = new THREE.DirectionalLight('#ffffff', 1.7); s.add(key);
  s.add(body); const cloth = new THREE.Group(); garments.forEach(g => cloth.add(g)); s.add(cloth);
  // unlit twins: the texture as painted, for the silhouette and the print measure
  const lit = new Map(), unlit = new Map();
  cloth.traverse(n => { if (!n.isMesh) return; lit.set(n, n.material);
    const m = [n.material].flat()[0];
    unlit.set(n, new THREE.MeshBasicMaterial({ map: m.map, color: m.color, side: m.side })); });
  return { s, key, body, cloth, lit, unlit };
}
function shoot(sc, angle, plain) {
  const a = angle * Math.PI / 180;
  camera.position.set(camera.userData.c.x + Math.sin(a) * 5, camera.userData.c.y, camera.userData.c.z + Math.cos(a) * 5);
  camera.lookAt(camera.userData.c);
  sc.key.position.set(Math.sin(a + .5) * 3, 3.2, Math.cos(a + .5) * 3);
  sc.body.visible = !plain;
  for (const [n, m] of (plain ? sc.unlit : sc.lit)) n.material = m;
  renderer.setClearColor(plain ? '#000000' : '#eceae7', plain ? 0 : 1);
  renderer.render(sc.s, camera);
  ctx.clearRect(0, 0, W, H); ctx.drawImage(renderer.domElement, 0, 0, W, H);
  return plain ? ctx.getImageData(0, 0, W, H).data : flat.toDataURL('image/webp', .82);
}
// Silhouette and print of the engine garment (e) against the published one (o), and the difference picture.
function compare(o, e) {
  const img = ctx.createImageData(W, H), d = img.data;
  let only = 0, either = 0;
  for (let i = 0; i < W * H; i++) {
    const a = o[4 * i + 3] > 127, b = e[4 * i + 3] > 127, p = 4 * i;
    if (a || b) either++;
    if (a !== b) only++;
    if (b) { const g = 150 + (.3 * e[p] + .59 * e[p + 1] + .11 * e[p + 2]) * .38; d[p] = d[p + 1] = d[p + 2] = g; }
    else { d[p] = 246; d[p + 1] = 245; d[p + 2] = 243; }
    if (a && !b) { d[p] = 214; d[p + 1] = 40; d[p + 2] = 110; }
    if (b && !a) { d[p] = 28; d[p + 1] = 126; d[p + 2] = 214; }
    d[p + 3] = 255;
  }
  let sum = 0, blocks = 0, hot = 0;
  for (let by = 0; by < H; by += BLOCK) for (let bx = 0; bx < W; bx += BLOCK) {
    let n = 0; const so = [0, 0, 0], se = [0, 0, 0];
    for (let y = by; y < by + BLOCK; y++) for (let x = bx; x < bx + BLOCK; x++) {
      const p = 4 * (y * W + x);
      if (o[p + 3] > 127 && e[p + 3] > 127) { n++; for (let c = 0; c < 3; c++) { so[c] += o[p + c]; se[c] += e[p + c]; } }
    }
    if (n < BLOCK * BLOCK * .6) continue;
    const delta = (Math.abs(so[0] - se[0]) + Math.abs(so[1] - se[1]) + Math.abs(so[2] - se[2])) / 3 / n / 255;
    sum += delta; blocks++;
    const k = Math.min(1, Math.max(0, (delta - .08) / .22)); if (!k) continue;
    hot++;
    for (let y = by; y < by + BLOCK; y++) for (let x = bx; x < bx + BLOCK; x++) {
      const p = 4 * (y * W + x);
      d[p] += (240 - d[p]) * k; d[p + 1] += (140 - d[p + 1]) * k; d[p + 2] += (0 - d[p + 2]) * k;
    }
  }
  ctx.putImageData(img, 0, 0);
  return { diff: flat.toDataURL('image/webp', .82), silhouette: either ? +(100 * only / either).toFixed(1) : 0,
    print: blocks ? +(100 * sum / blocks).toFixed(1) : 0, printArea: blocks ? +(100 * hot / blocks).toFixed(1) : 0 };
}
window.renderPiece = async job => {
  const [bodyNow, bodyEngine, now, mask, ...parts] = await Promise.all([load(job.bodyNow), load(job.bodyEngine), load(job.now),
    fetch(job.mask).then(r => r.ok ? r.json() : null), ...job.parts.map(load)]);
  matte(now); parts.forEach(matte); bodyMaterial(bodyNow, mask); bodyMaterial(bodyEngine, null);
  const A = scene(bodyNow, [now]), B = scene(bodyEngine, parts);
  const box = new THREE.Box3().setFromObject(A.cloth).union(new THREE.Box3().setFromObject(B.cloth));
  const size = box.getSize(new THREE.Vector3()), c = box.getCenter(new THREE.Vector3());
  const h = Math.max(size.y, Math.max(size.x, size.z) * H / W) * 1.1;
  camera.top = h / 2; camera.bottom = -h / 2; camera.right = h * W / H / 2; camera.left = -camera.right;
  camera.updateProjectionMatrix(); camera.userData.c = c;
  const views = {};
  for (const [name, angle] of job.views) {
    const o = shoot(A, angle, true), e = shoot(B, angle, true);
    views[name] = { ...compare(new Uint8ClampedArray(o), new Uint8ClampedArray(e)), now: shoot(A, angle, false), engine: shoot(B, angle, false) };
  }
  const photo = await createImageBitmap(await (await fetch(job.photo)).blob());
  const ph = 400, pw = Math.round(ph * photo.width / photo.height), pc = Object.assign(document.createElement('canvas'), { width: pw, height: ph });
  pc.getContext('2d').drawImage(photo, 0, 0, pw, ph);
  for (const sc of [A, B]) sc.s.traverse(n => { if (!n.isMesh) return; n.geometry.dispose();
    for (const m of [n.material].flat()) { m.map?.dispose(); m.dispose(); } });
  return { views, photo: pc.toDataURL('image/webp', .8), height: +h.toFixed(3) };
};
document.title = 'ready';
</script>`;

const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.json': 'application/json', '.glb': 'model/gltf-binary', '.webp': 'image/webp' };
const MOUNTS = { '/repo/': root, '/work/': work };
const server = createServer((req, res) => {
  const path = decodeURIComponent(new URL(req.url, 'http://x').pathname);
  if (path === '/') { res.writeHead(200, { 'content-type': 'text/html' }).end(RENDER); return; }
  const mount = Object.keys(MOUNTS).find(m => path.startsWith(m));
  const file = mount && join(MOUNTS[mount], path.slice(mount.length));
  if (!file || !file.startsWith(MOUNTS[mount]) || !existsSync(file)) { res.writeHead(404).end(); return; }
  res.writeHead(200, { 'content-type': TYPES[extname(file)] ?? 'application/octet-stream' }).end(readFileSync(file));
});
await new Promise(done => server.listen(0, '127.0.0.1', done));

const browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
const page = await browser.newPage({ viewport: { width: 700, height: 900 } });
const errors = [];
page.on('pageerror', e => errors.push(String(e)));
const garments = [];
try {
  await page.goto(`http://127.0.0.1:${server.address().port}/`);
  await page.waitForFunction(() => document.title === 'ready', null, { timeout: 60_000 });
  for (const id of pieces) {
    const parts = finals.filter(f => f.startsWith(`${id}-`) && f.endsWith('.glb')).sort();
    if (!parts.length) { errors.push(`${id}: no part in ${work}/final`); continue; }
    const pose = poseC.has(id) ? 'c' : 'b';
    const shot = await page.evaluate(job => window.renderPiece(job), {
      bodyNow: `/repo/site/assets/body/pose-${pose}.glb`, bodyEngine: `/work/low-${pose.toUpperCase()}.glb`,
      now: `/repo/site/assets/garments/${id}.glb`, mask: `/repo/site/assets/masks/pose-${pose}/${id}.json`,
      photo: `/repo/site/assets/photos/${id}.webp`, parts: parts.map(f => `/work/final/${f}`), views: VIEWS });
    const r = report.garments[id] ?? {};
    const measures = { identity: r.shell?.identity ?? null, crossing: r.body_crossing_pct ?? null, triangles: r.triangles ?? null,
      before: r.before ?? null, registered: r.registered ?? null };
    const flags = [];
    for (const [view] of VIEWS) {
      if (shot.views[view].silhouette > FLAG.silhouette) flags.push(`silhouette:${view}`);
      if (shot.views[view].print > FLAG.print) flags.push(`print:${view}`);
    }
    if (measures.crossing > FLAG.crossing) flags.push('crossing');
    garments.push({ id, ...(names[id] ?? { name: id, slot: Number(id) <= 15 ? 'bottom' : 'top' }), parts: parts.map(f => f.slice(4, -4)), ...shot, measures, flags });
    process.stdout.write(`${id} `);
  }
} finally {
  await browser.close();
  server.close();
}

const commit = (() => { try { return execSync('git rev-parse --short HEAD', { cwd: root, encoding: 'utf8' }).trim(); } catch { return ''; } })();
const data = { made: new Date().toISOString(), commit, limits: FLAG, summary: report.summary ?? null, lines: report.lines ?? null, garments };
const template = readFileSync(join(here, 'engine-sheet.html'), 'utf8');
if (!template.includes('__SHEET_DATA__')) throw new Error('engine-sheet.html lost its __SHEET_DATA__ placeholder');
writeFileSync(join(out, 'index.html'), template.replace('__SHEET_DATA__', () => JSON.stringify(data).replaceAll('<', '\\u003c')));
const strip = g => ({ ...g, photo: undefined, views: Object.fromEntries(Object.entries(g.views).map(([k, v]) => [k, { silhouette: v.silhouette, print: v.print, printArea: v.printArea }])) });
writeFileSync(join(out, 'sheet.json'), JSON.stringify({ ...data, garments: garments.map(strip) }, null, 1));

const flagged = garments.filter(g => g.flags.length);
console.log(`\n${garments.length} garments in ${join(out, 'index.html')}; ${flagged.length} flagged`);
for (const g of flagged) console.log(`  ${g.id} ${g.flags.join(' ')}`);
if (errors.length) console.log(`errors:\n  ${errors.join('\n  ')}`);
process.exit(errors.length || garments.length !== pieces.length ? 1 : 0);
