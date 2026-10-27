// CI runs only what the change of a pull request reaches, so a change to the docs or to one piece does not photograph
// all 38 pieces. Site code, the body or a tool changed: everything runs. Only pieces changed:
// visual QA photographs only the looks of the ci plan with those pieces (the rest of the catalog is the same as main,
// which already passed), plus every pair of a piece whose model or mask changed (the ci plan holds one pair per top:
// a top rebuilt with a new tear on another bottom passed CI and was sent back by the review, 27/10).
// Usage (in Actions, on the PR merge checkout with fetch-depth 2): bun site/ci-filter.ts >> "$GITHUB_OUTPUT"
// Outside pull_request (dispatch, push) everything is on.
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';

export type Filter = {
  /** fit job of Site CI (tools/fit/*.py over the GLBs) */
  fit: boolean;
  /** emulated phones of Site E2E (drive.mjs + layout.mjs) */
  phones: boolean;
  /** visual QA: 'all' (the whole ci plan), the pieces and pairs to photograph ('008,001.016'), 'check' (only the
   * links of defects.json to tools/known-issues.yaml, no photos) or '' (nothing) */
  visualQa: string;
  /** pieces whose model or mask changed ('008,030'): visual QA also photographs each of their pairs (plan pairs) */
  pieces: string;
};

export const EVERYTHING: Filter = { fit: true, phones: true, visualQa: 'all', pieces: '' };

/** Files that reach no heavy job: text, site tests (they run in validate) and repository settings. */
const NOTHING = [/\.md$/, /^site\/[^/]+\.test\.ts$/, /^\.gitignore$/];
/** Files of a single piece: the garment, its masks and the thrift-shop photo. */
const OF_PIECE = [/^site\/assets\/garments\/(\d{3})\.glb$/, /^site\/assets\/masks\/pose-[bc]\/(\d{3})\.json$/,
  /^site\/assets\/photos\/(\d{3})\.webp$/];
/** The model and masks of a piece: they change how it sits with every piece of the other group. */
const SHAPE = /^site\/assets\/(garments\/(\d{3})\.glb|masks\/pose-[bc]\/(\d{3})\.json)$/;
/** Selector thumbnails and their renderer: they change the row of pieces, not the stage (visual QA does not see them). */
const THUMBNAILS = [/^site\/assets\/thumbnails\/\d{3}\.webp$/, /^site\/thumbnails\.(ts|lock\.json)$/, /^site\/thumbnail-render\.(ts|html)$/];
const LAYERS = /^site\/assets\/layers\/(\d{3})\.json$/;
/** The calibration script and its saved defects: the fit job runs its cases, visual QA its --visual cases. */
const CALIBRATION = /^tools\/fit\/(calibration\.py|reference\/calibration\/)/;

/** Looks the visual cases of tools/fit/calibration.py photograph (RENDER.format('014.022,014.035')). */
export function calibrationLooks(text: string): string[] {
  return [...text.matchAll(/RENDER\.format\('([^']+)'\)/g)].flatMap(m => m[1].split(','));
}

type Layers = { bottomHash?: string; topHashes?: Record<string, string>; meshes?: unknown; pairs?: Record<string, unknown> };
const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);

/** Pairs (BBB.TTT) whose layer table of bottom BBB changed; the whole piece if its mesh changed. */
export function changedLayers(bid: string, before: Layers | null, after: Layers | null): string[] {
  if (!before || !after || before.bottomHash !== after.bottomHash || !same(before.meshes, after.meshes)) return [bid];
  const tops = new Set([...Object.keys(before.pairs ?? {}), ...Object.keys(after.pairs ?? {}),
    ...Object.keys(before.topHashes ?? {}), ...Object.keys(after.topHashes ?? {})]);
  return [...tops].filter(t => !same(before.pairs?.[t], after.pairs?.[t]) || before.topHashes?.[t] !== after.topHashes?.[t])
    .sort().map(t => `${bid}.${t}`);
}

