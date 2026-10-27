"""Calibration of the fit checks: each check must fail the garment as it was when the defect was seen (before) and
pass it once fixed (after).

reference/calibration/<case>/{before,after}/ mirror site/assets/ (garments/, masks/pose-b/, masks/pose-c/). For each
case the checks run in a temporary copy of the repository (tools/ and site/ copied, links to the rest) with
the case's files in place of the published ones, so site/assets itself is never written. A check that does not tell before from after is reported, not fixed here: it becomes a warning, and
a new check only enters if it fails the before of the defect that motivated it.
usage: python3 tools/fit/calibration.py [--visual] [CASE ...]   (no cases: all; --visual: the cases measured in the site's
       pictures; exits with an error if a check does not separate)"""
import os, shutil, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CORPUS = os.path.join(ROOT, 'tools/fit/reference/calibration')
# case: the defect, and the checks that must separate it (command, run from the repository root)
CASES = {
    'bridge-013': ('strip of cloth hanging in the gap between the legs of trousers 013, down to the shoe', [
        'python3 tools/fit/cuff.py 013',
    ]),
    'hip-014': ('hip of trousers 014 standing outside the tops\' hems: the layer tables hid it in slivers that showed the '
                'background, and the waistband poked through the tops', [
        'python3 tools/fit/layer_check.py --max-pokes 1500 --max-holes 5500 --max-total-pokes 90000 '
        '--max-total-holes 185000 --no-cache 014.016 014.017 014.018 014.019 014.020 014.021 014.022 014.023 014.024 014.025 014.026 014.027 014.028 014.029 014.030 014.031 014.032 014.033 014.034 014.035 014.036 014.037 014.038',
    ]),
    'projected-014': ('trousers 014 rebuilt on the neutral mannequin: the hem wrapped over the sneaker like a boot cover, the '
                      'side stripes wider, broken where the hip met the legs, and the other leg\'s stripes on the inner side', [
        'python3 tools/fit/shoe.py 014',
        'python3 tools/fit/print_check.py 014',
    ]),
    'large-jackets': ('jackets 036 and 038 too large for the body: sleeve past the fingers, hem at the crotch', [
        "bun test site/fit.test.ts -t 'long sleeves'",
        "bun test site/fit.test.ts -t 'no lining hanging'",
        'python3 tools/fit/layer_check.py --max-pokes 1500 --max-holes 5500 --max-total-pokes 90000 --max-total-holes 185000 '
        '--no-cache 001.036 002.036 003.036 004.036 005.036 006.036 007.036 008.036 009.036 010.036 011.036 012.036 013.036 014.036 015.036 001.038 002.038 003.038 004.038 005.038 006.038 007.038 008.038 009.038 010.038 011.038 012.038 013.038 014.038 015.038',
        'python3 tools/fit/back_inside.py',
    ]),
    'hem-hole-002': ('hole of 9.6 cm in the hem of trousers 002, left by the generator: dressed as cloth, the body shows '
                     'through it from behind, and main\'s 002 had it and passed every check', [
        'python3 tools/fit/close_holes.py --check 002',
    ]),
    'torn-sleeve-022': ('63 faces cut out of the right sleeve of 022, 2 to 9 cm above the hem: the per-view arm clip keeps the '
                        'arm out of sight behind the tear, and only the arm clipped with no cloth in front tells it', [
        'python3 tools/fit/poke_through.py 022',
        'python3 tools/fit/sleeve_tear.py 022',
    ]),
    'torn-sleeve-020': ('17 faces of the right sleeve of 020 cut to zero area, 0.4 to 3.2 cm above the hem: seen from below the '
                        'arm behind the tear looks like the arm going up into the sleeve, which the visual measure leaves out', [
        'python3 tools/fit/sleeve_tear.py 020',
    ]),
    'notch-016': ('one face of 0.7 cm² cut out of the hem of 016, at the front: the open boundary grows by one edge and by '
                  'less than 0.05 cm, which the cm alone rounded away', [
        'python3 tools/fit/sleeve_tear.py 016',
    ]),
    'waistband-004': ('back of the waistband of trousers 004, dressed whole as cloth, slid 1.4 cm down the small of the back '
                      'and folded over, with the dark inside showing; the waist region of stretch.py passed it', [
        'python3 tools/fit/stretch.py 004',
    ]),
    'cords-009': ('cords hanging down the front of skirt 009, which the 3D model drew where the photo has buttons', [
        'python3 tools/fit/cords.py --measure --max 10',
    ]),
    'inside-body-007': ('skirt 007 as Tripo made it on its mannequin: 5.4% of the covered neutral body inside it, 14% at the hip, '
                        'and the body poking through it', [
        'python3 tools/fit/penetration.py',
        'python3 tools/fit/poke_through.py --max-pokes 50 --max-holes 7000 --max-bottom-pokes 30 007',
    ]),
    'cuff-tip-021': ('tip of the left cuff of 021 hanging 4 cm below the rim, a beige V over the arm', [
        'python3 tools/fit/cuff_tip.py --check',
        'python3 tools/fit/sleeve.py --check',
    ]),
}


