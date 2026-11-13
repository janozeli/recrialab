// The pictures CI measures are of the site as it opens for a visitor. For a night the site opened with the fit engine's
// garments while visual QA and the showcase still asked for `?classico`, so no picture in CI was of what was on air
// and a polo with one sleeve to the elbow went out (13/11).
import { test, expect } from 'bun:test';
import { readFileSync } from 'node:fs';

const read = (f: string) => readFileSync(new URL(`../${f}`, import.meta.url), 'utf8');

test('visual QA and the showcase open the look with no version switch unless asked', () => {
  for (const f of ['tools/verify-site/visual-qa.mjs', 'tools/verify-site/showcase.mjs']) {
    const text = read(f);
    expect(text, f).toContain("process.argv.includes('--classic') ? '&classico' : process.argv.includes('--engine') ? '&engine' : ''");
    expect(text.match(/&classico|&engine/g)?.length, `${f}: a version switch outside the one choice`).toBe(2);
  }
});

test('CI photographs the default: no version switch on the visual QA and showcase steps', () => {
  const steps = read('.github/workflows/site-e2e.yml').split('\n').filter(l => /(visual-qa|showcase)\.mjs/.test(l) && !l.trim().startsWith('#'));
  expect(steps.length).toBeGreaterThanOrEqual(3);
  for (const l of steps) expect(l).not.toMatch(/--classic|--engine/);
  // the list CI compares with is the default one; the classic list is only for pictures taken with --classic
  expect(read('.github/workflows/site-e2e.yml')).not.toContain('defects-classic.json');
  expect(read('tools/fit/calibration.py')).toContain("--classic --looks {} --out site/verify-out/calibration");
  expect(read('tools/fit/calibration.py')).toContain('--defects tools/visual-qa/defects-classic.json');
});

test('every defect listed for the default site has a cap, so a listed look that gets worse fails', () => {
  const listed = JSON.parse(read('tools/visual-qa/defects.json')) as Record<string, Record<string, unknown>>;
  const open: string[] = [];
  for (const [measure, looks] of Object.entries(listed)) {
    if (measure.startsWith('_')) continue;
    for (const [look, entry] of Object.entries(looks)) {
      const e = entry as { issue?: string; up_to?: number };
      if (typeof e !== 'object' || typeof e.issue !== 'string' || typeof e.up_to !== 'number') open.push(`${measure} ${look}`);
    }
  }
  expect(open).toEqual([]);
  expect(read('tools/visual-qa/measure.py')).toContain('got worse than recorded');
});
