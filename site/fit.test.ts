// Fit of the garments on the mannequin, measured on the shipped GLBs.
// Posture of the bottoms: a piece must not lean forward or back relative to the body, measured as the pitch
// (degrees) of the front/back axis between waistband and hem, piece against body over the same band.
import { test, expect } from 'bun:test';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { readMesh, readPositions } from './glb';
import { flyLiningVisibleCm2, MAX_FLY_LINING_CM2 } from './fly';
import { CATALOG } from './catalog-data';
import { bodyPoseForBottom } from './body-poses';
import { knownIssues } from './known-issues';

const ASSETS = new URL('./assets/', import.meta.url).pathname;
const MAX_PITCH_DEGREES = 5;
const positions = (file: string) => readPositions(readFileSync(join(ASSETS, file)));

/** Front/back centre of a 2 cm slice; the arms and hands of the body are left out. */
function middleZ(p: Float32Array, y: number): number | null {
  let min = Infinity, max = -Infinity, count = 0;
  for (let i = 0; i < p.length; i += 3) {
    if (Math.abs(p[i + 1] - y) > 0.01 || (p[i + 1] > 0.6 && Math.abs(p[i]) > 0.19)) continue;
    min = Math.min(min, p[i + 2]); max = Math.max(max, p[i + 2]); count++;
  }
  return count > 5 ? (min + max) / 2 : null;
}

function pitch(p: Float32Array, low: number, high: number): number {
  let sy = 0, sz = 0, syy = 0, syz = 0, n = 0;
  for (let y = low; y <= high; y += 0.01) {
    const z = middleZ(p, y);
    if (z === null) continue;
    sy += y; sz += z; syy += y * y; syz += y * z; n++;
  }
  return Math.atan((n * syz - sy * sz) / (n * syy - sy * sy)) * 180 / Math.PI;
}

const body = positions('body/pose-b.glb');
const bottoms = CATALOG.filter(p => p.slot === 'bottom' && bodyPoseForBottom(p.id) === 'B').map(p => p.id);

test('bottoms on body B hang with the body, not leaning forward or back', () => {
  const off: string[] = [];
  for (const id of bottoms) {
    const garment = positions(`garments/${id}.glb`);
    let top = -Infinity, bottom = Infinity;
    for (let i = 1; i < garment.length; i += 3) { top = Math.max(top, garment[i]); bottom = Math.min(bottom, garment[i]); }
    const delta = pitch(garment, bottom + 0.03, top - 0.05) - pitch(body, bottom + 0.03, top - 0.05);
    if (Math.abs(delta) > MAX_PITCH_DEGREES) off.push(`${id}: ${delta.toFixed(1)}°`);
  }
  expect(off).toEqual([]);
});

// Waistband at the waist, measured at the middle of the front and of the back (|x| < 3 cm): the highest point of the
// piece. Skirt 010 sits on the hips, 7 to 12 cm below the others, and is held at its recorded baseline while its known
// issue is open: raising it with the current tools leaves the waistband loose or stretches the print.
const MIN_WAIST_Y = 0.95;
const WAIST_AS_SHIPPED: Record<string, number> = { '010': 0.90 };
test('bottoms sit at the waist, not down on the hips', () => {
  const low: string[] = [];
  for (const p of CATALOG.filter(p => p.slot === 'bottom')) {
    const g = positions(`garments/${p.id}.glb`);
    let front = -Infinity, back = -Infinity;
    for (let i = 0; i < g.length; i += 3) {
      if (Math.abs(g[i]) >= 0.03) continue;
      if (g[i + 2] > 0) front = Math.max(front, g[i + 1]); else back = Math.max(back, g[i + 1]);
    }
    const mid = (front + back) / 2;
    if (mid < (WAIST_AS_SHIPPED[p.id] ?? MIN_WAIST_Y)) low.push(`${p.id}: waistband at ${mid.toFixed(2)} m (front ${front.toFixed(2)}, back ${back.toFixed(2)})`);
  }
  expect(low).toEqual([]);
});

