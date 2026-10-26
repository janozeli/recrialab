"""Lays the hood and collar flat on the back, where the 3D generator left them standing up behind the nape.

The generator dressed the pieces on a straight-necked mannequin and left the hood full of air, standing more than
10 cm behind the nape (in profile, a flap coming off the shoulder). A cloth hood falls on the back. Here each vertex of the back column (|x| up to 19 cm, from the upper back up) moves forward,
only in z, by what exceeds D0 behind the body's back, keeping K of that excess; the displacement is smoothed in space
(a gaussian kernel of RADIUS, as in displacement_field.py), so lining and outer fabric move together, and nothing gets
closer than 5 mm to the body's back. x and y do not change: from the front and from behind the piece stays the same,
and so do print and UV. The hood flattens: edges going backwards shrink (only visible in profile), with their own
limit (MAX_SHRINK, p99) and on the area of what moves (MAX_AREA); it also refuses p99 stretch above MAX_STRETCH and
flipped triangles.
The input is always the GLB in ORIGINAL, from before hood.py ever ran, and the limits are measured against it, so that runs
cannot add up past them.
The front of a high collar can come out of the generator narrower than the mannequin's neck, inside it (035): on the
site the collar shows open, with the neck inside. For the pieces in CLOSE the collar (above COLLAR_Y, within
COLLAR_R of the neck axis) is pushed out of the neck, by a displacement smoothed in space, until it sits MARGIN
outside it; the plain collar stretches (MAX_COLLAR_STRETCH, p99 of its edges), and only there x changes. A piece
in CLOSE must be named by the known issue stretched-collar (tools/known-issues.yaml).
The check in site/fit.test.ts (hoodBehindCm) measures how far behind the body's back the piece sits, at the middle and
6 cm to each side; --check (CI) measures each published piece against ORIGINAL again.
usage: python3 tools/fit/hood.py --measure   (each top, in cm)
       python3 tools/fit/hood.py --check     (published piece against ORIGINAL: only z changes, within the limits)
       python3 tools/fit/hood.py 033 037     (writes; then install.py --mask 033 037 and layer_tables.py)"""
import os, sys, json, hashlib, tempfile, numpy as np
from trimesh.ray.ray_pyembree import RayMeshIntersector
from garment import Garment, kernel
from metric import body
from paths import GARMENTS, MASKS
from mask_io import hidden_indices
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'visual-qa'))
from known_issues import known_issues

D0, K, RADIUS = .035, .3, .03      # m, fraction of the excess that stays, m
RADIUS_PIECE = {
    '030': .025,               # collar of 030: the default radius leaves it behind the hoodBehindCm check
    '035': .05,                # high collar of 035: the default radius flips triangles of the nape seam
}
K_PIECE = {
    '030': 0,                  # collar of 030: keeping part of the excess leaves the nape past the 5 cm limit
}
CLOSE = {
    '035': .012,               # m outside the neck: the front of the high collar sat inside it (open collar)
}
NECK_Z, COLLAR_Y, COLLAR_R, CLOSE_RADIUS, CLOSE_ROUNDS = -.008, 1.44, .17, .04, 6   # m, m, m, m, rounds
# body triangles the mask of the piece hides below KEPT_BELOW, kept by hand from before close() (sha256 of the sorted
# indices, 16 hex): a fresh install.py hides more of the torso at the hem and opens the 005.035 tear
KEPT_BELOW = 1.40
KEPT = {
    '035': '4045696c1c3e8f2d',
}
MAX_COLLAR_STRETCH = .90         # p99 of the collar edges that stretch: a collapsed plain collar opening around the neck
MAX_INSIDE = .03                 # m: deepest a closed collar vertex may stay inside the neck; on 035 two points at the top centre stay 2.9 cm in, under the collar, and one more round passes MAX_COLLAR_STRETCH
ORIGINAL = 'tools/fit/reference/originals/before-hood'   # pieces before hood.py first ran
PIECES = [
    '030',
    '033',
    '034',
    '035',
    '036',
    '037',
]
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..')
SOFT = .01                       # m: the excess starts slowly near D0
MAX_STRETCH = .10                # p99 of the edges that stretch
MAX_SHRINK = .40                 # p99 of those that shrink: the hood flattens in z (from front and back the piece is the same)
MAX_AREA = .05                   # area lost in what moves: real fabric folds, it does not vanish


