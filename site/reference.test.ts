// The originals (tools/fit/reference) are the yardstick of the checks: they do not change.
import { test, expect } from 'bun:test';
import { createHash } from 'node:crypto';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';

const DIR = new URL('../tools/fit/reference/', import.meta.url).pathname;
const files = (d: string): string[] => readdirSync(d).flatMap(n => {
  const p = join(d, n);
  return statSync(p).isDirectory() ? files(p) : [relative(DIR, p)];
});

test('every reference file matches the manifest sha256, none missing and none extra', () => {
  const manifest: Record<string, string> = JSON.parse(readFileSync(join(DIR, 'manifest.json'), 'utf8'));
  const present = files(DIR).filter(f => f !== 'manifest.json' && f !== 'README.md').sort();
  expect(present).toEqual(Object.keys(manifest).sort());
  const wrong = present.filter(f => createHash('sha256').update(readFileSync(join(DIR, f))).digest('hex') !== manifest[f]);
  expect(wrong).toEqual([]);
});
