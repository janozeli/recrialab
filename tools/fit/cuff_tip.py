"""Pulls up the tips that hang below the rim of a separate sleeve cuff.

Some tops have each cuff as a mesh of its own (a ring of rib knit or of the shirt's trim). On 021 the 3D generator left
the left cuff with a 4 cm tip pointing down on the outer front, painted with the shaded inside of the cuff: on the
site, under the white cuff, a beige V over the arm (eye-315). The photo has a straight cuff.
Per cuff, the lowest point in each BIN of angle around the cuff's centre is the rim. A plane fits the rim (the cuff can
lean with the arm), and each rim point's drop below the plane is compared with that of its neighbours (2 to 4 bins on
each side): a tip is what drops more than its neighbours. The cuff's vertices below the plane, minus the neighbours'
drop, minus TOL, go up to that height; only y changes, so print and UV stay, and the tip's triangles flatten onto the
rim.
usage: python3 tools/fit/cuff_tip.py --check   (CI: fails where a cuff tip drops more than MAX below its neighbours)
       python3 tools/fit/cuff_tip.py 021        (writes; then install.py on the piece)"""
import os, sys, numpy as np
from garment import Garment
from paths import GARMENTS
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'visual-qa'))
from known_issues import known_issues

BIN, TOL, MAX = 10, .01, .03   # degrees, m, m
NEIGHBOURS = (-4, -3, -2, 2, 3, 4)
# tips left as they are, at today's value, while the known issue that owns them names the piece (tools/known-issues.yaml):
# 034 and 037 also go through hood.py, whose --check holds y against the GLB from before it
KNOWN = {
    '034': (.033, 'fit-structure'),
    '037': (.052, 'spiky-hems'),
}
# primitives of each top that are a sleeve cuff
CUFFS = {
    '018': [4, 5],
    '021': [6, 7],
    '027': [5, 6],
    '028': [8, 9],
    '034': [4, 5],
    '037': [9],
}


def cuff_vertices(g, part):
    off = sum(g.sizes[:part]); return np.arange(off, off + g.sizes[part])


def rim(P):
    """Bin of each vertex and, per bin, the index of its lowest vertex (-1: empty bin)."""
    c = P.mean(0); a = np.degrees(np.arctan2(P[:, 2] - c[2], P[:, 0] - c[0])) % 360; b = (a // BIN).astype(int)
    low = np.full(360 // BIN, -1)
    for k in range(len(low)):
        q = np.nonzero(b == k)[0]
        if len(q): low[k] = q[np.argmin(P[q, 1])]
    return b, low


def plane(L):
    """y = a x + b z + c over the rim points, refit three times without the 20% that drop most (the tips)."""
    keep = np.ones(len(L), bool); A = np.c_[L[:, 0], L[:, 2], np.ones(len(L))]
    for _ in range(3):
        co = np.linalg.lstsq(A[keep], L[keep, 1], rcond=None)[0]
        drop = A @ co - L[:, 1]; keep = drop < np.percentile(drop, 80)
    return co


def tips(P):
    """Per bin with a rim point: its drop below the plane minus the median drop of its neighbours (m); and the plane."""
    b, low = rim(P); ks = np.nonzero(low >= 0)[0]; L = P[low[ks]]; co = plane(L)
    drop = np.full(len(low), np.nan); drop[ks] = np.c_[L[:, 0], L[:, 2], np.ones(len(L))] @ co - L[:, 1]
    n = len(low); local = np.full(n, np.nan); around = np.full(n, np.nan)
    for k in ks:
        nb = [drop[(k + j) % n] for j in NEIGHBOURS]
        if np.isfinite(nb).any(): around[k] = np.nanmedian(nb); local[k] = drop[k] - around[k]
    return b, local, around, co


def pull(P):
    b, local, around, co = tips(P); Q = P.copy()
    floor = np.c_[P[:, 0], P[:, 2], np.ones(len(P))] @ co - np.nan_to_num(around[b], nan=np.inf) - TOL
    up = (P[:, 1] < floor) & (np.nan_to_num(local[b]) > TOL)
    Q[up, 1] = floor[up]
    return Q, int(up.sum())


def worst(pid):
    g = Garment(GARMENTS + f'{pid}.glb'); V = g.vertices(); out = []
    for part in CUFFS[pid]:
        _, local, _, _ = tips(V[cuff_vertices(g, part)]); out.append((np.nanmax(local), part))
    return max(out)


if __name__ == '__main__':
    if sys.argv[1:] == ['--check']:
        bad = []; issues = known_issues()
        for pid in CUFFS:
            d, part = worst(pid); print(f'{pid} cuff {part}: tip {100 * d:.1f} cm below its neighbours')
            cap, issue = KNOWN.get(pid, (MAX, None))
            if issue and pid not in issues.get(issue, ()): cap = MAX
            if d > cap: bad.append(f'{pid} (cuff {part}, {100 * d:.1f} cm)')
        if bad: sys.exit(f'cuff tip more than {100 * MAX:.0f} cm below the rim (run cuff_tip.py on them): ' + ', '.join(bad))
        sys.exit()
    for pid in sys.argv[1:]:
        path = GARMENTS + f'{pid}.glb'; g = Garment(path); A = g.vertices(); Q = A.copy(); moved = 0
        for part in CUFFS[pid]:
            vi = cuff_vertices(g, part); Q[vi], k = pull(A[vi]); moved += k
        g.save(path, Q, before=A)
        print(f'{pid}: {moved} vertices up, worst tip now {100 * worst(pid)[0]:.1f} cm')
