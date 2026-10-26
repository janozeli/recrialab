// Baseline of tools/fit/penetration.py (gap and penetration of the bottoms): it can only go down.
// The measure itself runs in the fit job of the Site CI; here we check that the baseline covers the 15 pieces, that
// the trousers still shaped by the generator's mannequin have a goal below the baseline, and that nobody loosened the baseline
// against main.
import { test, expect } from 'bun:test';
import { readFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';

const ROOT = new URL('../', import.meta.url).pathname;
const FILE = 'tools/fit/penetration.json';
type Base = { measure?: number; redefined?: string[]; pieces: Record<string, { goal?: { target_penetrates: number; bands: string[] }; bands: Record<string, Record<string, number>> }> };
const base: Base = JSON.parse(readFileSync(ROOT + FILE, 'utf8'));
const WITH_GOAL = ['002', '004', '006'];

test('the measure version only goes up', () => {
  const r = spawnSync('git', ['show', `origin/main:${FILE}`], { cwd: ROOT, encoding: 'utf8' });
  expect(base.measure).toBeGreaterThanOrEqual(r.status === 0 ? JSON.parse(r.stdout).measure ?? 1 : 1);
});

test('the baseline covers the 15 bottoms, with the total of each', () => {
  expect(Object.keys(base.pieces)).toEqual(Array.from({ length: 15 }, (_, i) => String(i + 1).padStart(3, '0')));
  for (const p of Object.values(base.pieces)) expect(Object.keys(p.bands.total).sort()).toEqual(['gap_over_4cm', 'penetrates', 'penetrates_visible']);
});

test('a goal only on the trousers shaped by the generator\'s mannequin, near zero and below the baseline', () => {
  expect(Object.keys(base.pieces).filter(k => base.pieces[k].goal)).toEqual(WITH_GOAL);
  for (const k of WITH_GOAL) {
    const { target_penetrates, bands } = base.pieces[k].goal!;
    expect(target_penetrates).toBeLessThanOrEqual(2);
    // goal reached: delete `goal` from the piece in penetration.json
    for (const f of bands) expect(base.pieces[k].bands[f].penetrates).toBeGreaterThan(target_penetrates);
  }
});

test('the baseline does not go up against main', () => {
  const r = spawnSync('git', ['show', `origin/main:${FILE}`], { cwd: ROOT, encoding: 'utf8' });
  if (r.status !== 0) return;   // not on main yet
  const main: Base = JSON.parse(r.stdout);
  // a new version of the measure (`measure` in penetration.json) starts a new baseline, which from then on only goes
  // down; only the bands it redefines (`redefined`) may start above main
  const free = (main.measure ?? 1) !== base.measure ? new Set(base.redefined ?? []) : new Set<string>();
  const rose: string[] = [];
  for (const [k, p] of Object.entries(main.pieces))
    for (const [f, m] of Object.entries(p.bands))
      if (!free.has(f))
        for (const [c, v] of Object.entries(m)) if ((base.pieces[k]?.bands[f]?.[c] ?? Infinity) > v) rose.push(`${k} ${f} ${c}`);
  expect(rose).toEqual([]);
});
