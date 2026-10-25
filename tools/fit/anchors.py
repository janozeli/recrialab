"""Support anchors: where the garment should rest on the body under gravity.
Tops: shoulders (vertical gap from the shoulder to the garment) and collar (horizontal gap around the neck).
Bottoms: waistband (horizontal gap from the waistband to the body, in the top 4 cm of the piece)."""
import sys, numpy as np, trimesh
from metric import POSE_C, body, load_mesh
from trimesh.ray.ray_pyembree import RayMeshIntersector
from paths import GARMENTS

def first_hit(mesh, o, d, maxd=.2):
    ri = RayMeshIntersector(mesh)
    loc, ir, _ = ri.intersects_location(o, d, multiple_hits=True)
    out = np.full(len(o), np.inf)
    if len(ir):
        dist = np.einsum('ij,ij->i', loc - o[ir], d[ir]); ok = dist > 0
        np.minimum.at(out, ir[ok], dist[ok])
    out[out > maxd] = np.inf
    return out

B = {'B': body('B'), 'C': body('C')}
def anchors(pid, g=None, b=None):
    g = g or load_mesh(GARMENTS + f'{pid}.glb')
    b = b or B['C' if pid in POSE_C else 'B']
    V, N = b.vertices, b.vertex_normals
    top = int(pid) >= 16
    r = {}
    if top:
        sh = (N[:, 1] > .6) & (V[:, 1] > 1.44) & (V[:, 1] < 1.56) & (np.abs(V[:, 0]) > .07) & (np.abs(V[:, 0]) < .2)
        up = first_hit(g, V[sh] + [0, 1e-4, 0], np.tile([0, 1., 0], (sh.sum(), 1)))
        r['shoulder_cm'] = round(100 * float(np.median(up[np.isfinite(up)])), 1) if np.isfinite(up).any() else None
        r['shoulder_covered_pct'] = round(100 * float(np.isfinite(up).mean()))
        # collar: neck ring at 1.53..1.58, horizontal rays
        nk = (V[:, 1] > 1.53) & (V[:, 1] < 1.58) & (np.abs(N[:, 1]) < .5)
        d = N[nk] * [1, 0, 1]; d /= np.linalg.norm(d, axis=1, keepdims=True)
        h = first_hit(g, V[nk] + d * 1e-4, d, .12)
        r['collar_cm'] = round(100 * float(np.median(h[np.isfinite(h)])), 1) if np.isfinite(h).any() else None
        r['collar_covered_pct'] = round(100 * float(np.isfinite(h).mean()))
        r['top_y'] = round(float(g.bounds[1][1]), 3)
    else:
        ytop = g.bounds[1][1]
        ring = (V[:, 1] > ytop - .06) & (V[:, 1] < ytop - .01) & (np.abs(N[:, 1]) < .5) & (np.abs(V[:, 0]) < .2)
        d = N[ring] * [1, 0, 1]; d /= np.linalg.norm(d, axis=1, keepdims=True)
        h = first_hit(g, V[ring] + d * 1e-4, d, .15)
        hb = first_hit(g, V[ring] + d * 1e-4, -d, .06)
        s = np.where(np.isfinite(h), h, -hb)
        f = np.isfinite(s)
        r['waistband_median_cm'] = round(100 * float(np.median(s[f])), 1) if f.any() else None
        r['waistband_front_cm'] = round(100 * float(np.median(s[f & (d[:, 2] > .7)])), 1) if (f & (d[:, 2] > .7)).any() else None
        r['waistband_back_cm'] = round(100 * float(np.median(s[f & (d[:, 2] < -.7)])), 1) if (f & (d[:, 2] < -.7)).any() else None
        r['waistband_side_cm'] = round(100 * float(np.median(s[f & (np.abs(d[:, 0]) > .7)])), 1) if (f & (np.abs(d[:, 0]) > .7)).any() else None
        r['top_y'] = round(float(ytop), 3)
    return r

if __name__ == '__main__':
    for pid in sys.argv[1:] or [f'{i:03d}' for i in range(1, 39)]:
        print(pid, anchors(pid), flush=True)
