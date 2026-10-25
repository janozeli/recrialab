"""Brings the jacket to the size of the body: uniform scale of the whole garment.

The generator returns each garment at its own size, and some jackets come too large for the neutral body: the sleeve
swallows the hand, the rib hem of a short jacket falls to the crotch and the torso sits 5 to 7 cm in front of the
chest. A uniform scale does not distort the print: everything shrinks evenly.
The pivot is at the middle of the torso, at the height where the top of the scaled garment's shoulder stays over the
body's shoulder (with the pivot at the shoulder, the shoulder tip would go into the deltoid); the sleeve shrinks
too and repose_sleeves.py puts it back on the arm. Scale SCALE, or the one that brings the sleeve end to CUFF (the
hand comes out through the cuff).
usage: python3 tools/fit/resize.py IN.glb OUT.glb [SCALE]"""
import sys, numpy as np
from garment import Garment
from metric import body
from repose_sleeves import sleeve_end

SLACK = .005        # top of the garment's shoulder above the body's
CUFF = .82          # sleeve end: covers the wrist (0.87) and the start of the hand, as on 033 and 035


def sleeve_end_any(P, B):
    """Height of the cuff (the lower of both sides), as repose_sleeves.sleeve_end and the check in site/fit.test.ts;
    when the sleeve goes past the hand, the lowest point of the garment in the hand column (6 cm around its center,
    seen from above)."""
    end = min(sleeve_end(P, B, s) for s in (1, -1))
    if end > B[np.abs(B[:, 0]) > .2, 1].min() + .005: return end
    out = []
    for s in (1, -1):
        c = B[(s * B[:, 0] > .17) & (B[:, 1] > .69) & (B[:, 1] < .87)][:, [0, 2]].mean(0)
        k = (P[:, 1] < .95) & (np.linalg.norm(P[:, [0, 2]] - c, axis=1) < .06)
        out.append(P[k, 1].min() if k.any() else np.inf)
    return min(out)


def top(P, xs):
    """Top of each |x| band near the body plane (like the shoulder check in site/fit.test.ts)."""
    return np.array([P[(np.abs(np.abs(P[:, 0]) - x) < .01) & (np.abs(P[:, 2]) < .06), 1].max() for x in xs])


if __name__ == '__main__':
    src, dst = sys.argv[1:3]
    B = body('B').vertices
    g = Garment(src); P = g.vertices()
    T = B[(np.abs(B[:, 0]) < .15) & (np.abs(B[:, 1] - 1.4) < .02)]; zc = (T[:, 2].min() + T[:, 2].max()) / 2
    end = sleeve_end_any(P, B)
    xs = np.arange(.12, .215, .01)   # from the collar base to the shoulder tip; beyond is the sleeve head, which repose_sleeves.py sets
    # pivot: lowest height at which, after scaling, the top of the garment's shoulder sits SLACK above the body's
    def pivot(s):
        if s >= 1: return 0
        gy = top(P, xs / s)   # the band that ends up at xs
        return float(np.max((top(B, xs) + SLACK - s * gy) / (1 - s)))
    if len(sys.argv) > 3: s = float(sys.argv[3])
    else:
        # the sleeve end rises by (pivot - end)(1 - s), and the pivot depends on the scale: the fixed point comes in a few rounds
        s = 1
        for _ in range(10):
            yp = max(pivot(s), 1.45); s = min(1, (yp - CUFF) / (yp - end))
    if s >= 1: sys.exit(f'{src}: cuff already at the wrist ({end:.2f} m); nothing written')
    yp = pivot(s); piv = np.array([0, yp, zc])
    Q = piv + (P - piv) * s
    print(f'{src}: scale {s:.3f}, pivot {np.round(piv, 3).tolist()}; sleeve end {end:.3f} → {sleeve_end_any(Q, B):.3f}')
    g.save(dst, Q)
