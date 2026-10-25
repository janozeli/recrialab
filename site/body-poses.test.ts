import { test, expect } from 'bun:test';
import { readFileSync, readdirSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { BODY_POSES, bodyPoseForBottom } from './body-poses';
import { validateBodyMask, WAIST_STEPS, WAIST_TORSO, WAIST_BAND, NECK_STEPS, NECK_AXIS_Z, NECK_RADIUS, NECK_BAND } from './body-occlusion';
import { BODY_MASKS, BODY_C_MASKS } from './body-masks';

const asset = (name) => new URL(`./assets/${name}`, import.meta.url);
const hash = (name) => createHash('sha256').update(readFileSync(asset(name))).digest('hex');

test('the five pose C pants select C; removal and every other catalog item restore B', () => {
  const cPants = new Set(['006', '011', '012', '013', '014']);
  for (let n = 1; n <= 38; n++) {
    const id = String(n).padStart(3, '0');
    expect(bodyPoseForBottom(id)).toBe(cPants.has(id) ? 'C' : 'B');
  }
  expect(bodyPoseForBottom(null)).toBe('B');
  expect(bodyPoseForBottom()).toBe('B');
  expect(bodyPoseForBottom('unknown')).toBe('B');
});

test('all deployed C masks bind to the actual C body and garment, and reject B', () => {
  expect(hash('body/pose-b.glb')).toBe(BODY_POSES.B.hash);
  expect(hash('body/pose-c.glb')).toBe(BODY_POSES.C.hash);
  expect(Object.keys(BODY_C_MASKS)).toHaveLength(28);
  for (const [id, mask] of Object.entries(BODY_C_MASKS)) {
    expect(hash(`garments/${id}.glb`)).toBe(mask.garment_sha256);
    for (const mesh of mask.meshes) {
      expect(validateBodyMask(mask, BODY_POSES.C.hash, mesh.name, 41600).length).toBeGreaterThan(0);
      expect(() => validateBodyMask(mask, BODY_POSES.B.hash, mesh.name, 41600)).toThrow();
    }
  }
});


test('all active B masks bind to shipped garment bytes and restore valid body triangles', () => {
  const ids = Object.keys(BODY_MASKS);
  expect(ids.length).toBeGreaterThan(0);
  expect(hash('body/pose-b.glb')).toBe(BODY_POSES.B.hash);
  for (const id of ids) {
    const mask = BODY_MASKS[id];
    expect(hash(`garments/${id}.glb`)).toBe(mask.garment_sha256);
    for (const mesh of mask.meshes) {
      const hidden = validateBodyMask(mask, BODY_POSES.B.hash, mesh.name, 41600);
      expect(new Set(hidden).size).toBe(hidden.length);
      expect(() => validateBodyMask(mask, BODY_POSES.C.hash, mesh.name, 41600)).toThrow();
    }
  }
});

// Torso clip at the waistband line (tools/fit/waist.py): the shader and the generator use the same numbers, and each
// line has one angle per step, at waist height.
test('waist lines match the shader clip and sit at the waist', () => {
  const py = readFileSync(new URL('../tools/fit/waist.py', import.meta.url), 'utf8');
  const [, step, torso, band] = py.match(/^STEP, TORSO, BAND[^=]*= ([\d.]+), ([\d.]+), ([\d.]+)/m);
  expect(360 / Number(step)).toBe(WAIST_STEPS);
  expect(Number(torso)).toBe(WAIST_TORSO);
  expect(Number(band)).toBe(WAIST_BAND);
  const lines = Object.entries({ ...BODY_MASKS, ...BODY_C_MASKS }).filter(([, m]) => m.waist_line);
  // the pieces with a clip are the ones waist.py lists: losing the line of one brings back the jagged edge
  const ids = py.match(/or \[([^\]]*)\]/)[1].match(/\d{3}/g);
  expect(lines.map(([id]) => id).sort()).toEqual(ids.sort());
  for (const [, mask] of lines) {
    expect(mask.waist_line).toHaveLength(WAIST_STEPS);
    for (const y of mask.waist_line) expect(y > 0.85 && y < 1.1).toBe(true);
  }
});

// Neck clip at the collar line (tools/fit/collar.py): same numbers in the shader and the generator, and the pieces
// with a line are the ones collar.py lists, with the line at neck height.
test('neck lines match the shader clip and sit at the neck', () => {
  const py = readFileSync(new URL('../tools/fit/collar.py', import.meta.url), 'utf8');
  const [, step, axis, radius, band] = py.match(/^STEP, AXIS_Z, RADIUS, BAND[^=]*= ([\d.]+), (-?[\d.]+), ([\d.]+), ([\d.]+)/m);
  expect(360 / Number(step)).toBe(NECK_STEPS);
  expect(Number(axis)).toBe(NECK_AXIS_Z);
  expect(Number(radius)).toBe(NECK_RADIUS);
  expect(Number(band)).toBe(NECK_BAND);
  const ids = py.match(/^IDS = \[([^\]]*)\]/m)[1].match(/\d{3}/g).sort();
  for (const registry of [BODY_MASKS, BODY_C_MASKS]) {
    const lines = Object.entries(registry).filter(([, m]) => m.neck_line);
    expect(lines.map(([id]) => id).sort()).toEqual(ids);
    for (const [, mask] of lines) {
      expect(mask.neck_line).toHaveLength(NECK_STEPS);
      for (const y of mask.neck_line) expect(y > 1.4 && y < 1.66).toBe(true);
    }
  }
});

test('the mask generator never reads the accepted-defects list (a removed acceptance must not silently change a mask)', () => {
  const dir = new URL('../tools/fit/', import.meta.url);
  for (const f of readdirSync(dir).filter(f => f.endsWith('.py'))) {
    expect(readFileSync(new URL(f, dir), 'utf8').includes('defects.json'), f).toBe(false);
  }
});
