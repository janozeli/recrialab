"""Hood and collar as a loose part in few polygons.

A shell (shell.py) flattens a hood onto the back. From the generated garment this keeps what is above the neck
line, or behind the back and away from the body, between the shoulders; only the large pieces (no slivers);
simplified to TARGET triangles and with the texture baked again from the garment.
usage: python3 tools/fit/loose_hood.py DENSE_BODY.glb GARMENT.glb OUT.glb"""
import sys, numpy as np, trimesh, fast_simplification
from scipy.spatial import cKDTree
from garment import Garment
import shell as S

FAR, NECK, BASE, SHOULDERS = .03, 1.47, 1.22, .19   # m: away from the body; neck line; lowest height; half width kept
MIN_AREA = .004        # m²: a kept piece smaller than this is a sliver
TARGET = 260           # triangles


def build(dense_path, src, dst):
    b = S.load_body(dense_path); body, _ = trimesh.sample.sample_surface_even(b, 200000, seed=1); kd = cKDTree(body)
    g = Garment(src).mesh(); m = trimesh.Trimesh(g.vertices, g.faces, process=False); m.merge_vertices(digits_vertex=4)
    P = np.asarray(m.vertices); d, j = kd.query(P)
    behind = np.minimum(np.minimum(d - FAR, (body[j, 2] - P[:, 2]) - .01), P[:, 1] - BASE)
    keep = (np.maximum(P[:, 1] - NECK, behind) > 0) & (np.abs(P[:, 0]) < SHOULDERS)
    m = trimesh.Trimesh(P, m.faces[keep[m.faces].sum(1) >= 2], process=False); m.remove_unreferenced_vertices()
    pieces = [p for p in m.split(only_watertight=False) if p.area > MIN_AREA]
    if not pieces: return None
    m = trimesh.util.concatenate(pieces)
    V, F = fast_simplification.simplify(np.asarray(m.vertices, np.float32), np.asarray(m.faces), target_count=TARGET, agg=5)
    N = np.asarray(trimesh.Trimesh(V, F, process=False).vertex_normals)
    base = V - N * .008
    dense, _ = trimesh.sample.sample_surface(trimesh.Trimesh(base, F, process=False), 40000, seed=1)
    V2, N2, UV, F2, img, missing = S.bake(S.Piece(src), cKDTree(dense), dense, V, base, N, F, .03, limbs=False)
    S.export(dst, V2, F2, N2, UV, img, double_sided=True)
    return {'triangles': int(len(F2)), 'triangles_before': int(len(m.faces)), 'pieces': len(pieces), 'texture_without_source_pct': round(100 * missing, 1)}


if __name__ == '__main__':
    print(build(*sys.argv[1:4]))