// Tops rest on the shoulders (they are generated on a mannequin with higher shoulders: tools/fit/drape.py and
// shoulder.py bring them down). Measured per |x| band near the body plane, from the base of the collar to the shoulder
// tip: top of the piece minus top of the body in the same band. Negative = the piece sank into the shoulder.
// Knits (016–032) have no structured shoulder: up to 4.5 cm in each band and 3.5 cm on average. Jackets (033–038): up
// to 5 cm.
const SHOULDER_BANDS = [[.12, .16], [.16, .20], [.20, .24]];
const MAX_KNIT_SHOULDER_GAP_CM = 4.5;
const MAX_KNIT_SHOULDER_MEAN_CM = 3.5;
const MAX_SHOULDER_GAP_CM = 5;
// on hoodie 037 the inner shoulder band is the fallen hood, which stands up; the outer shoulder rests on the body
const HOOD_SHOULDER_GAP_CM: Record<string, number> = { '037': 6.5 };
const JACKETS = new Set(['033', '034', '035', '036', '037', '038']);
function shoulderTops(p: Float32Array): number[] {
  return SHOULDER_BANDS.map(([lo, hi]) => {
    let top = -Infinity, count = 0;
    for (let i = 0; i < p.length; i += 3) {
      const x = Math.abs(p[i]);
      if (x >= lo && x < hi && Math.abs(p[i + 2]) < 0.06 && p[i + 1] > 1.3) { top = Math.max(top, p[i + 1]); count++; }
    }
    if (count < 10) throw new Error(`shoulder band ${lo}–${hi} has no vertices: the check measures nothing`);
    return top;
  });
}
const tops = CATALOG.filter(p => p.slot === 'top').map(p => p.id);

test('tops rest on the shoulders, from the collar to the shoulder tip, without sinking into them', () => {
  const body = shoulderTops(positions('body/pose-b.glb'));
  const off: string[] = [];
  for (const id of tops) {
    const max = HOOD_SHOULDER_GAP_CM[id] ?? (JACKETS.has(id) ? MAX_SHOULDER_GAP_CM : MAX_KNIT_SHOULDER_GAP_CM);
    const gaps = shoulderTops(positions(`garments/${id}.glb`)).map((top, k) => (top - body[k]) * 100);
    gaps.forEach((gap, k) => { if (gap > max || gap < 0) off.push(`${id} |x| ${SHOULDER_BANDS[k].join('–')}: ${gap.toFixed(1)} cm`); });
    const mean = gaps.reduce((a, b) => a + b) / gaps.length;
    if (!JACKETS.has(id) && mean > MAX_KNIT_SHOULDER_MEAN_CM) off.push(`${id} shoulder mean: ${mean.toFixed(1)} cm`);
  }
  expect(off).toEqual([]);
});

// A top touches the chest and hangs straight to the hip: the gap at the waist is the drop over the narrower waist
// (knits measured 0.2 to 1.6 cm at the chest, 3.0 to 5.7 cm at the waist). Pulling the waist in would mean recutting the
// piece; the check keeps it from floating in front again.
const MAX_KNIT_CHEST_GAP_CM = 2;
const MAX_JACKET_CHEST_GAP_CM = 5;
const MAX_WAIST_GAP_CM = 6;
function frontZ(p: Float32Array, lo: number, hi: number): number {
  let z = -Infinity, count = 0;
  for (let i = 0; i < p.length; i += 3) {
    if (Math.abs(p[i]) < 0.04 && p[i + 1] > lo && p[i + 1] < hi) { z = Math.max(z, p[i + 2]); count++; }
  }
  if (count < 4) throw new Error(`front band ${lo}–${hi} has no vertices: the check measures nothing`);
  return z;
}

