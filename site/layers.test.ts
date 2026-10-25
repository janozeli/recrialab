import { test, expect } from 'bun:test';
import { readFileSync } from 'node:fs';
import { expandLayerRanges } from './garment-layer-data';
import { visibleBodyIndices } from './body-occlusion';

const table = (n: number): string =>
  readFileSync(new URL(`./assets/layers/${String(n).padStart(3, '0')}.json`, import.meta.url), 'utf8');

test('bottom restored in full after removing or replacing top; cached indices untouched', () => {
  const source = new Uint16Array([0, 1, 2, 2, 3, 4, 4, 5, 6, 6, 7, 8]);
  const copy = source.slice();
  const first = visibleBodyIndices(source, [expandLayerRanges([[1, 2]], 4)]);
  expect([...first]).toEqual([0, 1, 2, 6, 7, 8]);
  expect([...visibleBodyIndices(source, [])]).toEqual([...copy]);
  expect([...visibleBodyIndices(source, [expandLayerRanges([[3, 3]], 4)])]).toEqual([0, 1, 2, 2, 3, 4, 4, 5, 6]);
  expect([...source]).toEqual([...copy]);
});

test('corrupt ranges fail rather than removing unrelated faces', () => {
  for (const bad of [[[0, 4]], [[2, 1]], [[0, 1], [1, 2]], [[-1, 1]], [[.5, 1]]]) {
    expect(() => expandLayerRanges(bad, 4)).toThrow();
  }
});

test('all 345 precomputed pairs fit each referenced primitive', () => {
  let count = 0;
  for (let n = 1; n <= 15; n++) {
    const d = JSON.parse(table(n));
    for (const ranges of Object.values(d.pairs) as number[][][][]) {
      expect(ranges.length).toBe(d.meshes.length);
      ranges.forEach((r, i) => {
        expect(expandLayerRanges(r, d.meshes[i].triangles).length).toBeLessThanOrEqual(d.meshes[i].triangles);
      });
      count++;
    }
  }
  expect(count).toBe(345);
});

test('layer tables keep one line per top (tools/fit/layer_tables.py), so git merges changes to different pieces', () => {
  const c = (v: unknown): string => JSON.stringify(v);
  const lines = (d: Record<string, unknown>): string => Object.keys(d).sort().map(k => `${c(k)}:${c(d[k])}`).join(',\n');
  for (let n = 1; n <= 15; n++) {
    const text = table(n);
    const t = JSON.parse(text);
    expect(text).toBe(`{"bottomHash":${c(t.bottomHash)},\n"meshes":${c(t.meshes)},\n"topHashes":{\n${lines(t.topHashes)}\n},\n"pairs":{\n${lines(t.pairs)}\n}}\n`);
  }
});
