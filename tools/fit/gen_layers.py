"""Top/bottom layers: hides the bottom garment's triangle that sits under the top or pokes through it.
Same rule as the body masks, with the bottom garment in place of the body. The ray along the normal catches the whole
triangle even when only one corner of it is under the hem; so the triangle the cameras see uncovered (no top in front
nor right behind) and that no camera sees poking through the top comes back. Without this the pants vanish in a
jagged line right below the blouse hem (`layer_check.py` measures it).
The top behind the bottom only counts as a poke-through when the ray meets its outside, as in layer_check.py. Looking
up through the hem of a loose jacket the ray meets the inside of its back, and the waistband there is where it
belongs: counted as poking through, it vanished and the background showed in its place (jacket 033 over shorts 003,
view from below). A top closer than CLOSE behind still covers from either side: the inner fold of a rib hem lies
right against the waistband, and showing it there left thin threads of the bottom (skirt 007 under hoodie 037). The
site's own cameras vote too, besides the layer window."""
import numpy as np
from trimesh.ray.ray_pyembree import RayMeshIntersector
from itertools import chain
from gen_mask import hits, samples, cameras, first, site_cameras


def to_ranges(idx):
    out = []
    for i in idx:
        if out and i == out[-1][1] + 1: out[-1][1] = int(i)
        else: out.append([int(i), int(i)])
    return out


# layer window: from the lowest hem (036, 0.57 m) to the chest, also looking up at the hem from below
WINDOW = dict(step=.006, center=1.05, half=.62, elevs=(-.3, 0, .25))
CLOSE = .03   # the top this close behind covers the bottom from either side (the fold of a rib hem)
UNDER = .15   # the same distance as the normal rule: the top up to 15 cm behind is a poke-through, not uncovered


def uncovered(ri, m):
    """Per bottom triangle, how many camera rays see it uncovered (no top in front nor up to UNDER behind) and how
    many see it poking through the top (the top up to UNDER behind, showing its outside)."""
    rb = RayMeshIntersector(m); exposed = np.zeros(len(m.faces), int); pokes = exposed.copy()
    for o, d in chain(cameras(**WINDOW), site_cameras()):
        tg, fg = first(ri, o, d); tb, fb = first(rb, o, d)
        with np.errstate(invalid='ignore'):
            seen = np.isfinite(tb); near = (tg < tb + UNDER) & (outside(ri, fg, d) | (tg < tb + CLOSE))
            np.add.at(exposed, fb[seen & ~near], 1)
            np.add.at(pokes, fb[seen & (tb < tg) & near], 1)
    return exposed, pokes


def outside(ri, fg, d):
    """The top's face shows its outside to the ray (normal against it): the bottom went through it. Showing the
    inside, the camera looks up through the hem into the top, and the bottom there is where it belongs."""
    n = ri.mesh.face_normals[np.maximum(fg, 0)]
    return (fg >= 0) & (np.einsum('ij,ij->i', n, d) < 0)


def poking(ri, m, hide):
    """Rays that see each visible triangle in front of the top with the top up to UNDER behind, showing its
    outside."""
    vis = np.nonzero(~hide)[0]; rv = RayMeshIntersector(m.submesh([vis], append=True))
    out = np.zeros(len(m.faces), int)
    for o, d in chain(cameras(**WINDOW), site_cameras()):
        tg, fg = first(ri, o, d); tv, fv = first(rv, o, d)
        with np.errstate(invalid='ignore'):
            f = np.isfinite(tv) & (tv < tg) & (tg - tv < UNDER) & (outside(ri, fg, d) | (tg - tv < CLOSE))
            np.add.at(out, vis[fv[f]], 1)
    return out


def pair(bottom, top_mesh, under=.15, inside=.06):
    ri = RayMeshIntersector(top_mesh)
    W = bottom.vertices(); m = bottom.mesh(W)
    F = m.faces; n = m.face_normals
    ok = np.isfinite(n).all(1) & (np.linalg.norm(n, axis=1) > .5)
    hide = np.zeros(len(F), bool)
    for p in samples(W, F):
        o = p + n * 1e-4
        hide |= np.isfinite(hits(ri, o, n, under)) | np.isfinite(hits(ri, o, -n, inside))
    hide &= ok
    # the triangle seen uncovered more often than poking through comes back: a sliver poking through the hem
    # weighs less than the pink hole in its place
    exposed, pokes = uncovered(ri, m)
    back = hide & (exposed > 2 * pokes)
    for _ in range(5):   # what comes back may poke through the top behind another hidden triangle
        f = poking(ri, m, hide & ~back)
        drop = back & (f > 0) & (exposed <= 2 * (pokes + f))
        if not drop.any(): break
        back &= ~drop
    else:
        back &= ~(poking(ri, m, hide & ~back) > 0)   # without converging: nothing that still pokes through comes back
    hide &= ~back
    res, off = [], 0
    for (a, M, p) in bottom.parts:
        t = bottom.js['accessors'][p['indices']]['count'] // 3
        res.append(to_ranges(np.nonzero(hide[off:off + t])[0])); off += t
    return res