test('tops rest on the chest and hang straight in front, not floating off the body', () => {
  const chest = frontZ(body, 1.2, 1.3), waist = frontZ(body, 1.0, 1.1);
  const off: string[] = [];
  for (const id of tops) {
    const p = positions(`garments/${id}.glb`);
    const c = (frontZ(p, 1.2, 1.3) - chest) * 100, w = (frontZ(p, 1.0, 1.1) - waist) * 100;
    if (c < 0 || c > (JACKETS.has(id) ? MAX_JACKET_CHEST_GAP_CM : MAX_KNIT_CHEST_GAP_CM)) off.push(`${id} chest: ${c.toFixed(1)} cm`);
    if (!JACKETS.has(id) && w > MAX_WAIST_GAP_CM) off.push(`${id} waist: ${w.toFixed(1)} cm`);
  }
  expect(off).toEqual([]);
});

// A long sleeve hangs on the arm and the hand comes out of the middle of the cuff (the pieces are generated on a
// mannequin with its shoulders forward: tools/fit/repose_sleeves.py changes the pose of the shoulder, arm and forearm).
// Profile: per 2 cm slice from the cuff up to 1.36 m (|x| > 21 cm; above that is the shoulder tip, covered by the
// shoulder check), front/back centre of the sleeve minus that of the arm, the worst on each side (an average hides a
// bad slice). Cuff: in the 5 cm of the cuff where the hand is, side centre of the cuff minus that of the hand.
// The list is the one in tools/fit/install.py (long-sleeve mask).
const LONG_SLEEVES = [...readFileSync(new URL('../tools/fit/install.py', import.meta.url), 'utf8')
  .match(/LONG_SLEEVE = \{([^}]*)\}/)![1].matchAll(/'(\d{3})'/g)].map(m => m[1]);
const MAX_SLEEVE_OFFSET_CM = 3.5;
const MAX_CUFF_TO_HAND_CM = 2;
// Held at the recorded baseline while the known issue that owns them is open: 036 sits 3.7 cm off the arm in one slice,
// and on 034 the oversized sleeve sits 4.0 cm off the arm on one side (tools/fit/cloth.py).
const SLEEVE_PENDING: Record<string, { offset: number, cuff: number }> = {
  '034': { offset: 4.1, cuff: MAX_CUFF_TO_HAND_CM },
};
function sleeveCenters(p: Float32Array, side: number, minX: number, low: number): Map<number, number> {
  const out = new Map<number, number>();
  for (let k = Math.ceil(low * 50); k <= 68; k++) {
    let min = Infinity, max = -Infinity, count = 0;
    for (let i = 0; i < p.length; i += 3) {
      if (side * p[i] <= minX || Math.abs(p[i + 1] - k / 50) > 0.01) continue;
      min = Math.min(min, p[i + 2]); max = Math.max(max, p[i + 2]); count++;
    }
    if (count > 5) out.set(k, (min + max) / 2);
  }
  return out;
}
function lowestY(p: Float32Array, side: number, minX: number): number {
  let y = Infinity;
  for (let i = 0; i < p.length; i += 3) if (side * p[i] > minX) y = Math.min(y, p[i + 1]);
  return y;
}
// Cuff height: going down from the elbow, the first slice where the garment no longer covers the outside of the arm
// (or the end of the hand, if the sleeve goes past it); the same as sleeve_end in tools/fit/repose_sleeves.py. (The
// lowest garment point beside the hand would catch a wide hem, like that of hoodie 034, instead of the cuff.)
function cuffY(p: Float32Array, side: number): number {
  const handEnd = lowestY(body, side, 0.2);
  const maxX = (q: Float32Array, minX: number, y: number) => {
    let m = -Infinity;
    for (let i = 0; i < q.length; i += 3) if (side * q[i] > minX && Math.abs(q[i + 1] - y) < 0.01) m = Math.max(m, side * q[i]);
    return m;
  };
  for (let k = 110; k > 60; k--) {
    const y = k / 100, arm = maxX(body, 0.17, y);
    if (arm === -Infinity) return y + 0.01;
    if (maxX(p, 0.15, y) < arm - 0.005) return Math.max(y + 0.01, handEnd);
  }
  return handEnd;
}
function middleX(p: Float32Array, side: number, minX: number, low: number, high: number): number {
  let min = Infinity, max = -Infinity;
  for (let i = 0; i < p.length; i += 3) {
    if (side * p[i] <= minX || p[i + 1] <= low || p[i + 1] >= high) continue;
    min = Math.min(min, p[i]); max = Math.max(max, p[i]);
  }
  if (min > max) throw new Error('cuff band has no vertices: the check measures nothing');
  return (min + max) / 2;
}