# cases measured in the site's own pictures (tools/visual-qa/measure.py): they build the site and photograph it with
# chromium, so they run with --visual in the visual-qa job (site-e2e.yml), not in the fit job
RENDER = ('cd site && GITHUB_SHA=calibration bun run build > /dev/null && cd .. && node tools/verify-site/visual-qa.mjs '
          '--looks {} --out site/verify-out/calibration > /dev/null && python3 tools/visual-qa/measure.py '
          'site/verify-out/calibration --ci')
VISUAL_CASES = {
    'large-jackets': ('jackets 036 and 038 too large for the body, seen in the site: the body poking through 036 and its hem '
                      'loose over trousers 006, the junction of 038 over shorts 008 jagged', [
        RENDER.format('006.036,008.038'),
    ]),
    'hip-014': ('hip of trousers 014 outside the tops\' hems, seen in the site: slivers of the hip loose beside the hem of '
                '022 and the body poking through the cloth of 014.035', [
        RENDER.format('014.022,014.035'),
    ]),
    'slit-033': ('slit to the background between the left sleeve of jacket 033 and its side, where the hidden arm would '
                 'be, seen from the front with shorts 003', [
        RENDER.format('003.033'),
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
        elif n in ('dist', 'verify-out'): continue   # built and photographed in the copy, never into the real ones
        elif os.path.isdir(s): os.symlink(s, d)
        else: shutil.copy2(s, d)


def run(case, state, cases=CASES):
    """Exit code of each check with the case's files of `state` in place of the published ones."""
    src = os.path.join(CORPUS, case, state); dst = tempfile.mkdtemp()
    try:
        tree(dst)
        for n in files(src): shutil.copy2(os.path.join(src, n), os.path.join(dst, 'site/assets', n))
        # the repository's git, for the checks that compare with main (sleeve_tear.py)
        git = subprocess.run(['git', 'rev-parse', '--absolute-git-dir'], cwd=ROOT, capture_output=True, text=True).stdout.strip()
        env = dict(os.environ, GIT_DIR=git) if git else None
        return [subprocess.run(c, shell=True, cwd=dst, capture_output=True, env=env).returncode for c in cases[case][1]]
    finally:
        shutil.rmtree(dst)


if __name__ == '__main__':
    bad = []; args = [a for a in sys.argv[1:] if a != '--visual']
    cases = VISUAL_CASES if '--visual' in sys.argv else CASES
    print('| check | case | before | after |\n|---|---|---|---|')
    for case in args or cases:
        before, after = run(case, 'before', cases), run(case, 'after', cases)
        for c, b, a in zip(cases[case][1], before, after):
            print(f'| `{c}` | {case} | {"fails" if b else "passes"} | {"fails" if a else "passes"} |')
            if not b or a: bad.append(f'{case}: {c}')
    if bad: sys.exit('does not separate before from after: ' + '; '.join(bad))
