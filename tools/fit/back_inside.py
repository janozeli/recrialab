"""Inside of the tops seen from behind: a sleeve fold that passes through the back panel shows the garment's inside.

Rays from behind (one every 2 mm, from 0.6 m up to NECK, below the open hood) meet the published piece; where the first
face they meet is turned to the body, the inside shows. The texture there is the lining, and the site paints it dark:
a hole in the back (034, when repose_sleeves.py turned the armpit fold through the back panel).
Each piece is held to its recorded value (BASELINE, cm², which only goes down); TOLERANCE absorbs the ray grid.
usage: python3 tools/fit/back_inside.py           (CI: each top against BASELINE)
       python3 tools/fit/back_inside.py --measure (prints each top)"""
import sys, numpy as np
from trimesh.ray.ray_pyembree import RayMeshIntersector
from garment import Garment
from paths import GARMENTS

NECK = 1.45
TOLERANCE = .5
BASELINE = {   # cm², measured on 25/10; open fronts, cut-outs and the hem seen from behind count, as they are
    '016': 4.1,
    '017': 5.4,
    '018': 1.6,
    '019': 14.7,
    '020': 160.5,
    '021': 3.2,
    '022': 89.4,
    '023': .9,
    '024': 24.2,
    '025': 2.2,
    '026': 2.7,
    '027': 4.8,
    '028': 7.2,
    '029': 2.5,
    '030': 160.2,
    '031': .3,
    '032': .4,
    '033': 32.5,
    '034': .1,
    '035': 3.6,
    '036': 115.6,
    '037': 33.2,
    '038': 18.0,
}


def back_inside(m, P=None):
    """Area (cm²) below NECK where a ray from behind first meets a face turned to the body."""
    mesh = m.copy()
    if P is not None: mesh.vertices = P
    xs, ys = np.meshgrid(np.arange(-.35, .35, .002), np.arange(.6, NECK, .002))
    O = np.c_[xs.ravel(), ys.ravel(), np.full(xs.size, -1.)]
    tri = RayMeshIntersector(mesh).intersects_first(O, np.tile([0, 0, 1.], (len(O), 1)))
    return (mesh.face_normals[tri[tri >= 0], 2] > 0).sum() * .04


if __name__ == '__main__':
    bad = []
    for pid, base in BASELINE.items():
        g = Garment(f'{GARMENTS}{pid}.glb'); P = g.vertices(); a = back_inside(g.mesh(P))
        if '--measure' in sys.argv or a > base + TOLERANCE:
            print(f'{pid}: {a:.1f} cm² (recorded {base})')
        if a > base + TOLERANCE: bad.append(pid)
    if bad: sys.exit(f'more of the inside shows from behind than recorded: {", ".join(bad)}')