// An exception to a check is a defect left as it is: it only holds while an open known issue owns it and names the piece.
test('every piece excused from a fit limit is named by the open known issue that owns the exception', () => {
  const issues = knownIssues(), orphans: string[] = [];
  for (const [id, map] of [['fit-structure', SLEEVE_PENDING], ['waistband-010', WAIST_AS_SHIPPED]] as const) {
    const issue = issues.find(i => i.id === id);
    for (const piece of Object.keys(map)) if (!issue?.pieces.includes(piece)) orphans.push(`${piece}: no open ${id} naming it`);
  }
  expect(orphans).toEqual([]);
});

test('long sleeves hang on the arm in profile and the hand comes out of the middle of the cuff', () => {
  expect(LONG_SLEEVES.length).toBeGreaterThanOrEqual(8);
  const off: string[] = [];
  for (const id of LONG_SLEEVES) {
    const p = positions(`garments/${id}.glb`);
    const limit = SLEEVE_PENDING[id] ?? { offset: MAX_SLEEVE_OFFSET_CM, cuff: MAX_CUFF_TO_HAND_CM };
    for (const side of [1, -1]) {
      const arm = sleeveCenters(body, side, 0.205, 0.84), sleeve = sleeveCenters(p, side, 0.21, Math.max(0.84, cuffY(p, side) + 0.03));
      const d = [...sleeve].filter(([k]) => arm.has(k)).map(([k, z]) => (z - arm.get(k)!) * 100);
      if (d.length < 20) off.push(`${id} side ${side}: only ${d.length} slices measured`);
      const worst = d.reduce((a, b) => Math.abs(b) > Math.abs(a) ? b : a, 0);
      if (Math.abs(worst) > limit.offset) off.push(`${id} side ${side}: sleeve ${worst.toFixed(1)} cm off the arm`);
      const cuff = cuffY(p, side);
      const gap = Math.abs(middleX(p, side, 0.19, cuff, cuff + 0.05) - middleX(body, side, 0.2, cuff, cuff + 0.05)) * 100;
      if (gap > limit.cuff) off.push(`${id} side ${side}: cuff ${gap.toFixed(1)} cm off the hand`);
    }
  }
  expect(off).toEqual([]);
});

// A long sleeve ends at the wrist and the hand shows (tools/fit/resize.py scales jackets generated too big). The hand
// runs from 0.87 (wrist) to 0.69 m: the sleeve covers up to 8 cm of it. Cuff height as in cuffY (the wide hem beside
// the hand does not count).
const MIN_CUFF_Y = 0.79;

test('long sleeves end at the wrist and the hand shows below the cuff', () => {
  const off: string[] = [];
  for (const id of LONG_SLEEVES) {
    const p = positions(`garments/${id}.glb`);
    for (const side of [1, -1]) {
      const cuff = cuffY(p, side);
      if (cuff < MIN_CUFF_Y) off.push(`${id} side ${side}: sleeve down to ${cuff.toFixed(2)} m`);
    }
  }
  expect(off).toEqual([]);
});

