"""Lets the top settle on the body under its own weight, like cloth.

The garments come from a mannequin with a straight neck, so the back collar sits 5 to 9 cm behind the nape. Moving
positions alone does not close that gap (the collar opening is deeper than the neck: pulling the collar shrinks the
back or folds the cloth). Here the garment becomes cloth: edges at their original length, bending between
neighboring faces and collision with the body; gravity pulls and the garment slides until it rests on the shoulders
and the chest, like a hanging t-shirt. The back collar meets the nape and the front drops a little. Then gravity
goes away and the cloth relaxes back to its original length. No vertex goes deeper into the body than it already
was. Only positions and normals change; UV and texture stay.
With --bottom (bottom garments): no gravity, and what was inside the body moves out (the glutes poked through the
seat of shorts); the cloth around follows through the edges.
usage: python3 tools/fit/top_cloth.py [--bottom] in.glb out.glb
"""
import sys, re, os, numpy as np, trimesh
from scipy.spatial import cKDTree
from garment import Garment
from metric import body, POSE_C

BOTTOM = '--bottom' in sys.argv
src, dst = [a for a in sys.argv[1:] if a != '--bottom']
# jackets too: lining and shoulder pad are garment geometry; the gap to the shoulder comes from the straight mannequin
# (035 is refused by the stretch limit)
G = 0 if BOTTOM else .0001          # drop per step (m); with 20 constraint rounds per step the cloth stretches < 2% (p95)
STEPS, RELAX, ROUNDS = 400, 100, 20
SLACK = .007         # minimum distance from the body (with less, the shoulder check measures the garment below the shoulder peak)
HIP = .72            # --bottom: from the hip up
BEND = .3            # bending stiffness between neighboring faces
MAX_STRETCH = .10    # edge p99
MAX_AREA = .25       # p99 of the face area change (no slivers)
MAX_FOLD = .003      # inside-out faces: up to 0.3% of the garment area

b = body('C' if BOTTOM and os.path.basename(src)[5:8] in POSE_C else 'B')
S, fi = trimesh.sample.sample_surface_even(b, 300000, seed=1); SN = b.face_normals[fi]; ST = cKDTree(S)
g = Garment(src); P0 = g.vertices(); m = g.mesh(P0)
# weld the vertices duplicated along UV seams: the cloth is one piece
_, inv = np.unique(np.round(P0, 5), axis=0, return_inverse=True); inv = inv.ravel()
X0 = np.zeros((inv.max() + 1, 3)); X0[inv] = P0
F = inv[m.faces]
mw = trimesh.Trimesh(X0, F, process=False)
E = mw.edges_unique; L = np.linalg.norm(X0[E[:, 0]] - X0[E[:, 1]], axis=1)
fa, ea = mw.face_adjacency, mw.face_adjacency_edges
def opposite(f, e):
    r = np.setdiff1d(F[f], e); return r[0] if len(r) else -1
D = np.array([[opposite(a, e), opposite(c, e)] for (a, c), e in zip(fa, ea)])
D = D[(D >= 0).all(1)]; LD = np.linalg.norm(X0[D[:, 0]] - X0[D[:, 1]], axis=1)

def constrain(X, idx, rest, k):
    d = X[idx[:, 1]] - X[idx[:, 0]]; l = np.linalg.norm(d, axis=1, keepdims=True) + 1e-12
    c = (l - rest[:, None]) / l * d * .5 * k
    acc = np.zeros_like(X); n = np.zeros(len(X))
    np.add.at(acc, idx[:, 0], c); np.add.at(acc, idx[:, 1], -c)
    np.add.at(n, idx[:, 0], 1); np.add.at(n, idx[:, 1], 1)
    return acc / np.maximum(n, 1)[:, None]

def body_side(X):
    d, j = ST.query(X); return d, j, np.einsum('ij,ij->i', X - S[j], SN[j])

_, _, sd0 = body_side(X0); floor = np.minimum(sd0, SLACK)   # what was already inside does not sink further
if BOTTOM: floor[X0[:, 1] > HIP] = SLACK   # between the thighs the nearest body is the other leg: not there
X = X0.copy()
for step in range(STEPS + RELAX):
    if step < STEPS: X[:, 1] -= G
    for _ in range(ROUNDS):
        X += constrain(X, E, L, 1.6)
        X += constrain(X, D, LD, BEND)
    d, j, sd = body_side(X)
    inside = (sd < floor) & (d < .05)
    X[inside] += (floor - sd)[inside][:, None] * SN[j[inside]]

n0 = np.cross(X0[F[:, 1]] - X0[F[:, 0]], X0[F[:, 2]] - X0[F[:, 0]])
side = np.max([np.linalg.norm(X0[F[:, i]] - X0[F[:, (i + 1) % 3]], axis=1) for i in range(3)], axis=0)
big = np.linalg.norm(n0, axis=1) / np.maximum(side, 1e-9) > .003   # height > 3 mm; a thinner sliver flips without showing
e = np.abs(np.linalg.norm(X[E[:, 0]] - X[E[:, 1]], axis=1) / np.maximum(L, 1e-9) - 1)
n1 = np.cross(X[F[:, 1]] - X[F[:, 0]], X[F[:, 2]] - X[F[:, 0]])
area = np.abs(np.linalg.norm(n1[big], axis=1) / np.linalg.norm(n0[big], axis=1) - 1)
flip = big & (np.einsum('ij,ij->i', n0, n1) < 0); flipped = int(flip.sum())
# a small fold becomes an inside-out face (the garment is drawn on both sides); a large fold would be a folded print
pv = np.linalg.norm(n0[flip], axis=1).sum() / np.linalg.norm(n0, axis=1).sum()
ps, pa = np.percentile(e, 99), np.percentile(area, 99)
print('%s stretch p95 %.1f%% p99 %.1f%%; area p99 %.1f%%; flipped %d (%.2f%% of the area); dropped %.1f cm (median), max %.1f cm' % (
    os.path.basename(src), 100 * np.percentile(e, 95), 100 * ps, 100 * pa, flipped, 100 * pv,
    100 * np.median(X0[:, 1] - X[:, 1]), 100 * np.linalg.norm(X - X0, axis=1).max()), flush=True)
if ps > MAX_STRETCH or pa > MAX_AREA or pv > MAX_FOLD:
    sys.exit(f'{src}: print distorts too much (stretch {100 * ps:.0f}%, area {100 * pa:.0f}%, {flipped} flipped); nothing written')
g.save(dst, X[inv], before=P0)
