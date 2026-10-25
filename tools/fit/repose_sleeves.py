"""Fits shoulder and sleeves of the tops to the neutral body by changing the pose, bone by bone, instead of patching slice by slice.

The garments come from the generator on a mannequin with forward shoulders: the sleeve hangs 3 to 9 cm in front of
the neutral body's arm and the cuff sits off the hand. Here each side becomes a chain of bones, as in a pose change:
  1. the front of the shoulder and the sleeve move back in z (the shoulder blade slides; the back already sits on
     the body and stays);
  2. the upper arm rotates around the shoulder and the forearm around the elbow (in the profile plane);
  3. the forearm opens outward around the elbow until the cuff centers on the hand.
The angles come from a fit: the front/back center of each sleeve slice lands on the center of the body's arm.
Bone weights are smooth; then the cloth settles (ARAP): each neighborhood rotates as rigidly as it can, what is far
from the joint stays pinned to the pose and the FREE band around the joint absorbs the difference without creasing.
Only positions change; UV and texture stay. Refuses (writes nothing) if the cloth stretches too much or a triangle flips.
Input: the GLB published before this step (settling undoes part of the pose, so running it again on its own output
changes the garment); then install.py with the ids, which rebuilds masks and layer tables. Long sleeves only.
usage: python3 tools/fit/repose_sleeves.py in.glb out.glb
"""
import sys, numpy as np, trimesh
import scipy.sparse as sp, scipy.sparse.linalg as spl
from scipy.optimize import minimize, minimize_scalar
from scipy.spatial import cKDTree
from garment import Garment
from metric import body

MAX_CUFF = .02       # the hand comes out through the middle of the cuff (same limit as site/fit.test.ts)
MAX_STRETCH = .20    # p99 of the edges that move
FREE = .06           # loose radius around the bone joint (with no band, the back creases)
FRONT = .08          # the torso shoulder moves back fully with z > 0 and not at all with z < -FRONT (the back)
Y = np.arange(.84, 1.43, .02)   # arm slices, from wrist to shoulder
smooth = lambda t: np.clip(t, 0, 1) ** 2 * (3 - 2 * np.clip(t, 0, 1))


def centers(P, s, X=.21):
    """Front/back center of each slice on side s beyond |x| = X."""
    out = []
    for y in Y:
        k = (s * P[:, 0] > X) & (np.abs(P[:, 1] - y) < .012)
        out.append((P[k, 2].min() + P[k, 2].max()) / 2 if k.sum() > 5 else np.nan)
    return np.array(out)


def rotate(P, pivot, axis, a):
    """Rodrigues: rotates the points P around the axis through pivot."""
    k = np.asarray(axis, float); k /= np.linalg.norm(k); v = P - pivot
    c, s = np.cos(a), np.sin(a)
    return pivot + v * c + np.cross(k, v) * s + np.outer(v @ k, k) * (1 - c)


def weights(P, s, B):
    """Weight of the shoulder (moves back), the upper arm and the forearm on side s. The arm starts 2 cm beyond the
    width of the body's torso at that height (at least |x| = 16 cm), so that the side of a jacket at the waist and hip
    does not rotate with the sleeve."""
    ax, y = s * P[:, 0], P[:, 1]
    side = s * P[:, 0] > 0
    T = B[(np.abs(B[:, 0]) < .17) & (B[:, 1] > .5)]
    ys = np.arange(.5, 1.5, .02); width = np.array([np.abs(T[np.abs(T[:, 1] - v) < .01, 0]).max() for v in ys])
    start = np.maximum(.16, np.interp(y, ys, width) + .02)
    arm = smooth((ax - start) / .05) * side
    shoulder = np.maximum(arm, smooth((ax - .07) / .10) * smooth((y - 1.18) / .14) * smooth((P[:, 2] + FRONT) / FRONT) * side)
    forearm = arm * smooth((1.06 - y) / .08)
    return shoulder, arm, forearm


def pose(P, s, a, joints, w):
    back, arm, forearm, opening = a
    shoulder, elbow = joints
    ws, wa, wf = w
    Q = P + ws[:, None] * np.array([0, 0, -back])
    sh, el = shoulder + [0, 0, -back], elbow + [0, 0, -back]
    Q = Q + wa[:, None] * (rotate(Q, sh, [1, 0, 0], arm) - Q)
    el = rotate(el[None], sh, [1, 0, 0], arm)[0]
    Q = Q + wf[:, None] * (rotate(Q, el, [1, 0, 0], forearm) - Q)
    if opening: Q = Q + wf[:, None] * (rotate(Q, el, [0, 0, 1], s * opening) - Q)
    return Q