// The back of the collar touches the nape (the pieces are generated on a mannequin with a straight neck):
// tools/fit/top_cloth.py settles the knits under their own weight, and tools/fit/hood.py, which only moves along z,
// lays collars like that of 030 without splitting its print.
const MAX_KNIT_NAPE_CM = 5;
const MAX_KNIT_NAPE_MEAN_CM = 4;
function backZ(p: Float32Array): number {
  let z = Infinity, count = 0;
  for (let i = 0; i < p.length; i += 3) {
    if (Math.abs(p[i]) < 0.03 && p[i + 1] > 1.5 && p[i + 1] < 1.56) { z = Math.min(z, p[i + 2]); count++; }
  }
  if (count < 4) throw new Error('nape has no vertices: the check measures nothing');
  return z;
}

test('knit tops sit against the nape, not standing up behind it', () => {
  const nape = backZ(body);
  const knits = tops.filter(id => !JACKETS.has(id));
  const gaps = knits.map(id => (nape - backZ(positions(`garments/${id}.glb`))) * 100);
  const off = knits.flatMap((id, k) => gaps[k] > MAX_KNIT_NAPE_CM || gaps[k] < 0 ? [`${id} nape: ${gaps[k].toFixed(1)} cm`] : []);
  const mean = gaps.reduce((a, b) => a + b) / gaps.length;
  if (mean > MAX_KNIT_NAPE_MEAN_CM) off.push(`nape mean: ${mean.toFixed(1)} cm`);
  expect(off).toEqual([]);
});

// Checks the rotation/scale maths of readPositions: with a wrong quaternion, x and z swap and the shoulder check would
// measure the wrong column without failing. Every top is wider than it is deep.
test('tops read in world space: wider side to side than front to back', () => {
  for (const id of tops) {
    const p = positions(`garments/${id}.glb`);
    let x0 = Infinity, x1 = -Infinity, z0 = Infinity, z1 = -Infinity;
    for (let i = 0; i < p.length; i += 3) { x0 = Math.min(x0, p[i]); x1 = Math.max(x1, p[i]); z0 = Math.min(z0, p[i + 2]); z1 = Math.max(z1, p[i + 2]); }
    expect(x1 - x0).toBeGreaterThan(1.3 * (z1 - z0));
  }
});

// Hands never vanish under a long-sleeve mask. The hand runs from the wrist (0.87 m) to the fingertips (0.69 m), the
// human length tools/fit/arm.py gives the forearm.
test('no body mask hides the hands', async () => {
  const bytes = readFileSync(join(ASSETS, 'body/pose-b.glb'));
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const json = JSON.parse(new TextDecoder().decode(bytes.subarray(20, 20 + view.getUint32(12, true))));
  const bin = 20 + view.getUint32(12, true) + 8;
  const acc = json.accessors[json.meshes[0].primitives[0].indices], bv = json.bufferViews[acc.bufferView];
  const at = bin + (bv.byteOffset ?? 0) + (acc.byteOffset ?? 0), size = acc.componentType === 5125 ? 4 : 2;
  const index = (k: number) => size === 4 ? view.getUint32(at + k * 4, true) : view.getUint16(at + k * 2, true);
  const p = positions('body/pose-b.glb');
  const hand = (t: number) => [0, 1, 2].every(k => { const v = index(3 * t + k); return p[3 * v + 1] < 0.9 && p[3 * v + 1] > 0.6 && Math.abs(p[3 * v]) > 0.17; });
  const { BODY_MASKS, BODY_C_MASKS } = await import('./body-masks');
  const { BODY_POSES } = await import('./body-poses');
  const { validateBodyMask } = await import('./body-occlusion');
  const off: string[] = [];
  for (const [pose, masks] of [['B', BODY_MASKS], ['C', BODY_C_MASKS]] as const)
    for (const [id, mask] of Object.entries(masks)) {
      const n = validateBodyMask(mask, pose === 'B' ? BODY_POSES.B.hash : BODY_POSES.C.hash, mask.meshes[0].name, 41600).filter(hand).length;
      if (n > 0) off.push(`${pose} ${id}: ${n}`);
    }
  expect(off).toEqual([]);
});

