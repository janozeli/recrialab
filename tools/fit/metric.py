"""Gap and penetration per garment, measured from the body.

From each body vertex a ray leaves along the normal: the first garment hit is the gap (+).
With no garment outside but some inside (ray along -normal), the body goes through the garment (-).
Covered region = vertices with garment up to 15 cm outside or 6 cm inside.
"""
import json, sys, numpy as np, trimesh
from trimesh.ray.ray_pyembree import RayMeshIntersector
from mask_io import load
from paths import BODY, GARMENTS, MASKS

REG = json.load(open(BODY + 'poses.json'))
POSE_C = set(REG['poseCBottomIds'])


def load_mesh(path):
    s = trimesh.load(path, process=False)
    if isinstance(s, trimesh.Scene):
        return trimesh.util.concatenate([g for g in s.dump()]) if hasattr(s, 'dump') else s.to_geometry()
    return s


def body(pose='B'):
    m = trimesh.load(BODY + ('pose-c.glb' if pose == 'C' else 'pose-b.glb'), process=False)
    m = list(m.geometry.values())[0] if isinstance(m, trimesh.Scene) else m
    return m


def masked_vertices(piece, b):
    path = MASKS + ('pose-c/' if piece in POSE_C else 'pose-b/') + f'{piece}.json'
    try:
        hid = load(path)
    except FileNotFoundError:
        return np.zeros(len(b.vertices), bool)
    v = np.zeros(len(b.vertices), bool)
    v[b.faces[hid].ravel()] = True
    return v


LEG_Y, LEG_X = .78, .01   # below the crotch of the neutral body (0.83 m), outside the 1 cm gap in the middle


def measure(garment, b, hidden=None, out_max=.15, in_max=.06, legs=False):
    """legs: below LEG_Y a ray that crosses the gap and hits the garment's other leg does not count (it is not gap)."""
    ri = RayMeshIntersector(garment)
    n = b.vertex_normals
    o = b.vertices + n * 1e-4
    # first intersection outward and inward
    def first(dirs, origins, maxd):
        loc, idx_ray, _ = ri.intersects_location(origins, dirs, multiple_hits=True)
        d = np.full(len(origins), np.inf)
        if len(idx_ray):
            dist = np.einsum('ij,ij->i', loc - origins[idx_ray], dirs[idx_ray])
            ok = dist > 0
            if legs:
                oy, ox = origins[idx_ray, 1], origins[idx_ray, 0]
                ok &= ~((oy < LEG_Y) & (np.abs(loc[:, 0]) > LEG_X) & (np.sign(loc[:, 0]) != np.sign(ox)))
            np.minimum.at(d, idx_ray[ok], dist[ok])
        d[d > maxd] = np.inf
        return d
    fwd = first(n, o, out_max)
    bwd = first(-n, o, in_max)
    covered = np.isfinite(fwd) | np.isfinite(bwd)
    signed = np.where(np.isfinite(fwd), fwd, -bwd)
    # area per vertex (1/3 of the adjacent faces)
    area = np.zeros(len(b.vertices))
    np.add.at(area, b.faces.ravel(), np.repeat(b.area_faces / 3, 3))
    c = covered
    a = area[c]
    s = signed[c]
    pen = s < -0.003
    res = {
        'covered_area_m2': round(float(a.sum()), 3),
        'penetrates_pct': round(100 * float(a[pen].sum() / a.sum()), 1) if a.sum() else 0,
        'gap_median_cm': round(100 * float(np.median(s[s >= 0])), 1) if (s >= 0).any() else None,
        'gap_p90_cm': round(100 * float(np.percentile(s[s >= 0], 90)), 1) if (s >= 0).any() else None,
        'gap_mean_cm': round(100 * float(np.average(np.clip(s, 0, None), weights=a)), 2),
        'gap_over_4cm_pct': round(100 * float(a[s > .04].sum() / a.sum()), 1) if a.sum() else 0,
    }
    if hidden is not None:
        vis = c & ~hidden
        av = area[vis]
        res['penetrates_visible_pct'] = round(100 * float(av[signed[vis] < -0.003].sum() / a.sum()), 1)
    return res, signed, covered


if __name__ == '__main__':
    ids = sys.argv[1:] or [f'{i:03d}' for i in range(1, 39)]
    bodies = {'B': body('B'), 'C': body('C')}
    rows = {}
    for pid in ids:
        g = load_mesh(GARMENTS + f'{pid}.glb')
        pose = 'C' if pid in POSE_C else 'B'
        b = bodies[pose]
        r, _, _ = measure(g, b, masked_vertices(pid, b))
        r['pose'] = pose
        r['y'] = [round(float(g.bounds[0][1]), 3), round(float(g.bounds[1][1]), 3)]
        rows[pid] = r
        print(pid, r, flush=True)
