"""From the shin down, all the fabric of the trousers is the trouser leg around the body's leg: nothing hangs outside it.

Fabric left in the gap between the legs (a strip cut by separate_legs.py) shows from the front reaching down to the
sneaker, and the measures of the body inside the fabric (poke-through, penetration) do not see it. Here, in slices of DY below TOP, the section of the piece is
cut into loops: the closed loop that contains the center of the body's leg is the trouser leg (loose or tight, it
does not matter); everything else outside it counts (length × DY). Measuring the distance to the body does not work:
loose trousers (013 gathered above the cuff) have fabric far from the leg with nothing loose.
usage: python3 tools/fit/cuff.py [IDs]   (without IDs: the 15 bottoms; exits with an error above MAX)"""
import sys, numpy as np
from garment import Garment
from metric import body, POSE_C
from paths import GARMENTS

TOP = .26      # from the shin down (the neutral body's ankle is at 0.12 m; the shin starts rising at 0.26)
DY = .01


def inside(q, pts):
    """Points pts (n×2) inside the closed loop q (even-odd, crossing the boundary towards +x)."""
    a, b = q[:-1], q[1:]; x, y = pts[:, :1], pts[:, 1:]
    crosses = (a[:, 1] > y) != (b[:, 1] > y)
    xc = a[:, 0] + (y - a[:, 1]) * (b[:, 0] - a[:, 0]) / np.where(b[:, 1] == a[:, 1], 1, b[:, 1] - a[:, 1])
    return ((crosses & (x < xc)).sum(1) % 2) == 1
MAX = 15.      # cm² outside the trouser leg (014 has 11.7 in open folds at the hem)


def loose(pid):
    m = Garment(GARMENTS + f'{pid}.glb').mesh(); b = body('C' if pid in POSE_C else 'B'); area = 0
    for y in np.arange(m.vertices[:, 1].min() + DY / 2, TOP, DY):
        s = m.section([0, 1, 0], [0, y, 0])
        if s is None: continue
        centers = [l[:, [0, 2]].mean(0) for l in b.section([0, 1, 0], [0, y, 0]).discrete if len(l) > 8]
        L = [l[:, [0, 2]] for l in s.discrete]
        leg = [q for q in L if np.allclose(q[0], q[-1], atol=1e-4) and len(centers) and inside(q, np.array(centers)).any()]
        for q in L:
            if any(q is p for p in leg): continue
            seg = np.linalg.norm(np.diff(q, axis=0), axis=1); mid = (q[1:] + q[:-1]) / 2
            out = np.ones(len(mid), bool)
            for p in leg: out &= ~inside(p, mid)   # the inner layer of the leg does not show
            area += seg[out].sum() * DY
    return area * 1e4


if __name__ == '__main__':
    bad = []
    for pid in sys.argv[1:] or [f'{i:03d}' for i in range(1, 16)]:
        v = loose(pid)
        print(f'{pid} fabric outside the trouser leg below {TOP} m: {v:.1f} cm²')
        if v > MAX: bad.append(f'{pid} {v:.1f} cm²')
    if bad: sys.exit(f'loose fabric outside the trouser leg (limit {MAX:.0f} cm²): ' + ', '.join(bad))
