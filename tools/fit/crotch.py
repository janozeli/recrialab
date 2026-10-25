"""Opens the crotch of shorts 008: the mesh joined the two legs with a membrane below the body's crotch.

In the shop photo the legs of the shorts separate just below the crotch; the 3D generator made a floor of fabric
between the thighs, 4 cm below the body's crotch, which from the front and back shows as a dark membrane (the
texture there is shadow). Each vertex in the gap between the thighs (|x| smaller than half the distance between the
thighs at that height, plus MARGIN) rises to 4 mm below the body, along the vertical ray; over BAND beyond that the
rise fades linearly, so the thigh fabric follows without tearing. Only positions and normals change; UV and texture
stay the same.
usage: python3 tools/fit/crotch.py INPUT.glb OUTPUT.glb
       python3 tools/fit/crotch.py --measure [--max N] NNN ...   (fabric in the gap between the thighs below the body's crotch,
                                                      in cm²; with --max exits with an error above N. Only valid for
                                                      shorts: on a skirt or trousers the fabric around the thigh
                                                      also falls in the gap)"""
import sys, numpy as np, trimesh
from trimesh.ray.ray_pyembree import RayMeshIntersector
from garment import Garment
from metric import POSE_C, body
from paths import GARMENTS

MARGIN = .004   # beyond the gap between the thighs (thickness of the leg fabric)
BAND = .015     # the rise fades linearly over this band beyond the margin
SLACK = .004    # distance from the body to the fabric that rose


def weld(P, faces):
    _, inv = np.unique(np.round(P, 5), axis=0, return_inverse=True); inv = inv.ravel()
    X = np.zeros((inv.max() + 1, 3)); X[inv] = P
    return X, inv, inv[faces]


def gap(b):
    """The body's crotch (height where the thighs separate) and half the distance between the thighs per height."""
    ys = np.arange(.60, .90, .005); half = []
    for y in ys:
        P = b.section([0, 1, 0], [0, y, 0]).vertices; P = P[np.abs(P[:, 2]) < .06]
        half.append(np.abs(P[:, 0]).min())
    half = np.array(half)
    return ys[np.argmax(half < 1e-3)], ys, half


def membrane(X, b):
    """Rise weight per vertex: 1 in the gap between the thighs, 0 at BAND from it; only below the body's crotch."""
    crotch, ys, half = gap(b)
    m = np.interp(X[:, 1], ys, half) + MARGIN
    w = np.clip(1 - (np.abs(X[:, 0]) - m) / BAND, 0, 1)
    w[X[:, 1] >= crotch] = 0
    return w, crotch


def gap_area(g, b):
    """Fabric area (cm²) in the gap between the thighs below the body's crotch: the floor joining the legs."""
    X, _, F = weld(g.vertices(), g.mesh().faces)
    w, _ = membrane(X, b)
    m = trimesh.Trimesh(X, F, process=False)
    return float(m.area_faces[(w[F] >= 1).all(1)].sum() * 1e4)


def open_crotch(src, dst):
    g = Garment(src); P0 = g.vertices(); m0 = g.mesh(P0)
    X0, inv, F = weld(P0, m0.faces)
    b = body('C' if src.split('light')[-1][:3] in POSE_C else 'B')
    w, crotch = membrane(X0, b)
    moves = w > 0
    hit = RayMeshIntersector(b).intersects_location(X0[moves], np.tile([0, 1., 0], (moves.sum(), 1)), multiple_hits=False)
    loc, ir = hit[0], hit[1]
    idx = np.nonzero(moves)[0]
    top = np.full(len(idx), crotch - SLACK); top[ir] = loc[:, 1] - SLACK
    # a ray that only finds the body far away started inside the buttock (the gap closes at the back): that vertex stays
    rise = np.where(top - X0[idx, 1] < crotch - X0[idx, 1] + .02, np.maximum(top - X0[idx, 1], 0), 0)
    X = X0.copy(); X[idx, 1] += rise * w[idx]
    print(f'{src}: fabric in the gap between the thighs {gap_area(g, b):.1f} cm² -> ', end='')
    g.save(dst, X[inv], before=P0)
    print(f'{gap_area(Garment(dst), b):.1f} cm²; {moves.sum()} vertices, max rise {100 * (X - X0)[:, 1].max():.1f} cm')


if __name__ == '__main__':
    if sys.argv[1:2] == ['--measure']:
        a = sys.argv[2:]; lim = float(a[1]) if a[:1] == ['--max'] else None; a = a[2:] if lim is not None else a
        bad = []
        for pid in a:
            v = gap_area(Garment(GARMENTS + f'{pid}.glb'), body('C' if pid in POSE_C else 'B'))
            print(pid, f'{v:.1f} cm²')
            if lim is not None and v > lim: bad.append(pid)
        if bad: sys.exit(f'legs joined by fabric below the crotch: {" ".join(bad)} (> {lim} cm²)')
    else:
        open_crotch(*sys.argv[1:3])
