"""Removes the cords the 3D generator hung on the front of skirt 009 (the shop photo has two buttons and short belt
loops on the waistband).

The cords are tubes stuck to the front: the ray leaving each triangle inwards, along the normal, hits the fabric
underneath at less than CORD. The large pieces like that on the front, between the waistband and the hem, are the
cords, the knot and the long belt loop. The mesh has no fabric under the cord (it is relief of the surface itself:
pushing it back opens a hole, pulling it to the root stretches triangles on the front), so the tube and a ring of
fabric around it relax to the average of their neighbours, with the border held: the relief becomes plain fabric.
The belt loop stays up to the waistband seam (LOOP), as in the photo. Only positions and normals change; UV and
texture stay the same.
usage: python3 tools/fit/cords.py INPUT.glb OUTPUT.glb
       python3 tools/fit/cords.py --measure [--max CM2] [GLB]   (cord area on the front, in cm², the CI check; without GLB, the site's 009)"""
import sys, numpy as np, trimesh
from trimesh.ray.ray_pyembree import RayMeshIntersector
from garment import Garment
from fringe import weld
from paths import GARMENTS


CORD = .004          # fabric just behind the triangle (m): a tube stuck to the front
MIN_AREA = 1e-3      # a piece smaller than this (10 cm²) is a fold of the pocket or zipper, not a cord
LOOP = .905          # height of the waistband seam (m): the belt loop stays above it
TUBE = .012          # side and back of the tube: fabric closer than this behind
RINGS = 4
RELAX = 400
MARGIN = 1           # rings of fabric around the cord that relax with it
TARGET = 5e-4        # cord left over (m²)
ROUNDS = 8


def cords(X, F):
    """Triangles of the cords (the whole tube), minus what stays of them (the belt loop above the waistband seam)."""
    w = trimesh.Trimesh(X, F, process=False)
    ri = RayMeshIntersector(w); c, n = w.triangles_center, w.face_normals
    loc, ir, _ = ri.intersects_location(c - n * 1e-4, -n, multiple_hits=False)
    din = np.full(len(c), np.inf); din[ir] = np.linalg.norm(loc - c[ir], axis=1)
    zone = (c[:, 1] > .66) & (c[:, 1] < 1.02) & (c[:, 2] > 0)
    # the side belt loop (|x| > 5 cm) stays above the waistband seam; the middle cords, with the knot, go entirely
    zone &= ~((np.abs(c[:, 0]) > .05) & (c[:, 1] > LOOP))
    cand = (din < CORD) & zone
    adj = w.face_adjacency
    ok = cand[adj[:, 0]] & cand[adj[:, 1]]
    sel = np.zeros(len(F), bool)
    for k in trimesh.graph.connected_components(adj[ok], nodes=np.nonzero(cand)[0], min_len=1):
        if w.area_faces[k].sum() >= MIN_AREA: sel[k] = True
    for _ in range(RINGS):   # sides and back of the tube: neighbours with fabric just behind
        nb = np.zeros(len(F), bool); nb[adj[sel[adj[:, 0]] | sel[adj[:, 1]]].ravel()] = True
        sel |= nb & (din < TUBE) & zone
    return sel, w


def remove(src, dst):
    g = Garment(src); P0 = g.vertices(); m0 = g.mesh(P0)
    X0, inv, F = weld(P0, m0.faces)
    nb = [[] for _ in range(len(X0))]
    for a, b in trimesh.Trimesh(X0, F, process=False).edges_unique:
        nb[a].append(b); nb[b].append(a)
    X = X0.copy()
    for rnd in range(ROUNDS):
        out, w = cords(X, F)
        print(f'  round {rnd}: cord {w.area_faces[out].sum() * 1e4:.1f} cm²')
        if w.area_faces[out].sum() < TARGET: break
        # the tube becomes fabric: each vertex that is only cord moves to the average of its neighbours, with the
        # border held in the fabric around it (the mesh has no fabric under the cord; pushing it back opens a hole).
        # The cord is relief of the surface itself, so a ring of fabric around it joins, to leave free vertices.
        free_faces = out.copy()
        for _ in range(MARGIN):
            v = np.zeros(len(X), bool); v[F[free_faces].ravel()] = True; free_faces |= v[F].any(1)
        free = np.zeros(len(X), bool); free[F[free_faces].ravel()] = True; free[F[~free_faces].ravel()] = False
        idx = np.nonzero(free)[0]
        for _ in range(RELAX):
            X[idx] = np.array([X[nb[i]].mean(0) for i in idx])
    d = np.linalg.norm(X - X0, axis=1)
    print(f'{src}: {(d > 1e-4).sum()} vertices, largest displacement {100 * d.max():.1f} cm')
    g.save(dst, X[inv], before=P0)


def measure(glb):
    g = Garment(glb); P = g.vertices(); X, _, F = weld(P, g.mesh(P).faces)
    out, w = cords(X, F)
    return float(w.area_faces[out].sum() * 1e4)


if __name__ == '__main__':
    if sys.argv[1:2] == ['--measure']:
        a = sys.argv[2:]; lim = float(a[1]) if a[:1] == ['--max'] else None; a = a[2:] if lim is not None else a
        area = measure(a[0] if a else GARMENTS + '009.glb')
        print(f'cord {area:.1f} cm²')
        if lim is not None and area > lim: sys.exit(f'cord hanging on the front of 009: {area:.1f} cm² (limit {lim})')
    else:
        remove(*sys.argv[1:3])
