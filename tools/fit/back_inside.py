"""Inside of the tops seen from behind: a sleeve fold that passes through the back panel shows the garment's inside.

Rays from behind (one every 2 mm, from 0.6 m up to NECK, below the open hood) meet the published piece; where the first
face they meet is turned to the body, in a patch closed all around by the outside of the garment, the inside shows
through a hole (the lining past the hem, an open front or a cut-out reach the edge of the garment and do not count). The texture there is the lining, and the site paints it dark:
a hole in the back (034, when repose_sleeves.py turned the armpit fold through the back panel).
Each piece is held to its recorded value (BASELINE, cm², which only goes down); TOLERANCE absorbs the ray grid.
usage: python3 tools/fit/back_inside.py           (CI: each top against BASELINE)
       python3 tools/fit/back_inside.py --measure (prints each top)"""
import sys, numpy as np
from scipy import ndimage as nd
from trimesh.ray.ray_pyembree import RayMeshIntersector
from garment import Garment
from paths import GARMENTS

NECK = 1.45
TOLERANCE = .5
BASELINE = {   # cm², measured on 26/10
    '016': 0.0,
    '017': 0.0,
    '018': 0.4,
    '019': 13.6,
    '020': 0.2,
    '021': 2.6,
    '022': 0.3,
    '023': 0.0,
    '024': 24.2,
    '025': 0.0,
    '026': 0.0,
    '027': 0.2,
    '028': 2.6,
    '029': 0.0,
    '030': 74.3,
    '031': 0.3,
    '032': 0.4,
    '033': 6.6,
    '034': 0.1,
    '035': 2.7,
    '036': 0.0,
    '037': 31.4,
    '038': 12.9,
}


def back_inside(m, P=None):
    """Area (cm²) below NECK where a ray from behind first meets a face turned to the body, in patches closed all
    around by the outside of the garment (a hole in the back); a patch that reaches the edge of the garment is the
    lining seen past the hem, an open front or a cut-out, as the photo has it."""
    mesh = m.copy()
    if P is not None: mesh.vertices = P
    xs, ys = np.meshgrid(np.arange(-.45, .45, .002), np.arange(.6, NECK, .002))
    O = np.c_[xs.ravel(), ys.ravel(), np.full(xs.size, -1.)]
    tri = RayMeshIntersector(mesh).intersects_first(O, np.tile([0, 0, 1.], (len(O), 1)))
    hit = (tri >= 0).reshape(xs.shape)
    inside = np.zeros(len(O), bool); inside[tri >= 0] = mesh.face_normals[tri[tri >= 0], 2] > 0
    inside = inside.reshape(xs.shape)
    lab, n = nd.label(inside)
    edge = np.unique(lab[nd.binary_dilation(~hit) & inside])
    return np.isin(lab, np.setdiff1d(np.arange(1, n + 1), edge)).sum() * .04


if __name__ == '__main__':
    bad = []
    for pid, base in BASELINE.items():
        g = Garment(f'{GARMENTS}{pid}.glb'); P = g.vertices(); a = back_inside(g.mesh(P))
        if '--measure' in sys.argv or a > base + TOLERANCE:
            print(f'{pid}: {a:.1f} cm² (recorded {base})')
        if a > base + TOLERANCE: bad.append(pid)
    if bad: sys.exit(f'more of the inside shows from behind than recorded: {", ".join(bad)}')
