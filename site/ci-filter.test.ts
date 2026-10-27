import { test, expect } from 'bun:test';
import { readFileSync } from 'node:fs';
import { filter, changedLayers, changedDefects, calibrationLooks } from './ci-filter';

const none = () => null;
const wf = (f: string) => readFileSync(new URL(`../.github/workflows/${f}`, import.meta.url), 'utf8');

test('docs, tests and text neither photograph nor measure anything', () => {
  expect(filter(['README.md', 'site/ux.test.ts', 'AGENTS.md'], none))
    .toEqual({ fit: false, phones: false, visualQa: '', pieces: '' });
});

test('a change to the fit limits runs the fit job, where calibration.py holds them against the saved defects', () => {
  expect(filter(['site/fit.test.ts'], none)).toEqual({ fit: true, phones: false, visualQa: '', pieces: '' });
});

test('site code, the body or a tool changed: everything runs', () => {
  for (const a of ['site/dressup.ts', 'site/index.html', 'site/assets/body/pose-b.glb',
    'site/assets/body/poses.json', 'tools/visual-qa/measure.py', 'tools/verify-site/visual-qa.mjs',
    '.github/workflows/site-e2e.yml', 'site/ci-filter.ts', 'site/package.json'])
    expect(filter([a], none)).toMatchObject({ phones: true, visualQa: 'all', pieces: '' });
  expect(filter(['site/assets/body/pose-b.glb'], none).fit).toBe(true);
});

test('only one piece changed: fit and phones run, visual QA photographs only that piece', () => {
  expect(filter(['site/assets/garments/008.glb', 'site/assets/masks/pose-c/008.json'], none))
    .toEqual({ fit: true, phones: true, visualQa: '008', pieces: '008' });
  expect(filter(['site/assets/photos/023.webp', 'site/assets/masks/pose-b/031.json'], none).visualQa).toBe('023,031');
});

test('a piece whose model or mask changed is also photographed with every piece of the other group', () => {
  // the ci plan holds one pair per top: 030 rebuilt passed CI with a new tear on 001.030, seen only in review (27/10)
  expect(filter(['site/assets/garments/030.glb'], none).pieces).toBe('030');
  expect(filter(['site/assets/masks/pose-b/031.json', 'site/assets/masks/pose-c/008.json'], none).pieces).toBe('008,031');
  expect(filter(['site/assets/photos/023.webp'], none).pieces).toBe('');
  const e2e = wf('site-e2e.yml');
  expect(e2e).toContain('pieces: ${{ steps.filter.outputs.pieces }}');
  // its own folder: measures-<part>.json of the ci plan step must not be overwritten (they hold the midriff rows)
  expect(e2e).toContain('--plan pairs --changed "$PIECES" --out site/verify-out/visual-qa/pairs');
});

test('selector thumbnails and their renderer: phones only, no visual QA', () => {
  expect(filter(['site/assets/thumbnails/023.webp', 'site/thumbnails.lock.json', 'site/thumbnails.ts', 'site/thumbnail-render.ts'], none))
    .toEqual({ fit: false, phones: true, visualQa: '', pieces: '' });
  expect(filter(['site/assets/garments/023.glb', 'site/assets/thumbnails/023.webp', 'site/thumbnails.lock.json'], none).visualQa).toBe('023');
  expect(filter(['site/fabric.ts'], none).visualQa).toBe('all');
});

test('a fit tool only turns on its own job', () => {
  expect(filter(['tools/fit/poke_through.py'], none)).toEqual({ fit: true, phones: false, visualQa: '', pieces: '' });
});

test('a calibration case or script also photographs the looks of the visual cases', () => {
  const looks = calibrationLooks(readFileSync(new URL('../tools/fit/calibration.py', import.meta.url), 'utf8'));
  expect(looks).toContain('014.022');
  // every visual case names its looks as a literal, or the filter would read none and skip visual QA silently
  const text = readFileSync(new URL('../tools/fit/calibration.py', import.meta.url), 'utf8');
  expect(text.match(/RENDER\.format\(/g)!.length).toBe([...text.matchAll(/RENDER\.format\('[^']+'\)/g)].length);
  for (const a of ['tools/fit/calibration.py', 'tools/fit/reference/calibration/hip-014/before/garments/014.glb'])
    expect(filter([a], none)).toEqual({ fit: true, phones: false, visualQa: [...looks].sort().join(','), pieces: '' });
  expect(calibrationLooks("RENDER.format('003.033'),\n RENDER.format('014.022,014.035')")).toEqual(['003.033', '014.022', '014.035']);
});

test('layer table: only the pairs that changed, or the bottom piece if its mesh changed', () => {
  const base = { bottomHash: 'b', meshes: [{ triangles: 3 }], topHashes: { '016': 'x', '017': 'y' }, pairs: { '016': [[0, 1]], '017': [] } };
  expect(changedLayers('001', base, { ...base, topHashes: { ...base.topHashes, '017': 'z' }, pairs: { '016': [[0, 1]], '017': [[2, 2]] } }))
    .toEqual(['001.017']);
  expect(changedLayers('001', base, { ...base, bottomHash: 'c' })).toEqual(['001']);
  expect(changedLayers('001', null, base)).toEqual(['001']);
  expect(changedLayers('001', base, base)).toEqual([]);
});

test('defects.json: photographs the looks whose link changed and checks the links', () => {
  expect(changedDefects({ _readme: 'a', junction: { '008.023': 'w' } }, { _readme: 'b', junction: {} })).toEqual(['008.023']);
  const read = (_: string, w: string) => w === 'before' ? { junction: { '008.023': 'f' } } : { junction: {} };
  expect(filter(['tools/visual-qa/defects.json'], read).visualQa).toBe('008.023');
  expect(filter(['tools/known-issues.yaml'], none).visualQa).toBe('check');
});

test('the workflows follow the filter and cancel the old run of the same PR', () => {
  const e2e = wf('site-e2e.yml'), ci = wf('site-ci.yml');
  expect(e2e).toContain('bun site/ci-filter.ts');
  expect(ci).toContain('bun ci-filter.ts');
  expect(e2e).toContain("needs.changes.outputs.phones == 'true'");
  expect(e2e).toContain("needs.changes.outputs.visual_qa != ''");
  expect(e2e).toContain('--changed');
  expect(ci).toContain("needs.validate.outputs.fit == 'true'");
  for (const w of [e2e, ci]) {
    expect(w).toContain('cancel-in-progress: ${{ github.event_name == \'pull_request\' }}');
    expect(w).toMatch(/fetch-depth: [02]\b/);  // HEAD^1 (the base) must be in the checkout
  }
});

test('branch protection can require the phones by one fixed name, whether the matrix ran or was skipped', () => {
  type Job = { needs?: string[]; if?: string; strategy?: unknown };
  const jobs = (Bun.YAML.parse(wf('site-e2e.yml')) as { jobs: Record<string, Job> }).jobs;
  const result = jobs['phones-result'];
  expect(jobs.phones.strategy).toBeDefined();
  expect(result.needs).toEqual(['changes', 'phones']);
  expect(result.if).toBe('always()');
  expect(result.strategy).toBeUndefined();
});
