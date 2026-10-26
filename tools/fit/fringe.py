"""Trims the thin points of the hem of the bottoms (spiky fringe and slivers of 007, 008, 009 and 010).

The 3D generator produced the frayed hem as spikes of 3 to 8 cm, thinner than 1.4 cm, which the shop photo does not
have (there the fringe is short). It looks at the piece alone from the 14 points of the site's orbit (those of
tools/visual-qa) and finds, on the silhouette, what is thinner than 1.4 cm with the same rule as
tools/visual-qa/measure.py (thin). The triangles forming that thin part pull back to the root (the closest vertex,
along the mesh, outside the thin part): half the way per round, until the thin part of each view fits in TARGET.
Short fringe (below the minimum thin area) stays. The waistband is left out (belt loops). Only positions and normals
change; UV and texture stay the same.
usage: python3 tools/fit/fringe.py INPUT.glb OUTPUT.glb
       python3 tools/fit/fringe.py --measure NNN ...   (thin part per view, the piece alone, in cm²)"""
import os, sys, numpy as np, trimesh
from collections import deque
from scipy.spatial import cKDTree
from trimesh.ray.ray_pyembree import RayMeshIntersector
from garment import Garment
from metric import POSE_C, body

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '../visual-qa'))
from measure import thin, CM  # noqa: E402  (the same measure the CI check uses)
from paths import GARMENTS, piece_id

PX = CM / 100        # meters per pixel on the mannequin plane (site camera)
TARGET = 4e-4        # thin part per view after trimming (m²): a third of measure.py's limit
HEM = .25            # bottom band (fraction of the piece height) where the shred cut out by the leg is trimmed too
WAISTBAND = .06      # from the top down: belt loops and waistband do not move
ROUNDS = 8
SLACK = .006         # what pulled back stays at least this far from the body (or where it was, if closer)
VIEWS = [(az, 88) for az in range(0, 360, 45)] + [(az, 111.6) for az in (0, 90, 180, 270)] + [(az, 68.4) for az in (0, 180)]


def weld(P, faces):
    _, inv = np.unique(np.round(P, 5), axis=0, return_inverse=True); inv = inv.ravel()
    X = np.zeros((inv.max() + 1, 3)); X[inv] = P
    return X, inv, inv[faces]


def view(m, ri, az, polar, n_garment=None):
    """Silhouette of the piece seen from (az, polar) in parallel projection with the site's pixel: mask and triangle per pixel."""
    a, p = np.radians(az), np.radians(polar)
    d = -np.array([np.sin(p) * np.sin(a), np.cos(p), np.sin(p) * np.cos(a)])      # from the camera to the mannequin
    dir_x = np.array([np.cos(a), 0, -np.sin(a)]); dir_y = np.cross(dir_x, d)
    dir_y /= np.linalg.norm(dir_y)
    u, v = m.vertices @ dir_x, m.vertices @ dir_y
    u, v = u[:n_garment], v[:n_garment]
    us = np.arange(u.min() - 4 * PX, u.max() + 4 * PX, PX); vs = np.arange(v.max() + 4 * PX, v.min() - 4 * PX, -PX)
    U, V = np.meshgrid(us, vs)
    o = U.ravel()[:, None] * dir_x + V.ravel()[:, None] * dir_y - d * 3
    tri = ri.intersects_first(o, np.tile(d, (len(o), 1))).reshape(U.shape)
    return tri >= 0, tri


def thin_parts(m, faces_ok, body_mesh, hem=None):
    """Per view: thin area (m²) and the triangles that show in it (only those in faces_ok). The body comes in front
    as on the site: the leg in front of the hem leaves only a shred of it visible."""
    both = trimesh.util.concatenate([m, body_mesh]); n = len(m.faces)
    ri, rs = RayMeshIntersector(both), RayMeshIntersector(m); areas, marked = [], np.zeros(n, bool)
    for az, polar in VIEWS:
        _, tri = view(both, ri, az, polar, len(m.vertices))
        f = thin((tri >= 0) & (tri < n))
        areas.append(float(f.sum() * PX * PX))
        if hem is not None:   # at the hem, the shred left between the leg and the edge is long fringe too
            t = tri[f]; marked[t[hem[t]]] = True
        # mark only what is thin on the piece alone (a spike); the shred the leg cuts out of the hem is normal fabric
        _, tri = view(m, rs, az, polar)
        f = thin(tri >= 0)
        t = tri[f]
        marked[t[faces_ok[t]]] = True
    return np.array(areas), marked