def behind_cm(P, b):
    """The same as hoodBehindCm in site/fit.test.ts: in three columns (x = -6, 0 and 6 cm) and per 2 cm slice from 1.30
    to 1.66 m, the body's back (the rearmost triangle the line crosses) minus the rearmost point of the piece within
    2.5 cm of the column; the largest."""
    ys = np.arange(1.30, 1.661, .02); out = 0
    for x0 in (-.06, 0, .06):
        loc, idx, _ = RayMeshIntersector(b).intersects_location(np.c_[0 * ys + x0, ys, 0 * ys - 1], np.tile([0, 0, 1.], (len(ys), 1)), multiple_hits=False)
        for z, k in zip(loc[:, 2], idx):
            g = P[(np.abs(P[:, 0] - x0) < .025) & (np.abs(P[:, 1] - ys[k]) < .01)]
            if len(g): out = max(out, (z - g[:, 2].min()) * 100)
    return out


def original(pid):
    with tempfile.NamedTemporaryFile(suffix='.glb') as f:
        f.write(open(os.path.join(ROOT, ORIGINAL, f'{pid}.glb'), 'rb').read()); f.flush()
        return Garment(f.name).vertices()


def collar(P):
    """Vertices of the collar that CLOSE pushes out of the neck."""
    return (P[:, 1] > COLLAR_Y) & (np.hypot(P[:, 0], P[:, 2] - NECK_Z) < COLLAR_R)


def shrink_limits(g, P, Q, closed=False):
    """Summary text and whether it is refused, from P (ORIGINAL) to Q. With closed, the stretch of the collar's
    edges answers to MAX_COLLAR_STRETCH instead of MAX_STRETCH; shrink, area and flips count every edge."""
    m0, m1 = g.mesh(P), g.mesh(Q); E = m0.edges_unique
    e = np.linalg.norm(Q[E[:, 0]] - Q[E[:, 1]], axis=1) / np.maximum(np.linalg.norm(P[E[:, 0]] - P[E[:, 1]], axis=1), 1e-9) - 1
    inner = collar(P)[E].all(1) if closed else np.zeros(len(E), bool)
    collar_stretch = np.percentile(np.maximum(e[inner], 0), 99) if inner.any() else 0
    moves = np.abs(e) > 1e-6
    rest = moves & ~inner
    stretch = np.percentile(np.maximum(e[rest], 0), 99) if rest.any() else 0
    shrink = np.percentile(np.maximum(-e[moves], 0), 99) if moves.any() else 0
    A0, A1 = m0.area_faces, m1.area_faces; fm = np.abs(A1 / np.maximum(A0, 1e-12) - 1) > 1e-6
    area = 1 - A1[fm].sum() / A0[fm].sum() if fm.any() else 0
    flipped = int(((m0.face_normals * m1.face_normals).sum(1) < 0).sum())
    summary = f'stretch p99 {100 * stretch:.1f}%, shrink p99 {100 * shrink:.1f}%, area {-100 * area:.1f}%, {flipped} flipped'
    if closed: summary += f', collar stretch p99 {100 * collar_stretch:.1f}%'
    bad = stretch > MAX_STRETCH or shrink > MAX_SHRINK or area > MAX_AREA or flipped or collar_stretch > MAX_COLLAR_STRETCH
    return summary, bad


def lay_down(P, b, radius=None, k=K):
    o = P.copy(); o[:, 2] = -1
    loc, idx, _ = RayMeshIntersector(b).intersects_location(o, np.tile([0, 0, 1.], (len(P), 1)), multiple_hits=False)
    zb = np.full(len(P), np.nan); zb[idx] = loc[:, 2]
    d = np.nan_to_num(zb - P[:, 2], nan=0.0)
    w = np.clip((P[:, 1] - 1.28) / .06, 0, 1) * np.clip((.19 - np.abs(P[:, 0])) / .04, 0, 1)
    delta = np.where(np.isfinite(zb), w * (1 - k) * SOFT * np.logaddexp(0, (d - D0) / SOFT), 0)
    N = kernel(P, radius or RADIUS)
    for _ in range(3): delta = N @ delta
    Q = P.copy(); Q[:, 2] += delta
    lim = np.where(np.isfinite(zb), zb - .005, np.inf)
    Q[:, 2] = np.minimum(Q[:, 2], np.maximum(P[:, 2], lim))
    return Q


