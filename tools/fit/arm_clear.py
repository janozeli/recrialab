"""Opens the inner side of a sleeve and the side of the torso around the body's arm, where the generator left them
through it.

On jacket 033 the left sleeve's inner wall runs through the arm between the elbow and the hip (1.4 cm inside it), and
the side of the torso lies against the arm. The mask hides the arm there, so from the front a slit of background shows
between the sleeve and the side (visual QA arm_gap). Here, in a band of heights, the parts that face the torso move
off the arm along its normal: the sleeve's inner wall to SLACK_SLEEVE from it, the side of the torso to SLACK_TORSO
(beyond the sleeve, so the two walls keep their order). The field is smoothed in space within each part (the sleeve
and the torso are not mixed) and fades out above and below the band. Only positions change; UV and texture stay.
Refuses (writes nothing) above MAX_STRETCH (p95 of the edges that move) or with a flipped triangle.
The same displacement goes to the piece's copy in reference/originals/before-hood/ when given: hood.py --check holds the
published piece to it in x and y. Then install.py with the id (masks and layer tables) and site/thumbnails.ts.
usage: python3 tools/fit/arm_clear.py in.glb out.glb [before-hood.glb]   (033: the GLB published before, left side
only; the right sleeve is one piece with the torso there and has no slit)"""
import sys, numpy as np, trimesh
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from garment import Garment, kernel
from metric import body
import sleeve

Y0, Y1, FADE = .98, 1.16, .04            # band of heights that moves, and its fade
SLACK_SLEEVE, SLACK_TORSO = .006, .014   # distance from the arm each part ends at, at least
RADIUS, ROUNDS = .02, 60
MAX_STRETCH = .08                        # p95 of the edges that move


def main(src, dst, original=None):
    b = body('B')
    S, fi = trimesh.sample.sample_surface_even(b, 300000, seed=1); SN = b.face_normals[fi]
    arm = (S[:, 0] < -sleeve.ARM_X) & (np.linalg.norm(sleeve.plane(S), axis=1) < .07) & (S[:, 1] > .85) & (S[:, 1] < 1.4)
    S, SN = S[arm], SN[arm]; ST = cKDTree(S)
    g = Garment(src); P0 = g.vertices(); m = g.mesh(P0)
    _, inv = np.unique(np.round(P0, 5), axis=0, return_inverse=True); inv = inv.ravel()
    X0 = np.zeros((inv.max() + 1, 3)); X0[inv] = P0; F = inv[m.faces]
    E = trimesh.Trimesh(X0, F, process=False).edges_unique
    L = np.linalg.norm(X0[E[:, 0]] - X0[E[:, 1]], axis=1)
    # the parts in the band: faces wholly in it, connected; a part close to the arm axis is the sleeve
    inb = (X0[:, 1] > Y0 - FADE) & (X0[:, 1] < Y1 + FADE)
    fb = inb[F].all(1)
    ed = np.vstack([F[fb][:, [0, 1]], F[fb][:, [1, 2]], F[fb][:, [2, 0]]])
    _, lab = connected_components(coo_matrix((np.ones(len(ed)), (ed[:, 0], ed[:, 1])), shape=(len(X0),) * 2), directed=False)
    kind = np.full(len(X0), '', object)
    for k in np.unique(lab[inb]):
        v = (lab == k) & inb
        if v.sum() >= 20: kind[v] = 'sleeve' if np.median(np.linalg.norm(sleeve.plane(X0[v]), axis=1)) < .08 else 'torso'
    # only the left side, and on it what faces the torso
    w = np.clip(np.minimum(X0[:, 1] - (Y0 - FADE), (Y1 + FADE) - X0[:, 1]) / FADE, 0, 1) * (kind != '') * (X0[:, 0] < 0)
    w *= np.clip((.01 - sleeve.plane(X0)[:, 0]) / .02, 0, 1)
    slack = np.where(kind == 'sleeve', SLACK_SLEEVE, SLACK_TORSO)
    K = [(idx, kernel(X0[idx], RADIUS)) for idx in (np.nonzero(kind == t)[0] for t in ('sleeve', 'torso'))]

    def side(X):
        d, j = ST.query(X); return np.einsum('ij,ij->i', X - S[j], SN[j]), j, d < .05

    sd0, _, _ = side(X0)
    D = np.zeros_like(X0)
    for _ in range(ROUNDS):
        sd, j, ok = side(X0 + D)
        near = ok & (sd < slack) & (w > 0)
        D[near] += (slack[near] - sd[near])[:, None] * SN[j[near]]
        for idx, Kt in K: D[idx] = Kt @ D[idx]
        D *= w[:, None]
    X = X0 + D
    sd, _, _ = side(X)
    e = np.abs(np.linalg.norm(X[E[:, 0]] - X[E[:, 1]], axis=1) / np.maximum(L, 1e-9) - 1)
    moved = np.linalg.norm(D[E], axis=2).max(1) > 1e-4
    n0 = np.cross(X0[F[:, 1]] - X0[F[:, 0]], X0[F[:, 2]] - X0[F[:, 0]]); n1 = np.cross(X[F[:, 1]] - X[F[:, 0]], X[F[:, 2]] - X[F[:, 0]])
    flipped = int(((np.einsum('ij,ij->i', n0, n1) < 0) & (np.linalg.norm(n0, axis=1) > 1e-7)).sum())
    band = (X0[:, 1] > Y0) & (X0[:, 1] < Y1) & (w > 0)
    p95 = np.percentile(e[moved], 95) if moved.any() else 0
    print('inside the arm in the band %d → %d vertices; moved edges %d, stretch p95 %.1f%%; flipped %d; moved up to %.1f cm' % (
        (band & (sd0 < 0)).sum(), (band & (sd < 0)).sum(), moved.sum(), 100 * p95, flipped, 100 * np.linalg.norm(D, axis=1).max()))
    if p95 > MAX_STRETCH or flipped:
        sys.exit(f'{src}: the cloth stretches too much (p95 {100 * p95:.1f}%, {flipped} flipped); nothing written')
    g.save(dst, X[inv], before=P0)
    if original:
        o = Garment(original); O = o.vertices()
        if O.shape != P0.shape or np.abs(O - P0)[np.linalg.norm(D[inv], axis=1) > 0].max() > 1e-5:
            sys.exit(f'{original}: not the same piece where it moves; written only {dst}')
        o.save(original, O + D[inv], before=O)


if __name__ == '__main__':
    main(*sys.argv[1:4])