def fit_angles(P, B, s, w):
    """Angles of side s: shoulder move and rotations from the front/back center of the sleeve slices onto the arm's;
    then the forearm opening from the center of the cuff (sideways) onto the hand's, in that order: fitted all at once,
    Nelder-Mead lands on a different minimum from each start."""
    ca = centers(B, s, .205); ok = np.isfinite(ca)
    if (np.isfinite(centers(P, s)) & ok).sum() < 20 or not (w[1] > .5).any():
        sys.exit(f'side {s:+d}: fewer than 20 sleeve slices beyond |x| = 21 cm; repose_sleeves.py is for long sleeves only')
    za = lambda y: np.interp(y, Y[ok], ca[ok])
    joints = (np.array([s * .21, 1.40, za(1.40)]), np.array([s * .23, 1.04, za(1.04)]))
    def cost(a):
        c = centers(pose(P, s, [*a, 0], joints, w), s); k = np.isfinite(c) & ok
        return np.mean((c[k] - ca[k]) ** 2)
    r = min((minimize(cost, x0, method='Nelder-Mead', options=dict(xatol=1e-3, fatol=1e-7)) for x0 in
             ([0, 0, 0], [.04, 0, -.3], [.04, .1, -.4], [.02, -.1, -.2])), key=lambda r: r.fun)
    sleeve = w[1] > .5
    Q = pose(P, s, [*r.x, 0], joints, w)
    yb = sleeve_end(Q, B, s)
    cuff = sleeve & (Q[:, 1] > yb) & (Q[:, 1] < yb + .05)
    kb = (s * B[:, 0] > .2) & (B[:, 1] > yb) & (B[:, 1] < yb + .05)
    hand = s * (B[kb, 0].min() + B[kb, 0].max()) / 2
    middle = lambda Q: s * (Q[cuff, 0].min() + Q[cuff, 0].max()) / 2
    rb = minimize_scalar(lambda b: (middle(pose(P, s, [*r.x, b], joints, w)) - hand) ** 2, bounds=(-.3, .3), method='bounded')
    print('side %+d: shoulder back %.1f cm, arm %.1f°, forearm %.1f°, opening %.1f°; sleeve to arm %.1f → %.1f cm (rms), cuff to hand %.1f → %.1f cm' % (
        s, 100 * r.x[0], *np.degrees(r.x[1:]), np.degrees(rb.x), 100 * np.sqrt(cost([0, 0, 0])), 100 * np.sqrt(r.fun),
        100 * abs(middle(Q) - hand), 100 * np.sqrt(rb.fun)))
    return [*r.x, rb.x], joints


def arap(X0, T, E, pinned, rounds=15, K=1e3, k=1e-6):
    """The cloth settles: neighborhoods rotate rigidly (ARAP, uniform Laplacian); `pinned` is held to T with weight K
    and everything else with weight k, which only holds in place a loose piece with no pinned vertex (otherwise the
    system has no solution)."""
    n = len(X0); i, j = E[:, 0], E[:, 1]; d0 = X0[j] - X0[i]
    deg = np.bincount(np.r_[i, j], minlength=n).astype(float)
    Lap = sp.csr_matrix((-np.ones(2 * len(E)), (np.r_[i, j], np.r_[j, i])), shape=(n, n)) + sp.diags(deg)
    anchor = K * pinned + k
    fac = spl.splu((Lap + sp.diags(anchor)).tocsc())
    X = T.copy()
    for _ in range(rounds):
        S = np.zeros((n, 3, 3)); C = np.einsum('ki,kj->kij', d0, X[j] - X[i])
        np.add.at(S, i, C); np.add.at(S, j, C)
        U, _, Vt = np.linalg.svd(S)
        Vt[np.linalg.det(np.einsum('kji,kjl->kil', Vt, U.transpose(0, 2, 1))) < 0, 2] *= -1
        R = np.einsum('kji,kjl->kil', Vt, U.transpose(0, 2, 1))
        rd = .5 * np.einsum('kab,kb->ka', R[i] + R[j], -d0)
        b = np.zeros((n, 3)); np.add.at(b, i, rd); np.add.at(b, j, -rd)
        rhs = b + anchor[:, None] * T
        X = np.column_stack([fac.solve(rhs[:, c]) for c in range(3)])
    return X


