"""Calibration of the fit checks: each check must fail the garment as it was when the defect was seen (before) and
pass it once fixed (after).

reference/calibration/<case>/{before,after}/ mirror site/assets/ (garments/, masks/pose-b/, masks/pose-c/). For each
case the files are put in place of the published ones, each check of the case runs, and the published files come back
(also on error). A check that does not tell before from after is reported, not fixed here: it becomes a warning, and
a new check only enters if it fails the before of the defect that motivated it.
usage: python3 tools/fit/calibration.py [CASE ...]   (no cases: all; exits with an error if a check does not separate)"""
import os, shutil, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CORPUS = os.path.join(ROOT, 'tools/fit/reference/calibration')
ASSETS = os.path.join(ROOT, 'site/assets')
# case: the defect, and the checks that must separate it (command, run from the repository root)
CASES = {
    'bridge-013': ('strip of cloth hanging in the gap between the legs of trousers 013, down to the shoe', [
        'python3 tools/fit/cuff.py 013',
    ]),
    'large-jackets': ('jackets 036 and 038 too large for the body: sleeve past the fingers, hem at the crotch', [
        "bun test site/fit.test.ts -t 'long sleeves'",
        "bun test site/fit.test.ts -t 'no lining hanging'",
    ]),
}


def files(state):
    return [os.path.relpath(os.path.join(d, f), state) for d, _, fs in os.walk(state) for f in fs]


def run(case, state):
    """Exit code of each check with the case's files of `state` in place of the published ones."""
    src = os.path.join(CORPUS, case, state); keep = tempfile.mkdtemp()
    names = files(src)
    try:
        for n in names:
            os.makedirs(os.path.dirname(os.path.join(keep, n)), exist_ok=True)
            shutil.copy2(os.path.join(ASSETS, n), os.path.join(keep, n))
            shutil.copy2(os.path.join(src, n), os.path.join(ASSETS, n))
        return [subprocess.run(c, shell=True, cwd=ROOT, capture_output=True).returncode for c in CASES[case][1]]
    finally:
        for n in names: shutil.copy2(os.path.join(keep, n), os.path.join(ASSETS, n))
        shutil.rmtree(keep)


if __name__ == '__main__':
    bad = []
    print('| check | case | before | after |\n|---|---|---|---|')
    for case in sys.argv[1:] or CASES:
        before, after = run(case, 'before'), run(case, 'after')
        for c, b, a in zip(CASES[case][1], before, after):
            print(f'| `{c}` | {case} | {"fails" if b else "passes"} | {"fails" if a else "passes"} |')
            if not b or a: bad.append(f'{case}: {c}')
    if bad: sys.exit('does not separate before from after: ' + '; '.join(bad))