// Fly of short 008 (measured in fly.ts), closed by tools/fit/zipper.py: the photo has the zip open, and the 3D model
// copied the flaps apart with the lining showing between the seams. Check: from the front, almost no ray may land on
// the lining texels (UV rectangles of the texture).
test('short 008 has its fly closed: the lining between the flaps is not visible from the front', () => {
  expect(flyLiningVisibleCm2(readFileSync(join(ASSETS, 'garments/008.glb')))).toBeLessThan(MAX_FLY_LINING_CM2);
});

// Skirt 009 is a miniskirt in the thrift store photo (height/waist width 1.39), and the 3D model reaches the knee:
// tools/fit/hem.py cuts it at the height of the photo, and the hem stays between 0.56 and 0.62 m.
test('skirt 009 stays a miniskirt, as in the photo', () => {
  const p = positions('garments/009.glb');
  let bottom = Infinity;
  for (let i = 1; i < p.length; i += 3) bottom = Math.min(bottom, p[i]);
  expect(bottom).toBeGreaterThan(0.56);
  expect(bottom).toBeLessThan(0.62);   // and not too short: in the photo the hem is at ~0.58 m
});

// Loose bits: the 3D generator leaves crumbs of cloth attached to the piece by a vertex or by nothing (frayed hems of
// trousers, jacket cuffs), and on the site they become slivers in the air (visual QA, `loose`). tools/fit/islands.py
// deletes them; check: besides the body of the piece, no edge-connected bit is smaller than MIN_PIECE_CM2.
const MIN_PIECE_CM2 = Number(/ISLAND_CM2 = ([\d.]+)/.exec(readFileSync(new URL('../tools/fit/islands.py', import.meta.url), 'utf8'))![1]);

/** Area (cm²) of each bit of the mesh: triangles joined by 2-face edges, vertices welded by position. */
function pieceAreas(file: string): number[] {
  const { positions: p, indices } = readMesh(readFileSync(join(ASSETS, file)));
  const weld = new Map<string, number>(), v = new Int32Array(p.length / 3);
  for (let i = 0; i < v.length; i++) {
    const key = `${Math.round(p[3 * i] * 1e5)},${Math.round(p[3 * i + 1] * 1e5)},${Math.round(p[3 * i + 2] * 1e5)}`;
    if (!weld.has(key)) weld.set(key, weld.size);
    v[i] = weld.get(key)!;
  }
  const n = indices.length / 3, parent = Int32Array.from({ length: n }, (_, i) => i);
  const find = (i: number): number => { while (parent[i] !== i) i = parent[i] = parent[parent[i]]; return i; };
  // only an edge of exactly 2 faces joins (like trimesh.face_adjacency in islands.py): held by a 3-face edge is loose
  const edge = new Map<string, number[]>();
  for (let t = 0; t < n; t++)
    for (let k = 0; k < 3; k++) {
      const a = v[indices[3 * t + k]], b = v[indices[3 * t + (k + 1) % 3]];
      const key = a < b ? `${a},${b}` : `${b},${a}`;
      edge.set(key, [...(edge.get(key) ?? []), t]);
    }
  for (const faces of edge.values()) if (faces.length === 2) parent[find(faces[0])] = find(faces[1]);
  const area = new Map<number, number>();
  for (let t = 0; t < n; t++) {
    const [a, b, c] = [0, 1, 2].map(k => 3 * indices[3 * t + k]);
    const u = [0, 1, 2].map(k => p[b + k] - p[a + k]), w = [0, 1, 2].map(k => p[c + k] - p[a + k]);
    const x = u[1] * w[2] - u[2] * w[1], y = u[2] * w[0] - u[0] * w[2], z = u[0] * w[1] - u[1] * w[0];
    const r = find(t);
    area.set(r, (area.get(r) ?? 0) + Math.hypot(x, y, z) / 2 * 1e4);
  }
  return [...area.values()].sort((a, b) => b - a);
}