def dress(P0, faces, B):
    # vertices at the same position (UV seam) become one: sleeve and cloth move together on both sides of the seam
    _, inv = np.unique(np.round(P0, 5), axis=0, return_inverse=True); inv = inv.ravel()
    X0 = np.zeros((inv.max() + 1, 3)); X0[inv] = P0
    E = trimesh.Trimesh(X0, inv[faces], process=False).edges_unique
    T = X0.copy(); W = np.zeros(len(X0))
    for s in (1, -1):
        w = weights(X0, s, B)
        a, joints = fit_angles(T, B, s, w)
        T = pose(T, s, a, joints, w)
        for p in w: W = np.maximum(W, 4 * p * (1 - p))   # 0 on the bone and the torso, 1 in the middle of the joint
    pinned = cKDTree(X0[W >= .05]).query(X0)[0] > FREE
    return arap(X0, T, E, pinned)[inv]


def sleeve_end(P, B, s):
    """Height of the cuff on side s: going down from the elbow, the first slice where the garment no longer covers the
    outside of the body's arm (or the end of the hand, if the sleeve goes past it). The lowest point of the garment
    beyond some |x| would catch a wide hem near the hand (hoodie 034) instead of the cuff."""
    for y in np.arange(1.10, .6, -.01):
        kb = (s * B[:, 0] > .17) & (np.abs(B[:, 1] - y) < .01); kg = (s * P[:, 0] > .15) & (np.abs(P[:, 1] - y) < .01)
        if not kb.any(): return y + .01
        if not kg.any() or (s * P[kg, 0]).max() < (s * B[kb, 0]).max() - .005: return max(y + .01, B[s * B[:, 0] > .2, 1].min())
    return B[s * B[:, 0] > .2, 1].min()


def cuff_to_hand(P, B, s):
    """Sideways distance (m) from the center of the cuff to the center of the hand, over the 5 cm of cuff where the hand already is."""
    sleeve = s * P[:, 0] > .19
    yb = sleeve_end(P, B, s)
    k = sleeve & (P[:, 1] > yb) & (P[:, 1] < yb + .05); kb = (s * B[:, 0] > .2) & (B[:, 1] > yb) & (B[:, 1] < yb + .05)
    return abs((P[k, 0].min() + P[k, 0].max()) / 2 - (B[kb, 0].min() + B[kb, 0].max()) / 2)


def check(m, P0, P):
    """Stretch of the edges that move (p95, p99) and flipped triangles (height > 3 mm)."""
    D = P - P0; e = m.edges_unique
    e0 = np.linalg.norm(P0[e[:, 0]] - P0[e[:, 1]], axis=1); e1 = np.linalg.norm(P[e[:, 0]] - P[e[:, 1]], axis=1)
    ok = (e0 > 1e-5) & (np.linalg.norm(D[e], axis=2).max(1) > .001)
    st = np.abs(e1[ok] / e0[ok] - 1)
    F = m.faces
    n0 = np.cross(P0[F[:, 1]] - P0[F[:, 0]], P0[F[:, 2]] - P0[F[:, 0]]); n1 = np.cross(P[F[:, 1]] - P[F[:, 0]], P[F[:, 2]] - P[F[:, 0]])
    side = np.max([np.linalg.norm(P0[F[:, k]] - P0[F[:, (k + 1) % 3]], axis=1) for k in range(3)], axis=0)
    big = np.linalg.norm(n0, axis=1) / np.maximum(side, 1e-9) > .003
    return np.percentile(st, 95), np.percentile(st, 99), int((np.einsum('ij,ij->i', n0, n1)[big] < 0).sum())


if __name__ == '__main__':
    src, dst = sys.argv[1:3]
    B = body('B').vertices
    g = Garment(src); P0 = g.vertices(); m = g.mesh(P0)
    P = dress(P0, m.faces, B)
    p95, p99, flipped = check(m, P0, P)
    for s in (1, -1):
        print('after, side %+d (cm per height, from 0.84 to 1.42):' % s, ' '.join('%.1f' % v for v in 100 * (centers(P, s) - centers(B, s, .205))[::3]))
    cuff = max(cuff_to_hand(P, B, s) for s in (1, -1))   # measured after the cloth settles, which undoes part of the opening
    print('%s: stretch p95 %.1f%% p99 %.1f%%; flipped %d; cuff to hand %.1f cm' % (src.split('/')[-1], 100 * p95, 100 * p99, flipped, 100 * cuff))
    if cuff > MAX_CUFF: sys.exit(f'{src}: cuff {100 * cuff:.1f} cm from the hand after the cloth; nothing written')
    if p99 > MAX_STRETCH or flipped:
        sys.exit(f'{src}: cloth stretches too much (p99 {100 * p99:.0f}%, {flipped} flipped triangles); nothing written')
    g.save(dst, P, before=P0)