def neck_gap(P, b):
    """Per collar vertex: distance outside the neck along the ray from the neck axis (negative: inside the neck)."""
    from gen_mask import first
    C = b.triangles_center; neck = np.nonzero((np.hypot(C[:, 0], C[:, 2] - NECK_Z) < .13) & (C[:, 1] > 1.40))[0]
    rb = RayMeshIntersector(b.submesh([neck], append=True))
    q = np.c_[P[:, 0], P[:, 2] - NECK_Z]; r = np.linalg.norm(q, axis=1); u = q / np.maximum(r, 1e-6)[:, None]
    t, _ = first(rb, np.c_[0 * r, P[:, 1], 0 * r + NECK_Z], np.c_[u[:, 0], 0 * r, u[:, 1]])
    return r - np.where(np.isfinite(t), t, 0), u


def close(P, b, margin):
    """Pushes the collar out of the neck: each round, the collar vertex closer than margin to the neck (from COLLAR_Y,
    fully 3 cm above; only x and z) gets the missing distance outwards, smoothed over CLOSE_RADIUS so the lining and the outer cloth
    move together."""
    Q = P.copy(); k = np.nonzero(collar(P))[0]
    for _ in range(CLOSE_ROUNDS):
        gap, u = neck_gap(Q[k], b)
        need = np.maximum(margin - gap, 0) * np.clip((Q[k, 1] - COLLAR_Y) / .03, 0, 1)
        D = np.zeros_like(Q); D[k, 0] = u[:, 0] * need; D[k, 2] = u[:, 1] * need
        N = kernel(Q, CLOSE_RADIUS)
        for _ in range(2): D = N @ D
        D[~collar(P)] = 0
        Q = Q + D
    return Q


if __name__ == '__main__':
    b = body('B')
    if sys.argv[1:] == ['--measure']:
        for n in range(16, 39):
            print(f'{n:03d} {behind_cm(Garment(GARMENTS + f"{n:03d}.glb").vertices(), b):.1f}')
        sys.exit()
    if sys.argv[1:] == ['--check']:
        bad = []
        for pid in PIECES:
            g = Garment(GARMENTS + f'{pid}.glb'); P, Q = original(pid), g.vertices()
            summary, refused = shrink_limits(g, P, Q, pid in CLOSE)
            free = collar(P) if pid in CLOSE else np.zeros(len(P), bool)   # close() moves x on the collar, never y
            if np.abs(P[~free, 0] - Q[~free, 0]).max() > 1e-6 or np.abs(P[:, 1] - Q[:, 1]).max() > 1e-6:
                summary, refused = summary + ', x or y changed', True
            top = collar(Q) & (Q[:, 1] > COLLAR_Y + .03)   # where close() pushes in full
            if pid in CLOSE and pid not in known_issues().get('stretched-collar', ()):
                summary, refused = summary + ', collar stretched without the known issue stretched-collar', True
            if pid in CLOSE and (inside := (neck_gap(Q[top], b)[0] < -MAX_INSIDE).sum()):
                summary, refused = summary + f', {inside} collar vertices more than {100 * MAX_INSIDE:.0f} cm inside the neck', True
            for pose in 'BC' if pid in KEPT else '':
                C = body(pose).triangles_center; m = json.load(open(MASKS + f'pose-{pose.lower()}/{pid}.json'))
                h = np.array(sorted(i for i in hidden_indices(m) if C[i, 1] < KEPT_BELOW), '<i4')
                if hashlib.sha256(h.tobytes()).hexdigest()[:16] != KEPT[pid]:
                    summary, refused = summary + f', pose {pose} mask below {KEPT_BELOW} m not the one kept (KEPT)', True
            print(pid, summary)
            if refused: bad.append(f'{pid}: {summary}')
        if bad: sys.exit('hood and collar outside the shrink limits against ' + ORIGINAL + ': ' + '; '.join(bad))
        sys.exit()
    for pid in sys.argv[1:]:
        if pid not in PIECES: sys.exit(f'{pid}: not in PIECES (add it; ORIGINAL must have the piece as input)')
        path = GARMENTS + f'{pid}.glb'; g = Garment(path); A = g.vertices(); P = original(pid)
        Q = lay_down(P, b, RADIUS_PIECE.get(pid), K_PIECE.get(pid, K))
        if pid in CLOSE: Q = close(Q, b, CLOSE[pid])
        summary, refused = shrink_limits(g, P, Q, pid in CLOSE)
        if refused: sys.exit(f'{pid}: {summary}; nothing written')
        print(f'{pid}: behind the back {behind_cm(P, b):.1f} → {behind_cm(Q, b):.1f} cm, {summary}')
        g.save(path, Q, before=A)   # turns the normals too: the site lights with them