def trim(src, dst):
    g = Garment(src); P0 = g.vertices(); m0 = g.mesh(P0)
    X0, inv, F = weld(P0, m0.faces)
    pid = piece_id(src); body_mesh = body('C' if pid in POSE_C else 'B')
    X = X0.copy(); top = X0[:, 1].max()
    faces_ok = X0[F][:, :, 1].max(1) < top - WAISTBAND
    bottom = X0[:, 1].min(); hem = X0[F][:, :, 1].max(1) < bottom + HEM * (top - bottom)
    S, fi = trimesh.sample.sample_surface_even(body_mesh, 300000, seed=1); SN = body_mesh.face_normals[fi]; T = cKDTree(S)
    def side(Y):
        _, j = T.query(Y); return np.einsum('ij,ij->i', Y - S[j], SN[j]), j
    floor = np.minimum(side(X0)[0], SLACK)
    nv = len(X)
    nb = [[] for _ in range(nv)]
    for a, b in trimesh.Trimesh(X0, F, process=False).edges_unique:
        nb[a].append(b); nb[b].append(a)
    before = None
    for rnd in range(ROUNDS):
        m = trimesh.Trimesh(X, F, process=False)
        areas, marked = thin_parts(m, faces_ok, body_mesh, hem)
        if before is None: before = areas
        print(f'  round {rnd}: max thin part {areas.max() * 1e4:.1f} cm² ({VIEWS[int(areas.argmax())]}), {marked.sum()} triangles')
        if areas.max() <= TARGET or not marked.any():
            break
        # pull every vertex of the thin part back to the root: the closest thick-fabric vertex along the mesh
        free = np.zeros(nv, bool); free[F[marked].ravel()] = True
        root = np.full(nv, -1); queue = deque()
        for i in np.nonzero(free)[0]:
            for j in nb[i]:
                if not free[j] and root[j] < 0: root[j] = j; queue.append(j)
        while queue:
            i = queue.popleft()
            for j in nb[i]:
                if free[j] and root[j] < 0:
                    root[j] = root[i]; queue.append(j)
        moves = free & (root >= 0)
        X[moves] = X[root[moves]] + (X[moves] - X[root[moves]]) * .5
        # what pulled back inside the thigh comes out to the gap it had (otherwise the thigh pokes through the hem)
        for _ in range(3):
            moved = np.linalg.norm(X - X0, axis=1) > 1e-5
            d, j = side(X[moved])
            X[moved] += SN[j] * np.maximum(floor[moved] - d, 0)[:, None]
    m = trimesh.Trimesh(X, F, process=False)
    areas, _ = thin_parts(m, faces_ok, body_mesh)
    print(f'{src}: max thin part {before.max() * 1e4:.1f} -> {areas.max() * 1e4:.1f} cm²; '
          f'largest pull-back {100 * np.linalg.norm(X - X0, axis=1).max():.1f} cm on {(np.linalg.norm(X - X0, axis=1) > 1e-4).sum()} vertices')
    g.save(dst, X[inv], before=P0)


if __name__ == '__main__':
    if sys.argv[1:2] == ['--measure']:
        for pid in sys.argv[2:]:
            g = Garment(GARMENTS + f'{pid}.glb'); X, _, F = weld(g.vertices(), g.mesh().faces)
            a, _ = thin_parts(trimesh.Trimesh(X, F, process=False), np.ones(len(F), bool), body('C' if pid in POSE_C else 'B'))
            print(pid, 'thin part per view (cm²):', ' '.join(f'{v * 1e4:.1f}' for v in a))
    else:
        trim(*sys.argv[1:3])
