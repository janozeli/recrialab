// Visual QA: photographs each look from every point of the site orbit (from below and above too) with the site's
// masks and layers, and saves per view the class mask (body, top, bottom, inside out), the garment depth, the unlit
// texture and the torso in view at the waist. tools/visual-qa/measure.py measures what looks wrong.
// Usage: node tools/verify-site/visual-qa.mjs [--looks 016,004.016] [--plan all|ci|pairs] [--changed 008,001.016] [--part 0/4] [--out dir] [--beauty]
// Serves site/dist/ (run `bun run build` first). Writes NNN/view.cls, .depth.gz (garment depth), .body.gz (whole body, no mask) and .albedo.jpg, measures.json and, with --beauty,
// the lit picture of each view as JPEG to compare by eye with the thrift-shop photos.
import { createServer } from 'node:http';
import { execSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { extname, join } from 'node:path';
import { gzipSync } from 'node:zlib';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const { chromium } = (() => {
  try { return require('playwright'); } catch {
    return require(join(execSync('npm root -g', { encoding: 'utf8' }).trim(), 'playwright'));
  }
})();
const arg = (name, fallback) => { const i = process.argv.indexOf(`--${name}`); return i > 0 ? process.argv[i + 1] : fallback; };
// the repository this script sits in (also the temporary copy calibration.py makes, which has no .git)
const root = fileURLToPath(new URL('../..', import.meta.url)).replace(/\/$/, '');
const out = arg('out', join(root, 'site', 'verify-out', 'visual-qa'));
const beauty = process.argv.includes('--beauty');
mkdirSync(out, { recursive: true });

const ids = n => Array.from({ length: n }, (_, i) => String(i + 1).padStart(3, '0'));
const BOTTOMS = ids(15), TOPS = ids(38).slice(15);
/** Look plan: each garment alone and each one with contrasting garments of the other group. */
export function plan(name) {
  const looks = new Set();
  if (name === 'ci') {
    // CI: each bottom alone (waistband, hem, dark patch) and each top over a bottom (where the two meet).
    BOTTOMS.forEach(b => looks.add(b));
    TOPS.forEach((c, i) => looks.add(`${BOTTOMS[i % BOTTOMS.length]}.${c}`));
    return [...looks];
  }
  if (name === 'pairs') { for (const b of BOTTOMS) for (const c of TOPS) looks.add(`${b}.${c}`); return [...looks]; }
  for (const id of [...BOTTOMS, ...TOPS]) looks.add(id);
  for (const c of TOPS) for (const b of ['004', '008', '009', '013']) looks.add(`${b}.${c}`);
  for (const b of BOTTOMS) for (const c of ['016', '031', '028', '038']) looks.add(`${b}.${c}`);
  return [...looks];
}
// --changed 008,001.016: only the plan's looks with those garments or pairs (site/ci-filter.ts says what the PR changed)
const changed = arg('changed') ? new Set(arg('changed').split(',')) : null;
const all = (arg('looks') ? arg('looks').split(',') : plan(arg('plan', 'all')))
  .filter(l => !changed || changed.has(l) || l.split('.').some(p => changed.has(p)));
// --part i/n: one of n processes (software WebGL uses one core per browser)
const [part, parts] = arg('part', '0/1').split('/').map(Number);
const looks = all.filter((_, i) => i % parts === part);

// The site orbit angles (dressup.ts), from 22° above to 22° below the chest, at a fixed reference distance: target at
// 1.0 m, camera at 4.4 m. The site's own framing and zoom may change; the measure stays comparable with its baselines.
const VIEWS = [
  ...[0, 45, 90, 135, 180, 225, 270, 315].map(az => ({ name: `eye-${az}`, az, polar: 88 })),
  ...[0, 90, 180, 270].map(az => ({ name: `low-${az}`, az, polar: 111.6 })),
  ...[0, 180].map(az => ({ name: `high-${az}`, az, polar: 68.4 })),
];
const W = 720, H = 1200;

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

/** Runs in the page: photographs the views and measures each one on the class mask. */
async function photograph({ views, W, H, beauty }) {
  const { THREE, scene, camera, controls, renderer, worn, mannequin, followCamera, bodyGeometry, qaSleeve } = window.__qa;
  // Classes: 0 background, 1 body, 2 top (right side), 3 top (inside out), 4 bottom (right side), 5 bottom (inside out).
  const COLOURS = [[0, 0, 0], [255, 0, 0], [0, 255, 0], [0, 255, 255], [0, 0, 255], [255, 0, 255]];
  const garmentMat = (front, back, side) => new THREE.ShaderMaterial({
    side,
    vertexShader: 'void main(){gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);}',
    fragmentShader: `void main(){gl_FragColor=gl_FrontFacing?vec4(${front.map(c => (c / 255).toFixed(1))},1.):vec4(${back.map(c => (c / 255).toFixed(1))},1.);}`,
  });
  const meshes = (object) => { const list = []; object?.traverse(n => { if (n.isMesh && n.visible) list.push(n); }); return list; };
  const tops = meshes(worn.get('top')?.object), bottoms = meshes(worn.get('bottom')?.object);
  const body = meshes(mannequin);
  const lights = []; scene.traverse(n => { if (n.isLight) lights.push(n); });
  const canvas = renderer.domElement;
  const size = renderer.getSize(new THREE.Vector2());
  const pixelRatio = renderer.getPixelRatio();
  renderer.setPixelRatio(1);
  renderer.setSize(W, H, false);
  const cam = camera.clone();
  cam.aspect = W / H;
  cam.updateProjectionMatrix();
  const target = new THREE.Vector3(0, 1, 0);
  const radius = Math.hypot(.15, 4.4);
  const gl = renderer.getContext();
  const buf = new Uint8Array(W * H * 4), posBuf = new Uint8Array(W * H * 4), depthBuf = new Uint8Array(W * H * 4), wholeBuf = new Uint8Array(W * H * 4),
    sleeveBuf = new Uint8Array(W * H * 4);
  // Garment depth (distance to the camera, from DEPTH0 in steps of DEPTH m; 0 = no garment): tells a hole in a single
  // sheet from the gap between two surfaces (one leg in front of the other).
  const DEPTH0 = 3.4, DEPTH = 0.008;
  const depthMat = new THREE.ShaderMaterial({
    side: THREE.DoubleSide,
    vertexShader: 'varying float vD; void main(){vec4 p=modelViewMatrix*vec4(position,1.);vD=-p.z;gl_Position=projectionMatrix*p;}',
    fragmentShader: `varying float vD; void main(){gl_FragColor=vec4(clamp(floor((vD-${DEPTH0.toFixed(1)})/${DEPTH}+.5),1.,255.)/255.,0.,0.,1.);}`,
  });
  const posMat = new THREE.ShaderMaterial({
    vertexShader: 'varying vec3 vW; void main(){vec4 w=modelMatrix*vec4(position,1.);vW=w.xyz;gl_Position=projectionMatrix*viewMatrix*w;}',
    fragmentShader: 'varying vec3 vW; void main(){gl_FragColor=vec4(min(abs(vW.x)*2.,1.),min(vW.y/2.,1.),1.,1.);}',
  });
  const ARM_X = 0.17, ARM_Y0 = 0.9, ARM_Y1 = 1.4;
  const result = [];
  // World height of an image row, on the mannequin plane (holds for the view at chest height).
  const metersPerPx = 2 * radius * Math.tan(THREE.MathUtils.degToRad(cam.fov / 2)) / H;
  for (const v of views) {
    const polar = THREE.MathUtils.degToRad(v.polar), az = THREE.MathUtils.degToRad(v.az);
    const pos = new THREE.Vector3(Math.sin(polar) * Math.sin(az), Math.cos(polar), Math.sin(polar) * Math.cos(az)).multiplyScalar(radius).add(target);
    camera.position.copy(pos);
    camera.lookAt(target);
    followCamera();
    cam.position.copy(pos);
    cam.lookAt(target);
    let jpeg = null, albedo = null;
    {
      // Unlit pass: only the garments' texture, to find a dark patch the thrift-shop photo does not have.
      const background = scene.background, mats = new Map(), saved = [...tops, ...bottoms].map(m => m.material);
      scene.background = new THREE.Color(0, 0, 0);
      body.forEach(m => { m.visible = false; });
      [...tops, ...bottoms].forEach(m => {
        const orig = [m.material].flat()[0];
        if (!mats.has(orig)) mats.set(orig, new THREE.MeshBasicMaterial({ map: orig.map, color: orig.map ? 0xffffff : orig.color, side: orig.side }));
        m.material = mats.get(orig);
      });
      const tm = renderer.toneMapping;
      renderer.toneMapping = THREE.NoToneMapping;
      renderer.render(scene, cam);
      albedo = canvas.toDataURL('image/jpeg', 0.9);
      renderer.toneMapping = tm;
      [...tops, ...bottoms].forEach((m, i) => { m.material = saved[i]; });
      body.forEach(m => { m.visible = true; });
      mats.forEach(m => m.dispose());
      scene.background = background;
    }
    if (beauty) {
      const background = scene.background;
      scene.background = new THREE.Color(0.55, 0.55, 0.58);
      renderer.render(scene, cam);
      scene.background = background;
      jpeg = canvas.toDataURL('image/jpeg', 0.85);
    }
    // Class pass: body with the site material (keeps the per-pixel clip), emissive only; flat garments.
    const kept = { toneMapping: renderer.toneMapping, background: scene.background,
      lights: lights.map(l => l.intensity), body: body.map(m => [m.material.color.clone(), m.material.emissive.clone(), m.material.envMapIntensity]),
      garments: [...tops, ...bottoms].map(m => m.material) };
    renderer.toneMapping = THREE.NoToneMapping;
    scene.background = new THREE.Color(0, 0, 0);
    lights.forEach(l => { l.intensity = 0; });
    for (const m of body) { m.material.color.setRGB(0, 0, 0); m.material.emissive.setRGB(1, 0, 0); m.material.envMapIntensity = 0; }
    const mats = new Map();
    const paint = (list, front, back) => list.forEach(m => {
      const side = [m.material].flat()[0].side;
      const key = `${front}${side}`;
      if (!mats.has(key)) mats.set(key, garmentMat(front, back, side));
      m.material = mats.get(key);
    });
    paint(tops, COLOURS[2], COLOURS[3]);
    paint(bottoms, COLOURS[4], COLOURS[5]);
    renderer.render(scene, cam);
    gl.readPixels(0, 0, W, H, gl.RGBA, gl.UNSIGNED_BYTE, buf);
    // Sleeve pass: the same render, with the body writing how far each pixel lies above the sleeve line of the worn top
    // (the site's own line, band and clip): the arm left in view over the sleeve.
    qaSleeve.value = 1;
    renderer.render(scene, cam);
    gl.readPixels(0, 0, W, H, gl.RGBA, gl.UNSIGNED_BYTE, sleeveBuf);
    qaSleeve.value = 0;
    // Second pass: where each body pixel is in the world (|x| and height), to tell the torso from the arm.
    const bodyMats = body.map(m => m.material);
    body.forEach(m => { m.material = posMat; });
    renderer.render(scene, cam);
    gl.readPixels(0, 0, W, H, gl.RGBA, gl.UNSIGNED_BYTE, posBuf);
    body.forEach((m, i) => { m.material = bodyMats[i]; });
    // Third pass: depth of the garments only (the hidden body does not cover the garment where the class is garment).
    const garmentMats = [...tops, ...bottoms].map(m => m.material);
    body.forEach(m => { m.visible = false; });
    [...tops, ...bottoms].forEach(m => { m.material = depthMat; });
    renderer.render(scene, cam);
    gl.readPixels(0, 0, W, H, gl.RGBA, gl.UNSIGNED_BYTE, depthBuf);
    [...tops, ...bottoms].forEach((m, i) => { m.material = garmentMats[i]; });
    body.forEach(m => { m.visible = true; });
    // Fourth pass: the whole body, without the mask, without garments, with its world position: background in view where
    // the body should be is a real hole (hidden body and open garment); outside it, it is the gap between arm and torso or
    // between the legs. On the arm, it is the arm clipped with nothing behind it (the slit under the sleeve).
    const geo = (bodyGeometry ?? []).filter(b => b.mesh.visible && body.includes(b.mesh));
    const keptIdx = geo.map(b => [b.mesh.geometry.index.array.slice(), { ...b.mesh.geometry.drawRange }, b.mesh.material]);
    geo.forEach(b => { b.mesh.geometry.index.array.set(b.original); b.mesh.geometry.index.needsUpdate = true; b.mesh.geometry.setDrawRange(0, b.original.length); b.mesh.material = posMat; });
    [...tops, ...bottoms].forEach(m => { m.visible = false; });
    renderer.render(scene, cam);
    gl.readPixels(0, 0, W, H, gl.RGBA, gl.UNSIGNED_BYTE, wholeBuf);
    [...tops, ...bottoms].forEach(m => { m.visible = true; });
    geo.forEach((b, i) => { b.mesh.geometry.index.array.set(keptIdx[i][0]); b.mesh.geometry.index.needsUpdate = true; b.mesh.geometry.setDrawRange(keptIdx[i][1].start, keptIdx[i][1].count); b.mesh.material = keptIdx[i][2]; });
    // put everything back as it was
    renderer.toneMapping = kept.toneMapping;
    scene.background = kept.background;
    lights.forEach((l, i) => { l.intensity = kept.lights[i]; });
    body.forEach((m, i) => { m.material.color.copy(kept.body[i][0]); m.material.emissive.copy(kept.body[i][1]); m.material.envMapIntensity = kept.body[i][2]; });
    [...tops, ...bottoms].forEach((m, i) => { m.material = kept.garments[i]; });
    mats.forEach(m => m.dispose());

    // class per pixel (row 0 = top of the image)
    const cls = new Uint8Array(W * H), torso = new Uint8Array(W * H), depth = new Uint8Array(W * H), whole = new Uint8Array(W * H);
    for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
      const o = ((H - 1 - y) * W + x) * 4;
      let best = 0, bd = 1e9;
      for (let c = 0; c < COLOURS.length; c++) {
        const d = (buf[o] - COLOURS[c][0]) ** 2 + (buf[o + 1] - COLOURS[c][1]) ** 2 + (buf[o + 2] - COLOURS[c][2]) ** 2;
        if (d < bd) { bd = d; best = c; }
      }
      cls[y * W + x] = best;
      depth[y * W + x] = depthBuf[o];
      // 1: body; 2: arm between the elbow and the armpit (|x| > ARM_X, from ARM_Y0 to ARM_Y1), where the sleeve clip acts
      const wx = wholeBuf[o] / 255 / 2, wy = wholeBuf[o + 1] / 255 * 2;
      whole[y * W + x] = wholeBuf[o + 2] < 128 ? 0 : wx > ARM_X && wy > ARM_Y0 && wy < ARM_Y1 ? 2 : 1;
      // 3 and up: the arm in view above the sleeve line of the worn top (body pixel of the class pass), 3 + cm above it
      if (best === 1 && sleeveBuf[o] > 128 && sleeveBuf[o + 2] > 128) whole[y * W + x] = 3 + Math.round(sleeveBuf[o + 1] / 255 * 50);
      // torso in view in the waist band (0.85 to 1.25 m), away from the arms (|x| < 0.16 m)
      const q = ((H - 1 - y) * W + x) * 4;
      if (best === 1 && posBuf[q] / 255 / 2 < 0.16 && posBuf[q + 1] / 255 * 2 > 0.85 && posBuf[q + 1] / 255 * 2 < 1.25) torso[y * W + x] = 1;
    }
    result.push({ view: v, jpeg, albedo, measures: measure(cls, torso), mask: b64(rle(cls)), depth: b64(depth), whole: b64(whole) });
  }
  renderer.setPixelRatio(pixelRatio);
  renderer.setSize(size.x, size.y, false);
  controls.update();
  depthMat.dispose();
  return { result, metersPerPx };

  function b64(bytes) {
    let s = '';
    for (let i = 0; i < bytes.length; i += 8192) s += String.fromCharCode(...bytes.slice(i, i + 8192));
    return btoa(s);
  }
  // Simple RLE of the mask for Node to draw the diagnostic images.
  function rle(cls) {
    const outb = [];
    for (let i = 0; i < cls.length;) {
      let j = i; while (j < cls.length && cls[j] === cls[i] && j - i < 255) j++;
      outb.push(cls[i], j - i); i = j;
    }
    return outb;
  }

  // The other measures come from tools/visual-qa/measure.py, on the saved masks; here only what needs the world position.
  function measure(cls, torso) {
    const area = [0, 0, 0, 0, 0, 0];
    for (let i = 0; i < W * H; i++) area[cls[i]]++;
    // midriff: torso in view in the waist band, only when there is a top and a bottom
    let midriff = 0;
    if (area[2] + area[3] > 0 && area[4] + area[5] > 0) for (let i = 0; i < W * H; i++) midriff += torso[i];
    return { area: { body: area[1], top: area[2], topBack: area[3], bottom: area[4], bottomBack: area[5] }, midriff };
  }
}

const browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
const page = await browser.newPage({ viewport: { width: 500, height: 900 }, deviceScaleFactor: 2, reducedMotion: 'reduce' });
const errors = [];
page.on('pageerror', e => errors.push(String(e)));
const rows = [];
try {
  for (const look of looks) {
    await page.goto(`${base}/?look=${look}&qa=1`);
    await page.waitForFunction(() => document.querySelector('#stage')?.getAttribute('aria-busy') === 'false' && window.__qa, null, { timeout: 120_000 });
    // the look restored from the link finishes dressing after the mannequin is ready
    const expected = look.split('.').sort().join('.');
    await page.waitForFunction(e => [...window.__qa.worn.values()].map(w => w.piece.id).sort().join('.') === e, expected, { timeout: 120_000 })
      .catch(async () => { throw new Error(`look ${look} opened with ${await page.evaluate(() => [...window.__qa.worn.keys()].join('.'))}`); });
    await page.waitForLoadState('networkidle');
    const { result, metersPerPx } = await page.evaluate(photograph, { views: VIEWS, W, H, beauty });
    mkdirSync(join(out, look), { recursive: true });
    for (const r of result) {
      writeFileSync(join(out, look, `${r.view.name}.albedo.jpg`), Buffer.from(r.albedo.split(',')[1], 'base64'));
      if (r.jpeg) writeFileSync(join(out, look, `${r.view.name}.jpg`), Buffer.from(r.jpeg.split(',')[1], 'base64'));
      writeFileSync(join(out, look, `${r.view.name}.cls`), Buffer.from(r.mask, 'base64'));
      writeFileSync(join(out, look, `${r.view.name}.depth.gz`), gzipSync(Buffer.from(r.depth, 'base64')));
      writeFileSync(join(out, look, `${r.view.name}.body.gz`), gzipSync(Buffer.from(r.whole, 'base64')));
      rows.push({ look, view: r.view.name, metersPerPx, ...r.measures });
    }
    process.stdout.write(`${look} `);
  }
} finally {
  writeFileSync(join(out, parts > 1 ? `measures-${part}.json` : 'measures.json'), JSON.stringify({ W, H, rows }, null, 1));
  await browser.close();
  server.close();
}
console.log(`\n${looks.length} looks in ${out}${errors.length ? `\nerrors:\n  ${errors.join('\n  ')}` : ''}`);
process.exit(errors.length ? 1 : 0);
