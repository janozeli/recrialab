// Per-piece baselines written as dictionaries in the fit checks: they only go down against main. EDGE of
// tools/fit/sleeve_tear.py is held by the check itself, which measures each top as main has it.
import { test, expect } from 'bun:test';
import { readFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';

const ROOT = new URL('../', import.meta.url).pathname;
const BASELINES = [
  { file: 'tools/fit/poke_through.py', name: 'TOP_HOLES' },
];
// without main (a shallow checkout) the comparison cannot run: in the CI that is an error, locally the test says so
const HAS_MAIN = spawnSync('git', ['rev-parse', '--verify', '-q', 'origin/main'], { cwd: ROOT }).status === 0;
test('origin/main is there to compare with', () => {
  if (!HAS_MAIN && !process.env.CI) console.warn('origin/main is missing: the baselines are not compared with main');
  expect(HAS_MAIN || !process.env.CI).toBe(true);
});

const parse = (src: string, name: string) => {
  const block = src.match(new RegExp(`^${name} = \\{([^}]*)\\}`, 'm'));
  if (!block) throw new Error(`${name} not found`);
  return Object.fromEntries([...block[1].matchAll(/'(\d{3})': ([\d.]+)/g)].map(m => [m[1], Number(m[2])]));
};

for (const { file, name } of BASELINES) {
  test(`${name} in ${file} does not go up against main`, () => {
    const src = readFileSync(ROOT + file, 'utf8');
    const now = parse(src, name);
    expect(Object.keys(now).length).toBeGreaterThan(0);
    const r = spawnSync('git', ['show', `origin/main:${file}`], { cwd: ROOT, encoding: 'utf8' });
    if (r.status !== 0 || !new RegExp(`^${name} = \\{`, 'm').test(r.stdout)) return;   // not on main yet
    const main = parse(r.stdout, name);
    const rose = Object.entries(main).filter(([id, value]) => (now[id] ?? Infinity) > value).map(([id]) => id);
    expect(rose).toEqual([]);
  });
}
