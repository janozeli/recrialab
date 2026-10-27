// Per-piece baselines written as dictionaries in the fit checks: they only go down against main. A new version of the
// measure (the `version` constant next to the dictionary) restarts it, and from then on it only goes down again.
import { test, expect } from 'bun:test';
import { readFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';

const ROOT = new URL('../', import.meta.url).pathname;
const BASELINES = [
  { file: 'tools/fit/poke_through.py', name: 'TOP_HOLES' },
  { file: 'tools/fit/sleeve_tear.py', name: 'EDGE', version: 'EDGE_MEASURE' },
];

const parse = (src: string, name: string) => {
  const block = src.match(new RegExp(`^${name} = \\{([^}]*)\\}`, 'm'));
  if (!block) throw new Error(`${name} not found`);
  return Object.fromEntries([...block[1].matchAll(/'(\d{3})': ([\d.]+)/g)].map(m => [m[1], Number(m[2])]));
};
const version = (src: string, name?: string) => name ? Number(src.match(new RegExp(`^${name} = (\\d+)`, 'm'))?.[1] ?? 1) : 1;

for (const { file, name, version: v } of BASELINES) {
  test(`${name} in ${file} does not go up against main`, () => {
    const src = readFileSync(ROOT + file, 'utf8');
    const now = parse(src, name);
    expect(Object.keys(now).length).toBeGreaterThan(0);
    const r = spawnSync('git', ['show', `origin/main:${file}`], { cwd: ROOT, encoding: 'utf8' });
    if (r.status !== 0 || !new RegExp(`^${name} = \\{`, 'm').test(r.stdout)) return;   // not on main yet
    expect(version(src, v)).toBeGreaterThanOrEqual(version(r.stdout, v));
    if (version(src, v) !== version(r.stdout, v)) return;
    const main = parse(r.stdout, name);
    const rose = Object.entries(main).filter(([id, value]) => (now[id] ?? Infinity) > value).map(([id]) => id);
    expect(rose).toEqual([]);
  });
}
