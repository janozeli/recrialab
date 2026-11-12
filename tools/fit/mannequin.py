"""The engine's mannequin, derived from the site's body: a curved back, then a low-poly body built in parts.

Every garment showed a straight back because the mannequin's back is straight: it varies by less than 2 cm between
glute, lumbar and shoulder blade. curved() pulls the lumbar in and pushes the shoulder blade and the glute out on
the dense body. lowpoly() fits rings to that body, in parts as on a PS1 character: torso with 12 sides, head, arms
and legs with 8, sloped shoulder, flat hand, foot. Both are derived, never stored: engine.py builds them from
site/assets/body/pose-b.glb and pose-c.glb on every run, so they cannot drift from the body.
Origin: the PS1/PS2 look study (costas.py, lowpoly.py).
usage: python3 tools/fit/mannequin.py B|C DENSE_OUT.glb LOWPOLY_OUT.glb"""
import sys, numpy as np, trimesh
from scipy.spatial import cKDTree
from landmarks import limb
from paths import BODY

# (shift in z, height, spread) in meters. The lumbar goes in by 0.8 cm only: at 3 cm the back curved but the waist
# read as too thin (girth at 1.06 m: 68.0 cm on the site's body, 63.5 with 3 cm, 66.7 with 0.8)
LUMBAR, BLADE, GLUTE = (.008, 1.05, .08), (-.022, 1.36, .07), (-.02, .88, .06)
GREY = [235, 235, 240, 255]


def material():
    return trimesh.visual.TextureVisuals(material=trimesh.visual.material.PBRMaterial(baseColorFactor=GREY, metallicFactor=0, roughnessFactor=1))


def curved(pose):
    m = trimesh.load(BODY + f'pose-{pose.lower()}.glb').to_geometry()
    m = trimesh.Trimesh(m.vertices, m.faces, process=False); m.merge_vertices(digits_vertex=5)
    v = np.asarray(m.vertices).copy(); lab = limb(v)
    dz = sum(a * np.exp(-((v[:, 1] - c) / s) ** 2) for a, c, s in (LUMBAR, BLADE, GLUTE))
    w = np.clip(-v[:, 2] / 0.06, 0, 1) * (lab == 0) * np.clip((0.19 - np.abs(v[:, 0])) / 0.04, 0, 1)   # back of the torso only
    v[:, 2] += dz * w
    out = trimesh.Trimesh(v, m.faces, process=False); out.visual = material()
    return out


def ring(pts, c, k, turn=np.pi / 2):
    a = np.arctan2(pts[:, 2] - c[2], pts[:, 0] - c[0]); r = np.hypot(pts[:, 0] - c[0], pts[:, 2] - c[2])
    ang = turn + np.arange(k) * 2 * np.pi / k; rr = np.full(k, np.nan)
    for i, t in enumerate(ang):
        s = np.abs((a - t + np.pi) % (2 * np.pi) - np.pi) < np.pi / k
        if s.sum(): rr[i] = np.percentile(r[s], 92)
    ok = ~np.isnan(rr); rr = np.interp(np.arange(k), np.flatnonzero(ok), rr[ok], period=k)
    return np.c_[c[0] + rr * np.cos(ang), np.full(k, c[1]), c[2] + rr * np.sin(ang)]


def part(v, sel, heights, k, band=0.02, top=None, base=None, center=None):
    """Tube of rings with k sides; sel is a mask or a function of the height. top and base close it with a point
    ('flat': the middle of the ring)."""
    rings = []
    for y in heights:
        p = v[(sel(y) if callable(sel) else sel) & (np.abs(v[:, 1] - y) < band)]
        rings.append(ring(p, np.r_[p[:, 0].mean() if center is None else center, y, p[:, 2].mean()], k))
    V = np.vstack(rings); F = []
    for i in range(len(rings) - 1):
        for j in range(k):
            a, b = i * k + j, i * k + (j + 1) % k; c, d = a + k, b + k
            F += [(a, c, b), (b, c, d)]
    for tip, i, sign in ((base, 0, 1), (top, len(rings) - 1, -1)):
        if tip is None: continue
        if isinstance(tip, str): tip = rings[i].mean(0)
        V = np.vstack([V, tip]); ti = len(V) - 1
        for j in range(k):
            a, b = i * k + j, i * k + (j + 1) % k
            F.append((a, b, ti) if sign > 0 else (b, a, ti))
    t = trimesh.Trimesh(V, F, process=False); t.fix_normals()
    return t


def lowpoly(dense):
    v = np.asarray(dense.vertices); lab = limb(v); parts = []
    torso = lab == 0
    # torso: from the hip to the shoulder, which slopes down to the base of the neck
    neck = lambda y: torso & (np.abs(v[:, 0]) < (0.16 if y < 1.55 else 0.07))
    torso_ring = lambda y: (torso & (np.abs(v[:, 0]) < 0.30)) if y < 1.52 else neck(y)
    t = part(v, torso_ring, [0.82, 0.90, 0.98, 1.06, 1.14, 1.22, 1.30, 1.36, 1.41, 1.45, 1.49, 1.52, 1.545, 1.57], 12, base=[0, 0.78, 0.0], top='flat', center=0.0)
    # sloped shoulder: the upper rings come down to the top surface of the body's shoulder
    up = v[torso & (v[:, 1] > 1.36)]; kd = cKDTree(up[:, [0, 2]])
    tv = t.vertices.copy()
    for i in np.flatnonzero(tv[:, 1] > 1.40):
        near = kd.query_ball_point(tv[i, [0, 2]], 0.03)
        if near: tv[i, 1] = min(tv[i, 1], up[near, 1].max() + 0.004)
    parts.append(trimesh.Trimesh(tv, t.faces, process=False))
    yh = v[:, 1].max(); head = torso & (np.abs(v[:, 0]) < 0.09)
    parts.append(part(v, head, [1.56, 1.60, 1.645, 1.69, 1.735, 1.775, 1.805], 8, top=[0.0, yh, v[v[:, 1] > yh - .02, 2].mean()]))
    # arms: from the shoulder to the wrist, flat hand down to the fingertips
    for m in (1, 2):
        s = lab == m; ys = v[s, 1]; lo = ys.min()
        parts.append(part(v, s, [lo + 0.025, 0.725, 0.765, 0.80, 0.86, 0.93, 1.00, 1.04, 1.10, 1.17, 1.24, 1.28], 8, base=v[s][ys < lo + 0.01].mean(0), top='flat'))
    # legs: from the foot (toe forward) up into the hip
    for m in (3, 4):
        sg = 1 if m == 3 else -1
        side = lambda y, m=m, sg=sg: ((lab == m) | ((lab == 0) & (y > 0.76))) & (v[:, 0] * sg > 0.0)
        parts.append(part(v, side, [0.012, 0.05, 0.09, 0.13, 0.22, 0.32, 0.42, 0.48, 0.54, 0.64, 0.74, 0.84, 0.90], 8, base=v[(lab == m) & (v[:, 1] < .015)].mean(0)))
    out = trimesh.util.concatenate(parts); out.merge_vertices(); out.visual = material()
    return out


def build(pose, dense_path, low_path):
    d = curved(pose); d.export(dense_path)
    low = lowpoly(d); low.export(low_path)
    return len(low.faces)


if __name__ == '__main__':
    print('low-poly triangles:', build(*sys.argv[1:4]))
