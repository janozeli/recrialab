"""Moves the whole bottom garment out of the neutral body in one step, with a smooth displacement field in space.

The pants come from a mannequin with narrower thighs and hips: the neutral body pokes through the side of the leg and
the hip from top to bottom, and a patch per region (top_cloth.py --bottom on the waistband) pulls the waistband lining
out through the cloth. Here the displacement is a
field in space, not on the mesh: on every round whatever is closer than SLACK to the body moves out along the body
normal, and the whole field is smoothed by a gaussian kernel of RADIUS around each vertex. Lining and outer cloth,
close in space but far apart on the mesh, move together. Below the crotch, body points on the other side (the other
leg) do not count.
Refuses edge stretch p99 above MAX_STRETCH or a flipped triangle: then the garment is smaller than the body
and the field cannot fix it. Only positions and normals change; UV and texture stay. SLACK is small because pants
pushed farther out poke through the hem of the tops (layer_check.py).
usage: python3 tools/fit/displacement_field.py IN.glb OUT.glb [RADIUS_M]   (002 and 007: 0.05; 004: 0.07)"""
import os, sys, numpy as np, trimesh
from scipy.spatial import cKDTree
from garment import Garment, kernel
from metric import body, POSE_C

SLACK = .002        # minimum distance from the body
ROUNDS = 60
CROTCH = .78        # below this the other side of the body is the other leg
MAX_STRETCH = .10   # edge p99
FAR = .04           # cloth farther than this from the body does not move (at 2 cm it moves fully): the gap does not grow

src, dst = sys.argv[1:3]
RADIUS = float(sys.argv[3]) if len(sys.argv) > 3 else .05
pid = os.path.basename(src)[5:8]
b = body('C' if pid in POSE_C else 'B')
S, fi = trimesh.sample.sample_surface_even(b, 300000, seed=1); SN = b.face_normals[fi]; ST = cKDTree(S)
g = Garment(src); P0 = g.vertices(); m = g.mesh(P0)
# weld the vertices duplicated along UV seams: the cloth is one piece
_, inv = np.unique(np.round(P0, 5), axis=0, return_inverse=True); inv = inv.ravel()
X0 = np.zeros((inv.max() + 1, 3)); X0[inv] = P0; F = inv[m.faces]
E = trimesh.Trimesh(X0, F, process=False).edges_unique
L = np.linalg.norm(X0[E[:, 0]] - X0[E[:, 1]], axis=1)

K = kernel(X0, RADIUS)


def body_side(X):
    d, j = ST.query(X); sd = np.einsum('ij,ij->i', X - S[j], SN[j])
    ok = (d < .06) & ~((X[:, 1] < CROTCH) & (np.sign(X[:, 0]) != np.sign(S[j, 0])) & (np.abs(X[:, 0]) > .01))
    return sd, j, ok


sd0, _, ok0 = body_side(X0)
# what was already far from the body stays put: the field only smooths near it, and the gap does not grow
stay = np.clip((FAR - sd0) / .02, 0, 1)[:, None]
D = np.zeros_like(X0)
for _ in range(ROUNDS):
    sd, j, ok = body_side(X0 + D)
    near = ok & (sd < SLACK)
    D[near] += (SLACK - sd[near])[:, None] * SN[j[near]]
    D = stay * (K @ D)
X = X0 + D
sd, _, ok = body_side(X)
e = np.abs(np.linalg.norm(X[E[:, 0]] - X[E[:, 1]], axis=1) / np.maximum(L, 1e-9) - 1)
n0 = np.cross(X0[F[:, 1]] - X0[F[:, 0]], X0[F[:, 2]] - X0[F[:, 0]]); n1 = np.cross(X[F[:, 1]] - X[F[:, 0]], X[F[:, 2]] - X[F[:, 0]])
flipped = int(((np.einsum('ij,ij->i', n0, n1) < 0) & (np.linalg.norm(n0, axis=1) > 1e-7)).sum())
ps = np.percentile(e, 99)
print('%s inside the body %d → %d vertices; stretch p95 %.1f%% p99 %.1f%%; flipped %d; displacement median %.1f, max %.1f cm' % (
    pid, int((ok0 & (sd0 < 0)).sum()), int((ok & (sd < 0)).sum()), 100 * np.percentile(e, 95), 100 * ps, flipped,
    100 * np.median(np.linalg.norm(D, axis=1)), 100 * np.linalg.norm(D, axis=1).max()), flush=True)
if ps > MAX_STRETCH or flipped:
    sys.exit(f'{src}: print distorts too much (stretch p99 {100 * ps:.0f}%, {flipped} flipped); nothing written')
g.save(dst, X[inv], before=P0)
