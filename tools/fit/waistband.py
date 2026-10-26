"""Raises the middle of a waistband that sank into a V (bermuda 001, shorts 008, trousers 002 and skirt 009 at the limit).

The 3D generator leaves the back (or front) waistband 5 to 10 cm below the sides, showing the inside in the middle
of the back; the shop photo shows a straight waistband. It measures the top edge of the piece per angle around the
waist (0° = front) and, where it sits more than TOL below the line between the sides (±90°), raises the edge to TOL
below that line. The rise fades linearly down to the hem (the whole panel slides, without concentrating the stretch
on the pocket) and the waistband's gap to the lower back hardly changes; what
would go into the body (fabric of the gluteal cleft rising to the sacrum) moves out along the normal to SLACK. Only
positions and normals change; UV and texture stay the same. Refuses a p99 edge stretch above MAX_STRETCH.
usage: python3 tools/fit/waistband.py INPUT.glb OUTPUT.glb
       python3 tools/fit/waistband.py --measure NNN ...   (sinking of the waistband per piece, in cm)"""
import sys, numpy as np, trimesh
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix, diags
from scipy.ndimage import gaussian_filter1d
from garment import Garment
from metric import POSE_C, body
from paths import GARMENTS, piece_id

TOL = .02           # a waistband middle up to 2 cm below the line of the sides stays as it is (low-rise waistband)
BAND = .15          # from the top down: where the top edge is measured
BIN = 5             # degrees per slice around the waist
SLACK = .005        # minimum distance from the body for the fabric that rose
MAX_STRETCH = .30   # p99 of the stretch of the edges that change


def weld(P, faces):
    _, inv = np.unique(np.round(P, 5), axis=0, return_inverse=True); inv = inv.ravel()
    X = np.zeros((inv.max() + 1, 3)); X[inv] = P
    return X, inv, inv[faces]


def edge(X):
    """Height of the top edge per slice of BIN degrees (0° = front, x to the right) and the angle of each vertex."""
    top = X[:, 1].max(); high = X[:, 1] > top - BAND
    c = X[high][:, [0, 2]].mean(0)
    ang = np.degrees(np.arctan2(X[:, 0] - c[0], X[:, 2] - c[1])) % 360
    n = 360 // BIN; b = (ang // BIN).astype(int) % n
    E = np.full(n, np.nan)
    for i in range(n):
        m = high & (b == i)
        if m.any(): E[i] = X[m, 1].max()
    ok = ~np.isnan(E); idx = np.arange(n)
    E = np.interp(idx, idx[ok], E[ok], period=n)
    return E, ang


def target(E):
    """Line between the sides (90° and 270°) for the front and for the back; rise = how far the edge sits below it beyond TOL."""
    n = len(E); a = np.arange(n) * BIN + BIN / 2
    side = lambda g: E[(np.abs(((a - g + 180) % 360) - 180) <= 10)].max()   # side: highest point within ±10°
    d, e = side(90), side(270)
    # front (270→360→90) and back (90→270): linear interpolation by angle
    T = np.empty(n)
    back = (a >= 90) & (a <= 270)
    T[back] = d + (e - d) * (a[back] - 90) / 180
    af = (a[~back] - 270) % 360
    T[~back] = e + (d - e) * af / 180
    rise = np.maximum(T - TOL - E, 0)
    # smooth it and zero it at the sides: the front's rise cannot lift the side (which is the back's reference)
    rise = gaussian_filter1d(rise, 15 / BIN, mode='wrap') * np.abs(np.cos(np.radians(a)))
    return rise, T


def sunken_cm(X):
    E, _ = edge(X); rise, T = target(E)
    a = np.arange(len(E)) * BIN + BIN / 2
    middle = lambda g: float((T - E)[np.abs(((a - g + 180) % 360) - 180) <= 10].max())
    return round(100 * middle(0), 1), round(100 * middle(180), 1)


def raise_waistband(src, dst):
    g = Garment(src); P0 = g.vertices(); m = g.mesh(P0)
    X0, inv, F = weld(P0, m.faces)
    E, ang = edge(X0); rise, _ = target(E)
    n = len(E); s = np.interp(ang, np.arange(n) * BIN + BIN / 2, rise, period=360)
    e = np.interp(ang, np.arange(n) * BIN + BIN / 2, E, period=360)
    # fades linearly from the edge to the hem (the lowest point of the piece at that angle)
    bottom = X0[:, 1].min()
    w = np.clip((X0[:, 1] - bottom) / np.maximum(e - bottom, 1e-6), 0, 1)
    X = X0.copy(); X[:, 1] += s * w
    # the fabric that rose from the gluteal curve to the sacrum would go into the body: it moves out along the normal to the gap it had
    pid = piece_id(src)
    b = body('C' if pid in POSE_C else 'B')
    S, fi = trimesh.sample.sample_surface_even(b, 300000, seed=1); SN = b.face_normals[fi]; T = cKDTree(S)
    def side(Y):
        _, j = T.query(Y); return np.einsum('ij,ij->i', Y - S[j], SN[j]), j
    d0 = side(X0)[0]; floor = np.where(d0 >= 0, SLACK, d0)   # what already poked through stays where it was
    moves = s * w > 1e-4
    # push smoothed over the mesh (vertex by vertex the fabric wrinkles)
    ed = trimesh.Trimesh(X0, F, process=False).edges_unique
    A = coo_matrix((np.ones(2 * len(ed)), (np.r_[ed[:, 0], ed[:, 1]], np.r_[ed[:, 1], ed[:, 0]])), shape=(len(X0),) * 2).tocsr()
    A = diags(1 / np.maximum(np.asarray(A.sum(1)).ravel(), 1)) @ A
    for _ in range(12):
        d1, j = side(X[moves])
        push = np.zeros_like(X); push[moves] = SN[j] * np.maximum(floor[moves] - d1, 0)[:, None]
        for _ in range(8): push = .5 * push + .5 * (A @ push)
        X += push * 1.5
    # stretch
    ed = trimesh.Trimesh(X0, F, process=False).edges_unique
    l0 = np.linalg.norm(X0[ed[:, 0]] - X0[ed[:, 1]], axis=1); l1 = np.linalg.norm(X[ed[:, 0]] - X[ed[:, 1]], axis=1)
    changed = np.abs(l1 - l0) > 1e-5
    est = np.abs(l1[changed] / np.maximum(l0[changed], 1e-6) - 1)
    p99 = float(np.percentile(est, 99)) if changed.any() else 0.0
    print(f'{src}: waistband sunken front/back {sunken_cm(X0)} -> {sunken_cm(X)} cm; max rise {100 * s.max():.1f} cm; '
          f'stretch p99 {100 * p99:.0f}% on {changed.sum()} edges')
    if p99 > MAX_STRETCH:
        sys.exit(f'refused: stretch p99 {100 * p99:.0f}% > {100 * MAX_STRETCH:.0f}%')
    g.save(dst, X[inv], before=P0)


if __name__ == '__main__':
    if sys.argv[1:2] == ['--measure']:
        for pid in sys.argv[2:]:
            g = Garment(GARMENTS + f'{pid}.glb'); X, _, _ = weld(g.vertices(), g.mesh().faces)
            print(pid, 'waistband sunken front/back (cm):', sunken_cm(X))
    else:
        raise_waistband(*sys.argv[1:3])
