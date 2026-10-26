"""Calibration of the fit checks: each check must fail the garment as it was when the defect was seen (before) and
pass it once fixed (after).

reference/calibration/<case>/{before,after}/ mirror site/assets/ (garments/, masks/pose-b/, masks/pose-c/). For each
case the checks run in a temporary copy of the repository (tools/ and site/ copied, links to the rest) with
the case's files in place of the published ones, so site/assets itself is never written. A check that does not tell before from after is reported, not fixed here: it becomes a warning, and
a new check only enters if it fails the before of the defect that motivated it.
usage: python3 tools/fit/calibration.py [CASE ...]   (no cases: all; exits with an error if a check does not separate)"""
import os, shutil, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CORPUS = os.path.join(ROOT, 'tools/fit/reference/calibration')
# case: the defect, and the checks that must separate it (command, run from the repository root)
CASES = {
    'bridge-013': ('strip of cloth hanging in the gap between the legs of trousers 013, down to the shoe', [
        'python3 tools/fit/cuff.py 013',
    ]),
    'projected-014': ('trousers 014 rebuilt on the neutral mannequin: the hem wrapped over the sneaker like a boot cover, the '
                      'side stripes wider, broken where the hip met the legs, and the other leg\'s stripes on the inner side', [
        'python3 tools/fit/shoe.py 014',
        'python3 tools/fit/print_check.py 014',
    ]),
    'large-jackets': ('jackets 036 and 038 too large for the body: sleeve past the fingers, hem at the crotch', [
        "bun test site/fit.test.ts -t 'long sleeves'",
        "bun test site/fit.test.ts -t 'no lining hanging'",
    ]),
    'cuff-tip-021': ('tip of the left cuff of 021 hanging 4 cm below the rim, a beige V over the arm', [
        'python3 tools/fit/cuff_tip.py --check',
    ]),
}


def files(state):
    return [os.path.relpath(os.path.join(d, f), state) for d, _, fs in os.walk(state) for f in fs]


def tree(dst):
    """A copy of the repository in `dst` that the checks can run in: tools/ and site/assets copied, the rest of site/
    copied file by file and everything else linked. Python and bun resolve a linked script or test to its real path, and
    with it the assets, so what finds site/assets is never a link."""
    for n in os.listdir(ROOT):
        if n == 'tools': shutil.copytree(os.path.join(ROOT, n), os.path.join(dst, n), symlinks=True)
        elif n not in ('site', '.git'): os.symlink(os.path.join(ROOT, n), os.path.join(dst, n))
    site = os.path.join(ROOT, 'site'); os.mkdir(os.path.join(dst, 'site'))
    for n in os.listdir(site):
        s, d = os.path.join(site, n), os.path.join(dst, 'site', n)
        if n == 'assets': shutil.copytree(s, d)
        elif os.path.isdir(s): os.symlink(s, d)
        else: shutil.copy2(s, d)


def run(case, state):
    """Exit code of each check with the case's files of `state` in place of the published ones."""
    src = os.path.join(CORPUS, case, state); dst = tempfile.mkdtemp()
    try:
        tree(dst)
        for n in files(src): shutil.copy2(os.path.join(src, n), os.path.join(dst, 'site/assets', n))
        return [subprocess.run(c, shell=True, cwd=dst, capture_output=True).returncode for c in CASES[case][1]]
    finally:
        shutil.rmtree(dst)


if __name__ == '__main__':
    bad = []
    print('| check | case | before | after |\n|---|---|---|---|')
    for case in sys.argv[1:] or CASES:
        before, after = run(case, 'before'), run(case, 'after')
        for c, b, a in zip(CASES[case][1], before, after):
            print(f'| `{c}` | {case} | {"fails" if b else "passes"} | {"fails" if a else "passes"} |')
            if not b or a: bad.append(f'{case}: {c}')
    if bad: sys.exit('does not separate before from after: ' + '; '.join(bad))
