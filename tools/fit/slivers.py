"""Removes the hem slivers that visual QA sees floating in the air: fringe tips that, in a view of the site orbit, show
apart from the garment with background between (the `loose` measure of tools/visual-qa/measure.py). On 006 they are
two tips of the frayed hem behind the sneaker, seen from below and in profile: attached to the leg in 3D, but on screen
they float (fringe.py, with a parallel camera, does not see them).
Each loose pixel becomes a ray of the view's perspective camera (the same as dressup.ts: target at 1.0 m, camera at
4.4 m, 30° field of view) and the first garment triangle it hits leaves the mesh (islands.remove). Only triangles go
away: position, UV and print of the rest stay. Run visual QA again afterwards: the tip that remains may show up loose
the next time.
usage: node tools/verify-site/visual-qa.mjs --looks NNN --out DIR
       python3 tools/fit/slivers.py DIR NNN   (then install.py --bottom NNN)"""
import os, sys, numpy as np
from scipy import ndimage as nd
from trimesh.ray.ray_pyembree import RayMeshIntersector
from garment import Garment
from islands import remove, clean

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '../visual-qa'))
import measure as M
from paths import GARMENTS

W, H = 720, 1200
TARGET, RADIUS, FOV = np.array([0, 1.0, 0]), 4.4, 30
POLAR = {'eye': 88, 'low': 111.6, 'high': 68.4}   # the views of tools/verify-site/visual-qa.mjs


def rays(px, py, view):
    """Origin and direction of the rays of pixels (px, py) of view 'name-az'."""
    name, az = view.split('-'); a, p = np.radians(float(az)), np.radians(POLAR[name])
    pos = np.array([np.sin(p) * np.sin(a), np.cos(p), np.sin(p) * np.cos(a)]) * RADIUS + TARGET
    f = (TARGET - pos) / np.linalg.norm(TARGET - pos); r = np.cross(f, [0, 1, 0]); r /= np.linalg.norm(r); u = np.cross(r, f)
    t = np.tan(np.radians(FOV / 2)); x = (2 * (px + .5) / W - 1) * t * W / H; y = (1 - 2 * (py + .5) / H) * t
    d = f + x[:, None] * r + y[:, None] * u
    return np.repeat(pos[None], len(px), 0), d / np.linalg.norm(d, axis=1, keepdims=True)


def loose(c):
    """Bottom garment pixels floating in the air: the same criterion as measure.measure_view."""
    bottom = np.isin(c, (M.BOTTOM, M.BOTTOM_BACK)); lab, n = nd.label(bottom)
    if n < 2: return np.zeros_like(bottom)
    areas = nd.sum(bottom, lab, range(1, n + 1)); largest = 1 + int(np.argmax(areas)); out = np.zeros_like(bottom)
    for i in range(1, n + 1):
        if i == largest or areas[i - 1] < 6: continue
        reg = lab == i
        if np.all(c[nd.binary_dilation(reg, M.disk(1)) & ~reg] == M.BACKGROUND): out |= reg
    return out


def slivers(folder, pid):
    path = GARMENTS + f'{pid}.glb'; g = Garment(path); m = g.mesh(); rm = RayMeshIntersector(m)
    out = np.zeros(len(m.faces), bool)
    for cls in sorted(os.listdir(os.path.join(folder, pid))):
        if not cls.endswith('.cls'): continue
        py, px = np.nonzero(loose(M.read_cls(os.path.join(folder, pid, cls))))
        if not len(px): continue
        t = rm.intersects_first(*rays(px, py, cls[:-4])); out[t[t >= 0]] = True
        print(f'  {cls[:-4]}: {len(px)} loose pixels, {len(np.unique(t[t >= 0]))} triangles')
    if out.any():
        remove(g, out, path)
        clean(path)   # removing edge triangles may leave a loose crumb (the check in site/fit.test.ts)
    print(f'{pid}: {out.sum()} triangles removed')


if __name__ == '__main__':
    slivers(sys.argv[1], sys.argv[2])
