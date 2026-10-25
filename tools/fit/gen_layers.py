"""Top/bottom layers: hides the bottom garment's triangle that sits under the top or pokes through it.
Same rule as the body masks, with the bottom garment in place of the body. The ray along the normal catches the whole
triangle even when only one corner of it is under the hem; so the triangle the cameras see uncovered (no top in front
nor right behind) and that no camera sees poking through the top comes back. Without this the pants vanish in a
jagged line right below the blouse hem (`layer_check.py` measures it)."""
import numpy as np
from trimesh.ray.ray_pyembree import RayMeshIntersector
from gen_mask import hits, samples, cameras, first


def to_ranges(idx):
    out = []
    for i in idx:
        if out and i == out[-1][1] + 1: out[-1][1] = int(i)
        else: out.append([int(i), int(i)])
    return out


# layer window: from the lowest hem (036, 0.57 m) to the chest, also looking up at the hem from below
WINDOW = dict(step=.006, center=1.05, half=.62, elevs=(-.3, 0, .25))
UNDER = .15   # the same distance as the normal rule: the top up to 15 cm behind is a poke-through, not uncovered


def uncovered(ri, m):
    """Per bottom triangle, how many camera rays see it uncovered (no top in front nor up to UNDER behind) and how
    many see it poking through the top (the top up to UNDER behind)."""
    rb = RayMeshIntersector(m); exposed = np.zeros(len(m.faces), int); pokes = exposed.copy()
    for o, d in cameras(**WINDOW):
        tg, _ = first(ri, o, d); tb, fb = first(rb, o, d)
        with np.errstate(invalid='ignore'):
            seen = np.isfinite(tb)
            np.add.at(exposed, fb[seen & ~(tg < tb + UNDER)], 1)
            np.add.at(pokes, fb[seen & (tb < tg) & (tg - tb < UNDER)], 1)
    return exposed, pokes


def poking(ri, m, hide):
    """Rays that see each visible triangle in front of the top with the top up to UNDER behind."""
    vis = np.nonzero(~hide)[0]; rv = RayMeshIntersector(m.submesh([vis], append=True))
    out = np.zeros(len(m.faces), int)
    for o, d in cameras(**WINDOW):
        tg, _ = first(ri, o, d); tv, fv = first(rv, o, d)
        with np.errstate(invalid='ignore'):
            np.add.at(out, vis[fv[np.isfinite(tv) & (tv < tg) & (tg - tv < UNDER)]], 1)
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
