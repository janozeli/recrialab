// The fit engine's garments on the site: every garment is either the engine's or on hold as published, the files are
// the ones engine-import.ts brought in, they fit a phone, and a look never mixes the two versions.
import { test, expect } from 'bun:test';
import { createHash } from 'node:crypto';
import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { readGlb } from './glb';
import { CATALOG } from './catalog-data';
import { ENGINE_PARTS } from './engine-garments';
import { ENGINE_HOLD } from './engine-hold';
import { engineLook, engineOn } from './engine-look';
import lock from './engine.lock.json';

const DIR = new URL('./assets/engine/', import.meta.url).pathname;
const ids = CATALOG.map(p => p.id);
// Phone limits of an engine garment, all its parts together; the published garments have their own (integrity.test.ts).
const MAX_PART_BYTES = 512 * 1024;
const MAX_TRIANGLES = 2_000;
const MAX_TEXTURE_PX = 512;

test('every garment is the engine\'s or on hold as published, with the reason', () => {
  for (const id of ids) expect(id in ENGINE_PARTS || id in ENGINE_HOLD, id).toBe(true);
  for (const [id, reason] of Object.entries(ENGINE_HOLD)) {
    expect(ids, id).toContain(id);
    expect(reason.length, id).toBeGreaterThan(10);
  }
  for (const id of Object.keys(ENGINE_PARTS)) expect(ENGINE_PARTS[id].length, id).toBeGreaterThan(0);
});

test('assets/engine holds exactly what engine-import.ts recorded', () => {
  expect(readdirSync(DIR).sort()).toEqual(Object.keys(lock.files).sort());
  for (const [name, hash] of Object.entries(lock.files)) {
    expect(createHash('sha256').update(readFileSync(join(DIR, name))).digest('hex'), name).toBe(hash);
  }
  expect(lock.engine).toMatch(/^[0-9a-f]{40}$/);
});

test('engine garments and bodies stay within the phone budget', () => {
  const triangles: Record<string, number> = {};
  for (const name of Object.keys(lock.files)) {
    const bytes = readFileSync(join(DIR, name));
    expect(bytes.length, name).toBeLessThanOrEqual(MAX_PART_BYTES);
    const glb = readGlb(bytes);
    const piece = name.startsWith('body') ? name : name.slice(0, name.indexOf('-'));
    triangles[piece] = (triangles[piece] ?? 0) + glb.triangles;
    for (const t of glb.textures) expect(Math.max(t.width, t.height), name).toBeLessThanOrEqual(MAX_TEXTURE_PX);
  }
  for (const [piece, n] of Object.entries(triangles)) expect(n, piece).toBeLessThanOrEqual(MAX_TRIANGLES);
});

test('a look is the engine\'s only when every garment in it is; one on hold brings the whole look back as published', () => {
  const [a, b] = Object.keys(ENGINE_PARTS);
  expect(engineLook([], true, {})).toBe(true);
  expect(engineLook([a, b], true, {})).toBe(true);
  expect(engineLook([a, b], true, { [b]: 'worse than the published one from the back' })).toBe(false);
  expect(engineLook([a], true, { [b]: 'worse than the published one from the back' })).toBe(true);
  expect(engineLook([a, '999'], true, {})).toBe(false);
  expect(engineLook([a, b], false, {})).toBe(false);
});

test('garments on hold are listed one per line', () => {
  const source = readFileSync(new URL('./engine-hold.ts', import.meta.url), 'utf8');
  const body = source.slice(source.indexOf('= {') + 3, source.lastIndexOf('}'));
  for (const line of body.split('\n').filter(l => l.trim())) expect(line.match(/'\d{3}':/g)?.length, line).toBe(1);
});

test('?engine turns the engine on and ?classico off, whatever the default', () => {
  expect(engineOn('?look=004.024', false)).toBe(false);
  expect(engineOn('?look=004.024&engine', false)).toBe(true);
  expect(engineOn('?look=004.024', true)).toBe(true);
  expect(engineOn('?look=004.024&classico', true)).toBe(false);
});
