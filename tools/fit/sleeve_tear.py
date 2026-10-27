"""Tears in the short sleeves, on the mesh: faces of zero area (a cut that keeps the edges) and open boundary on the
sleeve, above its hem and below the armpit (a cut that removes faces). poke_through.py does not count as a hole a
clipped arm whose far wall is closer than HIDDEN, which is what a tight sleeve shows through a tear; this check holds
that tear. EDGE holds, in cm, the boundary the published sleeves already have there (the hem of a sleeve that rises
above its line, a seam left open by the armhole), a baseline that only goes down: a tear that reaches the hem or the
armhole adds to it as much as one in the middle of the sleeve.
usage: python3 tools/fit/sleeve_tear.py [IDs]   (without IDs: the tops of sleeve.IDS; exits with an error on a tear)"""

import sys, json, numpy as np
from garment import Garment
import sleeve
from paths import GARMENTS, MASKS

AREA = 1e-9    # m²: a face this small is a cut that kept its edges
TOP = 1.5      # m: the armpit; the sleeve is looked at from its hem up to here
HEM = .003     # m: above the hem line by this (the line has SLACK above the hem, sleeve.py)
EDGE = {
    '017': 41.2,
    '018': 27.5,
    '019': 45.0,
    '020': 3.4,
    '021': 25.9,
    '022': 25.5,
    '024': 58.8,
    '025': 29.3,
    '026': 9.0,
    '029': 30.7,
    '032': 36.8,
}


def on_sleeve(P, L):
    return (np.abs(P[:, 0]) > sleeve.ARM_X) & (P[:, 1] > sleeve.on_line(P, L) + HEM) & (P[:, 1] < TOP) \
        & (np.linalg.norm(sleeve.plane(P), axis=1) < .12)


def tears(pid, mesh=None):
    """(zero-area faces, cm of open boundary) on the sleeve of `pid`."""
    m = mesh or Garment(GARMENTS + f'{pid}.glb').mesh()
    L = np.array(json.load(open(MASKS + f'pose-b/{pid}.json'))['sleeve_line'])
    flat = int((on_sleeve(m.triangles_center, L) & (m.area_faces < AREA)).sum())
    _, inv = np.unique(np.round(m.vertices, 5), axis=0, return_inverse=True); inv = inv.ravel()
    F = inv[m.faces]; X = np.zeros((inv.max() + 1, 3)); X[inv] = m.vertices
    E = np.sort(np.vstack([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]), axis=1)
    u, c = np.unique(E, axis=0, return_counts=True); b = u[c == 1]
    b = b[on_sleeve(X[b[:, 0]], L) & on_sleeve(X[b[:, 1]], L)]
    return flat, round(float(np.linalg.norm(X[b[:, 0]] - X[b[:, 1]], axis=1).sum()) * 100, 1)


if __name__ == '__main__':
    bad = []
    for pid in sys.argv[1:] or sleeve.IDS:
        flat, edge = tears(pid)
        print(pid, 'zero-area faces', flat, 'open boundary', edge, 'cm', flush=True)
        if flat or edge > EDGE.get(pid, 0): bad.append(pid)
    if bad: sys.exit('tear in the sleeve: ' + ', '.join(bad))