/** defects.json: looks whose link changed need photos (a defect taken off the list must really be gone). */
export function changedDefects(before: Record<string, unknown> | null, after: Record<string, unknown> | null): string[] | null {
  if (!before || !after) return null;
  const looks = new Set<string>();
  for (const k of new Set([...Object.keys(before), ...Object.keys(after)])) {
    if (k.startsWith('_')) continue;
    const a = (before[k] ?? {}) as Record<string, string>, d = (after[k] ?? {}) as Record<string, string>;
    for (const l of new Set([...Object.keys(a), ...Object.keys(d)])) if (a[l] !== d[l]) looks.add(l);
  }
  return [...looks].sort();
}

/** read(path, 'before' | 'after') returns the JSON of the file on the base or on the PR (null if it does not exist). */
export function filter(files: string[], read: (f: string, when: 'before' | 'after') => any): Filter {
  const f: Filter = { fit: false, phones: false, visualQa: '', pieces: '' };
  const looks = new Set<string>(), pieces = new Set<string>();
  let all = false, check = false;
  for (const a of files) {
    // fit.test.ts holds limits that calibration.py runs against the saved defects in the fit job.
    if (a === 'site/fit.test.ts') { f.fit = true; continue; }
    if (NOTHING.some(r => r.test(a))) continue;
    if (a === 'tools/known-issues.yaml') { check = true; continue; }
    if (CALIBRATION.test(a)) {
      f.fit = true;
      calibrationLooks(readFileSync(new URL('../tools/fit/calibration.py', import.meta.url), 'utf8')).forEach(x => looks.add(x));
      continue;
    }
    if (a === '.github/workflows/site-ci.yml' || a.startsWith('tools/fit/')) { f.fit = true; continue; }
    if (a === 'tools/visual-qa/defects.json') {
      const l = changedDefects(read(a, 'before'), read(a, 'after'));
      if (l) l.forEach(x => looks.add(x)); else all = true;
      check = true;
      continue;
    }
    if (THUMBNAILS.some(r => r.test(a))) { f.phones = true; continue; }
    const piece = OF_PIECE.map(r => a.match(r)?.[1]).find(Boolean);
    const layers = a.match(LAYERS)?.[1];
    if (piece || layers) {
      f.fit = f.phones = true;
      const shape = a.match(SHAPE);
      if (shape) pieces.add(shape[2] ?? shape[3]);
      (piece ? [piece] : changedLayers(layers!, read(a, 'before'), read(a, 'after'))).forEach(x => looks.add(x));
      continue;
    }
    // Any other file of the site, the body, the tools or the verification workflows: everything.
    if (a.startsWith('site/assets/')) f.fit = true;
    f.phones = true;
    all = true;
  }
  f.visualQa = all ? 'all' : looks.size ? [...looks].sort().join(',') : check ? 'check' : '';
  f.pieces = [...pieces].sort().join(',');
  return f;
}

if (import.meta.main) {
  let f = EVERYTHING;
  if (process.env.EVENT === 'pull_request') {
    // PR merge checkout: HEAD^1 is the current base, so the diff is what the PR changes on it.
    const git = (...a: string[]) => execFileSync('git', a, { encoding: 'utf8' });
    const files = git('diff', '--name-only', 'HEAD^1', 'HEAD').split('\n').filter(Boolean);
    const read = (a: string, when: 'before' | 'after') => {
      try { return JSON.parse(execFileSync('git', ['show', `${when === 'before' ? 'HEAD^1' : 'HEAD'}:${a}`], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'], maxBuffer: 1e8 })); } catch { return null; }
    };
    f = filter(files, read);
    console.error(`${files.length} files changed:\n  ${files.join('\n  ')}`);
  }
  console.error(JSON.stringify(f));
  console.log(`fit=${f.fit}\nphones=${f.phones}\nvisual_qa=${f.visualQa}\npieces=${f.pieces}`);
}