test('no loose bits of cloth: every piece of the mesh besides the garment itself is a real part', () => {
  const loose: string[] = [];
  for (const { id } of CATALOG) {
    const small = pieceAreas(`garments/${id}.glb`).slice(1).filter(a => a >= 0.01 && a < MIN_PIECE_CM2);   // zero area does not show
    if (small.length) loose.push(`${id}: ${small.length} bits, ${small.reduce((s, a) => s + a, 0).toFixed(1)} cm²`);
  }
  expect(loose).toEqual([]);
});

// Lining below the front hem (the 3D generator can leave it hanging below the hem, as on jacket 033, where it shows as
// dark tips over the trousers). Per 1 cm column of the front, the shell is
// the fabric up to 1.2 cm behind the frontmost in the bottom 6 cm; below the shell hem and more than 1.5 cm behind it is
// lining (the same computation as tools/fit/lining.py, which deletes it). A hem folded inwards (ribbed, a shirt with a
// turned hem) also counts and does not show in the showcase: so each piece is held at its recorded baseline, which only
// goes down.
const LINING_CM2: Record<string, number> = {
  '016': 9.8, '017': 2.0, '018': 6.5, '019': 24.2, '020': 2.0, '021': 0.1, '022': 4.5, '023': 26.4, '024': 55.9,
  '025': 4.7, '026': 27.8, '027': 2.7, '028': 16.1, '029': 2.0, '030': 0.0, '031': 3.6, '032': 6.3, '033': 0.0,
  '034': 68.7, '035': 15.9, '036': 56.3, '037': 57.7, '038': 121.5,
};

function liningBelowHemCm2(file: string): number {
  const { positions: p, indices } = readMesh(readFileSync(join(ASSETS, file)));
  const n = indices.length / 3, c = new Float32Array(n * 3), area = new Float32Array(n);
  for (let t = 0; t < n; t++) {
    const [a, b, d] = [0, 1, 2].map(k => 3 * indices[3 * t + k]);
    for (let k = 0; k < 3; k++) c[3 * t + k] = (p[a + k] + p[b + k] + p[d + k]) / 3;
    const u = [0, 1, 2].map(k => p[b + k] - p[a + k]), v = [0, 1, 2].map(k => p[d + k] - p[a + k]);
    area[t] = Math.hypot(u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]) / 2;
  }
  let total = 0;
  for (let i = -17; i <= 17; i++) {
    const x0 = i / 100, col: number[] = [];
    for (let t = 0; t < n; t++)
      if (Math.abs(c[3 * t] - x0) < 0.005 && c[3 * t + 2] > 0 && c[3 * t + 1] > 0.5 && c[3 * t + 1] < 1.2) col.push(t);
    if (col.length < 5) continue;
    const low = Math.min(...col.map(t => c[3 * t + 1]));
    const win = col.filter(t => c[3 * t + 1] < low + 0.06);
    const front = Math.max(...win.map(t => c[3 * t + 2]));
    const hem = Math.min(...win.filter(t => c[3 * t + 2] > front - 0.012).map(t => c[3 * t + 1]));
    for (const t of col) if (c[3 * t + 1] < hem && c[3 * t + 2] < front - 0.015) total += area[t];
  }
  return total * 1e4;
}

test('no lining hanging below the front hem of tops (each piece held to its recorded baseline, only goes down)', () => {
  const worse: string[] = [];
  for (const { id } of CATALOG.filter(p => p.slot !== 'bottom')) {
    const cm2 = liningBelowHemCm2(`garments/${id}.glb`);
    if (cm2 > (LINING_CM2[id] ?? 0) + 0.5) worse.push(`${id}: ${cm2.toFixed(1)} cm² (current ${LINING_CM2[id] ?? 0})`);
  }
  expect(worse).toEqual([]);
});

