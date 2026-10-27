"""Tears in the short-sleeve tops, on the whole mesh: faces of zero area (a cut that keeps its edges) and open boundary
(a cut that removes faces), on the sleeve, the torso and the shoulder alike. poke_through.py does not count as a hole a
clipped arm whose far wall is closer than HIDDEN, which is what a tight sleeve shows through a tear; this check holds
that tear, and any other. No published top has a zero-area face. EDGE holds, in cm, the open boundary each top has
(its hems, neckline and armholes): a cut adds to it (removing a face with one edge on the hem adds the other two),
so the measure must equal EDGE. EDGE only goes down: each top is also measured as main has it (git show origin/main),
and EDGE may not pass that, whatever changed in the measure.
usage: python3 tools/fit/sleeve_tear.py [IDs]   (without IDs: the tops of sleeve.IDS; exits with an error on a tear)"""
import os, subprocess, sys, tempfile, numpy as np
from garment import Garment
import sleeve
from paths import GARMENTS

AREA = 1e-9    # m²: a face this small is a cut that kept its edges
EDGE = {
    '016': 202.7,
    '017': 257.2,
    '018': 280.0,
    '019': 292.3,
    '020': 248.7,
    '021': 246.9,
    '022': 288.2,
    '024': 276.1,
    '025': 234.3,
    '026': 267.8,
    '029': 243.0,
    '030': 0.0,
    '032': 295.9,
}
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def tears(path):
    """(zero-area faces, cm of open boundary) of the garment at `path`."""
    m = Garment(path).mesh()
    flat = int((m.area_faces < AREA).sum())
    _, inv = np.unique(np.round(m.vertices, 5), axis=0, return_inverse=True); inv = inv.ravel()
    F = inv[m.faces]; X = np.zeros((inv.max() + 1, 3)); X[inv] = m.vertices
    E = np.sort(np.vstack([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]), axis=1)
    u, c = np.unique(E, axis=0, return_counts=True); b = u[c == 1]
    return flat, round(float(np.linalg.norm(X[b[:, 0]] - X[b[:, 1]], axis=1).sum()) * 100, 1)


def on_main(pid):
    """The same measure on the top as main has it; None where main has no such file. Without origin/main the CI fails
    (the checkout needs fetch-depth 0); locally it is skipped."""
    r = subprocess.run(['git', 'show', f'origin/main:site/assets/garments/{pid}.glb'], cwd=ROOT, capture_output=True)
    if r.returncode:
        if subprocess.run(['git', 'rev-parse', '--verify', '-q', 'origin/main'], cwd=ROOT, capture_output=True).returncode:
            if os.environ.get('CI'): sys.exit('origin/main is missing: fetch it to hold EDGE to main')
            print('origin/main is missing: EDGE not compared with main', file=sys.stderr)
        return None
    with tempfile.NamedTemporaryFile(suffix=f'-{pid}.glb') as f:
        f.write(r.stdout); f.flush()
        return tears(f.name)[1]


if __name__ == '__main__':
    bad = []
    for pid in sys.argv[1:] or sleeve.IDS:
        flat, edge = tears(GARMENTS + f'{pid}.glb')
        main = on_main(pid)
        print(pid, 'zero-area faces', flat, 'open boundary', edge, 'cm', '' if main is None else f'(main {main})', flush=True)
        if flat or edge != EDGE.get(pid) or (main is not None and EDGE[pid] > main): bad.append(pid)
    if bad: sys.exit('tear, or EDGE not equal to the measure or above main: ' + ', '.join(bad))
