// The repository guide must not point to checks that do not exist.
import { test, expect } from 'bun:test';
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

const ROOT = new URL('../', import.meta.url).pathname;

test('every file cited in AGENTS.md exists', () => {
  const text = readFileSync(join(ROOT, 'AGENTS.md'), 'utf8');
  const cited = [...text.matchAll(/`([\w./-]+\.(?:ts|js|mjs|md|yml|yaml|py|jsonc))`/g)].map(m => m[1]);
  expect(cited.length).toBeGreaterThan(5);
  expect(cited.filter(f => !existsSync(join(ROOT, f)) && !existsSync(join(ROOT, 'site', f)))).toEqual([]);
});
