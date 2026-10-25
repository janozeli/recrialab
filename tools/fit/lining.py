"""Removes the lining that shows below the front hem of a top. On jacket 033 the 3D generator left the bottom of the
lining (the inner layer, 1.5 to 6 cm behind the outer fabric) hanging down to 4 cm below the hem: from the front it
shows as darker points over the trousers, which the photo does not have. Per 1 cm column
of the front (|x| up to 17 cm), the shell is the fabric up to 1.2 cm behind the frontmost in the bottom 6 cm; what
sits below the shell's hem and more than 1.5 cm behind it is lining and leaves the mesh (islands.remove). Only
triangles disappear: position, UV and print of the rest stay the same. The same computation, in site/fit.test.ts,
holds each top to its recorded baseline (hems that fold inwards, like ribbed ones, also count and do not show; that is why
the check is a baseline that only goes down, not a fixed limit).
usage: python3 tools/fit/lining.py --measure     (the area of each top, in cm²)
       python3 tools/fit/lining.py 033            (removes it; then install.py --mask 033 and layer_tables.py)"""
import sys, numpy as np
from garment import Garment
from islands import remove, clean
from paths import GARMENTS

SHELL, LINING, WINDOW = .012, .015, .06


def lining(g):
    """Per-triangle mask (Garment.mesh() order) of the lining below the hem, and its area in cm²."""
    P = g.vertices(); m = g.mesh(P); T = P[m.faces]; c = T.mean(1)
    area = np.linalg.norm(np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]), axis=1) / 2
    out = np.zeros(len(c), bool)
    for x0 in np.arange(-.17, .171, .01):
        col = (np.abs(c[:, 0] - x0) < .005) & (c[:, 2] > 0) & (c[:, 1] > .5) & (c[:, 1] < 1.2)
        if col.sum() < 5: continue
        win = col & (c[:, 1] < c[col, 1].min() + WINDOW)
        zf = c[win, 2].max()
        hem = c[win & (c[:, 2] > zf - SHELL), 1].min()
        out |= col & (c[:, 1] < hem) & (c[:, 2] < zf - LINING)
    return out, float(area[out].sum() * 1e4)


if __name__ == '__main__':
    if sys.argv[1:] == ['--measure']:
        for i in range(16, 39):
            print(f'{i:03d} {lining(Garment(GARMENTS + f"{i:03d}.glb"))[1]:.1f}')
    for pid in sys.argv[1:]:
        if pid.startswith('--'): continue
        path = GARMENTS + f'{pid}.glb'; g = Garment(path)
        out, cm2 = lining(g)
        remove(g, out, path); clean(path)
        print(f'{pid}: lining of {cm2:.1f} cm² removed ({out.sum()} triangles)')