// Hoods and collars lie on the back (the 3D generator leaves the hood full of air, standing up behind the nape: in
// profile, a flap behind the back). tools/fit/hood.py lays
// them forward along z only (back view, print and UV unchanged). In three columns (x = -6, 0 and 6 cm: the middle and
// sides of the hood) and per 2 cm slice from 1.30 to 1.66 m: the back of the body (the rearmost triangle the line
// crosses) minus the rearmost point of the piece within 2.5 cm of the column; the largest. The same computation as
// hood.behind_cm. Each piece is held at its recorded baseline, which only goes down: real collars and hoods sit a few
// centimetres behind the back, and how far depends on the piece.
const HOOD_BEHIND_CM: Record<string, number> = {
  '016': 3.7, '017': 6.8, '018': 6.6, '019': 4.7, '020': 6.2, '021': 5.8, '022': 3.5, '023': 6.8, '024': 2.5,
  '025': 8.3, '026': 5.7, '027': 2.6, '028': 5.8, '029': 8.0, '030': 9.3, '031': 7.2, '032': 8.8, '033': 8.7,
  '034': 7.2, '035': 8.0, '036': 8.7, '037': 10.6, '038': 8.3,
};

/** z of the body's back on the line (x0, y): the rearmost crossing with the body triangles. */
function bodyBackZ(p: Float32Array, idx: Uint32Array, x0: number, y: number): number {
  let back = Infinity;
  for (let t = 0; t < idx.length; t += 3) {
    const [a, b, c] = [idx[t], idx[t + 1], idx[t + 2]].map(v => [p[3 * v], p[3 * v + 1], p[3 * v + 2]]);
    // the line (x0, y, z) crosses the triangle if (x0, y) falls inside its xy projection; z by barycentrics
    const det = (b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1]);
    if (Math.abs(det) < 1e-12) continue;
    const u = ((x0 - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (y - a[1])) / det;
    const v = ((b[0] - a[0]) * (y - a[1]) - (x0 - a[0]) * (b[1] - a[1])) / det;
    if (u < 0 || v < 0 || u + v > 1) continue;
    back = Math.min(back, a[2] + u * (b[2] - a[2]) + v * (c[2] - a[2]));
  }
  return back;
}

const bodyMesh = readMesh(readFileSync(join(ASSETS, 'body/pose-b.glb')));
const BODY_BACK = [-0.06, 0, 0.06].flatMap(x0 => Array.from({ length: 19 }, (_, k) => 1.3 + 0.02 * k)
  .map(y => [x0, y, bodyBackZ(bodyMesh.positions, bodyMesh.indices, x0, y)]));

function hoodBehindCm(file: string): number {
  const p = positions(file);
  let out = 0;
  for (const [x0, y, back] of BODY_BACK) {
    if (!Number.isFinite(back)) continue;
    let z = Infinity;
    for (let i = 0; i < p.length; i += 3) if (Math.abs(p[i] - x0) < 0.025 && Math.abs(p[i + 1] - y) < 0.01) z = Math.min(z, p[i + 2]);
    if (Number.isFinite(z)) out = Math.max(out, (back - z) * 100);
  }
  return out;
}

test('hoods and collars lie on the back, not standing up behind the nape (each piece held to its recorded baseline, only goes down)', () => {
  const worse: string[] = [];
  for (const id of tops) {
    const cm = hoodBehindCm(`garments/${id}.glb`);
    if (cm > (HOOD_BEHIND_CM[id] ?? 0) + 0.2) worse.push(`${id}: ${cm.toFixed(1)} cm behind the back (current ${HOOD_BEHIND_CM[id] ?? 0})`);
  }
  expect(worse).toEqual([]);
});
