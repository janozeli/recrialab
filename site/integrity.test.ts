// Invariants of the published catalog. They fail in CI before an error reaches someone's phone.
import { test, expect } from 'bun:test';
import { createHash } from 'node:crypto';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { readGlb } from './glb';
import { BODY_MASKS, BODY_C_MASKS } from './body-masks';
import { bodyPoseForBottom } from './body-poses';
import { CATALOG } from './catalog-data';

const ASSETS = new URL('./assets/', import.meta.url).pathname;
const sha = (path: string) => createHash('sha256').update(readFileSync(path)).digest('hex');
const glb = (id: string) => join(ASSETS, 'garments', `${id}.glb`);
const ids = CATALOG.map(p => p.id);
const bottoms = CATALOG.filter(p => p.slot === 'bottom').map(p => p.id);
const tops = CATALOG.filter(p => p.slot === 'top').map(p => p.id);

// Phone limits. Raising one needs a justification in the change.
// 2 MiB per piece: WebP textures ≤1024 px, no roughness/metalness maps (the site uses a fixed matte fabric).
const MAX_GLB_BYTES = 2 * 1024 * 1024;
const MAX_GARMENT_TRIANGLES = 16_000;
const MAX_TEXTURE_PX = 1024;
// Known exceptions, with their reason. Do not add one without measuring the impact on a phone.
const TEXTURE_EXCEPTIONS: Record<string, string> = {};

test('catalog has the 38 pieces, 15 bottoms and 23 tops, each with one model', () => {
  expect(ids).toHaveLength(38);
  expect(new Set(ids).size).toBe(38);
  expect(bottoms).toHaveLength(15);
  expect(tops).toHaveLength(23);
  for (const id of ids) expect(statSync(glb(id)).isFile()).toBe(true);
});

test('every piece has a body mask for each pose it can appear in', () => {
  for (const id of tops) {
    expect(BODY_MASKS[id]).toBeDefined();
    expect(BODY_C_MASKS[id]).toBeDefined();
  }
  for (const id of bottoms) {
    const pose = bodyPoseForBottom(id);
    expect(pose === 'B' ? BODY_MASKS[id] : BODY_C_MASKS[id]).toBeDefined();
  }
});

test('layer tables point at the exact GLB bytes being shipped and at the rule that built them', () => {
  const generator = sha(new URL('../tools/fit/gen_layers.py', import.meta.url).pathname);
  for (const bottom of bottoms) {
    const table = JSON.parse(readFileSync(join(ASSETS, 'layers', `${bottom}.json`), 'utf8'));
    // stale hash (after merging main, for example): python3 tools/fit/layer_tables.py redoes only the stale pairs
    expect(table.bottomHash).toBe(sha(glb(bottom)));
    // a table built by an older gen_layers.py: python3 tools/fit/layer_tables.py rebuilds all 15
    expect(table.generatorHash).toBe(generator);
    expect(Object.keys(table.topHashes).sort()).toEqual([...tops].sort());
    for (const [top, hash] of Object.entries(table.topHashes)) expect(hash).toBe(sha(glb(top)));
  }
});

test('models stay within the phone budget', () => {
  for (const id of ids) {
    const bytes = readFileSync(glb(id));
    expect(bytes.length).toBeLessThanOrEqual(MAX_GLB_BYTES);
    const { triangles, textures } = readGlb(bytes);
    expect(triangles).toBeLessThanOrEqual(MAX_GARMENT_TRIANGLES);
    const largest = Math.max(0, ...textures.map(t => Math.max(t.width, t.height)));
    if (TEXTURE_EXCEPTIONS[id]) continue;
    if (largest > MAX_TEXTURE_PX) throw new Error(`${id}: texture of ${largest} px (limit ${MAX_TEXTURE_PX})`);
  }
});

test('texture exceptions are still needed', () => {
  for (const id of Object.keys(TEXTURE_EXCEPTIONS)) {
    const largest = Math.max(...readGlb(readFileSync(glb(id))).textures.map(t => Math.max(t.width, t.height)));
    expect(largest).toBeGreaterThan(MAX_TEXTURE_PX);
  }
});

test('every file in assets/ is used by the code', () => {
  const source = readdirSync(new URL('.', import.meta.url).pathname)
    .filter(f => /\.(ts|js|html|css)$/.test(f) && !/\.test\./.test(f))
    .map(f => readFileSync(new URL(`./${f}`, import.meta.url), 'utf8')).join('\n');
  const unused: string[] = [];
  const walk = (dir: string) => {
    for (const name of readdirSync(dir)) {
      const path = join(dir, name);
      if (statSync(path).isDirectory()) walk(path);
      else if (!source.includes(path.slice(ASSETS.length - 'assets/'.length))) unused.push(path.slice(ASSETS.length));
    }
  };
  walk(ASSETS);
  expect(unused).toEqual([]);
});
