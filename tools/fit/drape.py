"""Gravity drape for the tops.

A real blouse rests on the shoulder and falls straight from the widest point above (chest, shoulder blade): it does
not cling to the waist. So the target of each point of the blouse torso is the body's "curtain", E(θ, y) = largest
torso radius at θ between y and the shoulder, plus CLEAR. The excess over the curtain shrinks by a fraction F,
horizontally only. At the shoulder, the garment drops until it rests. Arms stay outside the curtain: the side of the
blouse comes in and the arm passes outside instead of through the cloth. The field is smoothed in space (radius R).
usage: python3 tools/fit/drape.py in.glb out.glb [F] [CLEAR] [R] [DROP_m]
Without DROP, the shoulder is pulled by the field too, which stretches the print.
The input is always the ORIGINAL garment (tools/fit/reference/originals/before-drape/NNN.glb):
running on the already fitted garment drops it again.
"""
import sys, numpy as np, trimesh
from scipy.spatial import cKDTree
from garment import Garment
from metric import body

src, dst = sys.argv[1:3]
F = float(sys.argv[3]) if len(sys.argv) > 3 else .6
CLEAR = float(sys.argv[4]) if len(sys.argv) > 4 else .02
R = float(sys.argv[5]) if len(sys.argv) > 5 else .07
SHOULDER_Y = 1.32          # above this the shoulder rest applies
CAP = .08
NT, DY = 72, .02

b = body('B')
V = b.vertices
torso = (V[:, 1] > .8) & ((np.abs(V[:, 0]) < .165) | (V[:, 1] > 1.47))
T = V[torso]
zc = np.median(T[(T[:, 1] > 1.0) & (T[:, 1] < 1.4), 2])
def polar(p):
    return np.arctan2(p[:, 0], p[:, 2] - zc), np.hypot(p[:, 0], p[:, 2] - zc)
th, r = polar(T)
ti = ((th + np.pi) / (2 * np.pi) * NT).astype(int) % NT
yi = np.clip(((T[:, 1] - .8) / DY).astype(int), 0, 60)
rmax = np.zeros((NT, 61)); np.maximum.at(rmax, (ti, yi), r)
# fills sampling holes along θ
for k in range(61):
    col = rmax[:, k]
    if (col > 0).any():
        idx = np.nonzero(col)[0]
        rmax[:, k] = np.interp(np.arange(NT), idx, col[idx], period=NT)
top_k = int((SHOULDER_Y + .1 - .8) / DY)
curtain = np.maximum.accumulate(rmax[:, :top_k + 1][:, ::-1], axis=1)[:, ::-1]
curtain = np.c_[curtain, np.repeat(curtain[:, -1:], 61 - curtain.shape[1], 1)]

key = np.round(V * 1e4).astype(np.int64)
u, inv = np.unique(key, axis=0, return_inverse=True)
bw = trimesh.Trimesh(u / 1e4, inv.ravel()[b.faces], process=False)
pq = trimesh.proximity.ProximityQuery(bw)

g = Garment(src)
P0 = g.vertices(); P = P0.copy()
DROP = float(sys.argv[6]) if len(sys.argv) > 6 else float('nan')
RIGID = DROP == DROP
if RIGID: P[:, 1] -= DROP
for it in range(3):
    raw = np.zeros_like(P)
    th, rr = polar(P)
    ti = ((th + np.pi) / (2 * np.pi) * NT).astype(int) % NT
    yi = np.clip(((P[:, 1] - .8) / DY).astype(int), 0, 60)
    E = curtain[ti, yi]; Rb = rmax[ti, yi]
    sleeve = (np.abs(P[:, 0]) > .2) & (P[:, 1] < 1.48)
    body_zone = (P[:, 1] < SHOULDER_Y) & ~sleeve
    radial = np.c_[np.sin(th), np.zeros(len(P)), np.cos(th)]
    exc = rr - (E + CLEAR)
    m = body_zone & (exc > 0)
    raw[m] = -radial[m] * (F * exc[m])[:, None]
    pen = body_zone & (rr < Rb + .006)
    raw[pen] = radial[pen] * (Rb[pen] + .008 - rr[pen])[:, None]
    # shoulder: vertical/normal rest on the body
    sh = (P[:, 1] >= SHOULDER_Y) & ~sleeve
    c, dist, tri = pq.on_surface(P[sh])
    n = bw.face_normals[tri]; v = P[sh] - c
    s = np.where(np.einsum('ij,ij->i', v, n) >= 0, dist, -dist)
    dirn = v / np.maximum(dist, 1e-9)[:, None]
    dirn[s < 0] = -dirn[s < 0]
    rs = np.zeros((sh.sum(), 3))
    far = s > CLEAR * .6
    rs[far] = -dirn[far] * (F * (s[far] - CLEAR * .6))[:, None]
    ins = s < .004
    rs[ins] = dirn[ins] * (.008 - s[ins])[:, None]
    raw[sh] = 0 if RIGID else rs
    # the sleeve follows the shoulder drop (rigidly), without being pulled onto the arm
    if far.any() and not RIGID: raw[sleeve, 1] = np.median(rs[far, 1])
    nb = cKDTree(P).query_ball_point(P, R)
    d = raw
    for _ in range(2):
        d = np.array([d[i].mean(0) for i in nb])
    l = np.linalg.norm(d, axis=1, keepdims=True); d *= np.minimum(1, CAP / np.maximum(l, 1e-9))
    P = P + d
    if RIGID: break
m0 = g.mesh(P0); m1 = g.mesh(P)
e = m0.edges_unique
e0 = np.linalg.norm(m0.vertices[e[:, 0]] - m0.vertices[e[:, 1]], axis=1)
e1 = np.linalg.norm(m1.vertices[e[:, 0]] - m1.vertices[e[:, 1]], axis=1)
ok = e0 > 1e-5; strain = np.abs(e1[ok] / e0[ok] - 1)
print('mean displacement %.1f cm, max %.1f cm; stretch median %.1f%% p95 %.1f%%' % (
    100 * np.linalg.norm(P - P0, axis=1).mean(), 100 * np.linalg.norm(P - P0, axis=1).max(), 100 * np.median(strain), 100 * np.percentile(strain, 95)))
g.save(dst, P)
