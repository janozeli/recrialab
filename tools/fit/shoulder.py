"""Settles the shoulder of the tops on the body's shoulder.

After the rigid drop (drape.py) the collar already touches, but the garment's shoulder tip stays square, 4 to 8 cm
above the deltoid: the garments come from a mannequin with straight shoulders and the neutral body has sloped ones.
Here only the shoulder band comes down: for each distance from the center |x|, the gap measured from the body to the
garment (rays going up) minus TARGET becomes the drop s(|x|). It applies fully at the top and fades out HEIGHT below
the shoulder, so chest, front print and hem stay where they were. The sleeve follows the shoulder tip and fades
along the arm. Only positions change; UV and texture stay.
usage: python3 tools/fit/shoulder.py in.glb out.glb [TARGET_m] [HEIGHT_m]
"""
import sys, numpy as np
from scipy.spatial import cKDTree
from garment import Garment
from metric import body
from anchors import first_hit

src, dst = sys.argv[1:3]
import re, os
JACKETS = {
    '033',
    '035',
    '036',
    '038',
}
HOODIES = {
    '034',
    '037',
}
if (re.findall(r'\d{3}', os.path.basename(src)) or ['0'])[-1] in JACKETS:
    sys.exit(f'{src}: a jacket has a real structured shoulder; shoulder.py is for knits (016–032) and hoodies (034, 037)')
HOOD = (re.findall(r'\d{3}', os.path.basename(src)) or ['0'])[-1] in HOODIES
TARGET = float(sys.argv[3]) if len(sys.argv) > 3 else .015
HEIGHT = float(sys.argv[4]) if len(sys.argv) > 4 else .20
WIDEN = 4.           # the band grows 4 cm per cm beyond |x| = 18 cm: the sleeve comes down too, with no step at the armhole
MAX_DROP = .045      # more than this compresses the shoulder band and bends horizontal stripes
MAX_STRETCH = .35    # refuses the output with an edge 35% longer or shorter (p99) or a flipped triangle
SHOULDER_TOP = 1.50  # top of the deltoid on body B
X = np.arange(.03, .27, .01)
COLLAR = .06         # near the neck the ray finds the collar and the hood, not the shoulder: not measured

b = body('B'); V, N = b.vertices, b.vertex_normals
g = Garment(src); P0 = g.vertices(); m = g.mesh(P0)
sh = (N[:, 1] > .6) & (V[:, 1] > 1.44) & (np.abs(V[:, 0]) > .03) & (np.abs(V[:, 0]) < .25)
up = first_hit(m, V[sh] + [0, 1e-4, 0], np.tile([0, 1., 0], (sh.sum(), 1)), .25)
ax = np.abs(V[sh, 0])
gap = np.array([np.median(up[(ax >= x - .01) & (ax < x + .01) & np.isfinite(up)]) if
                ((ax >= x - .01) & (ax < x + .01) & np.isfinite(up)).sum() > 3 else np.nan for x in X])
s = np.clip(gap - TARGET, 0, None); s[X < COLLAR] = np.nan
# outside the body (beyond the deltoid) the last measure holds; inside, without a measure, nothing drops
last = np.where(np.isfinite(s))[0]
if not len(last): sys.exit(f'{src}: no shoulder ray hits the garment')
s[last[-1]:] = s[last[-1]]; s = np.nan_to_num(s)
s = np.convolve(np.r_[s[:2][::-1], s, s[-2:][::-1]], np.ones(5) / 5, 'valid')   # smooths over 5 cm
s = np.minimum(s, MAX_DROP)   # local gap: carrying the peak outward would sink the shoulder tip into the body

P = P0.copy()
px = np.abs(P[:, 0]); drop = np.interp(px, X, s)
# a single weight, continuous in x and y: the band that drops sits higher further out, so the sleeve follows the
# shoulder and the armhole does not tear in a step (a cut at a fixed |x| would stretch the armhole)
band = HEIGHT + WIDEN * np.clip(px - .18, 0, None)
t = np.clip((P[:, 1] - (SHOULDER_TOP - band)) / band, 0, 1); w = t * t * (3 - 2 * t)
# average over a 4 cm radius: removes the step between neighboring vertices that would become an inside-out triangle
if HOOD:   # hoodie: hood and cords stay put; below 1.38 m and beyond |x| = 19 cm the drop applies fully
    tx = np.clip((px - .13) / .06, 0, 1); w = w * (1 - (P0[:, 1] > 1.38) * (1 - tx * tx * (3 - 2 * tx)))
d = drop * w
for _ in range(2):
    d = np.array([d[i].mean() for i in cKDTree(P0).query_ball_point(P0, .04)])
P[:, 1] -= d

m1 = g.mesh(P); e = m.edges_unique
e0 = np.linalg.norm(P0[e[:, 0]] - P0[e[:, 1]], axis=1); e1 = np.linalg.norm(P[e[:, 0]] - P[e[:, 1]], axis=1)
ok = e0 > 1e-5; strain = np.abs(e1[ok] / e0[ok] - 1)
F = m.faces
n0 = np.cross(P0[F[:, 1]] - P0[F[:, 0]], P0[F[:, 2]] - P0[F[:, 0]]); n1 = np.cross(P[F[:, 1]] - P[F[:, 0]], P[F[:, 2]] - P[F[:, 0]])
side = np.max([np.linalg.norm(P0[F[:, i]] - P0[F[:, (i + 1) % 3]], axis=1) for i in range(3)], axis=0)
big = np.linalg.norm(n0, axis=1) / np.maximum(side, 1e-9) > .003   # height > 3 mm; a thinner sliver flips on screen without showing
flipped = int((np.einsum('ij,ij->i', n0, n1)[big] < 0).sum())
p99 = np.percentile(strain, 99)
print('%s gap per |x| (cm): %s; max drop %.1f cm; stretch p95 %.1f%% p99 %.1f%%; flipped %d' % (
    src.split('/')[-1], ' '.join('%.0f' % (100 * v) if v == v else '-' for v in gap[::2]),
    100 * s.max(), 100 * np.percentile(strain, 95), 100 * p99, flipped))
if p99 > MAX_STRETCH or flipped: sys.exit(f'{src}: print distorts too much (p99 {100 * p99:.0f}%, {flipped} flipped triangles); nothing written')
g.save(dst, P, before=P0)   # rotates the normals too: the site lights with them
