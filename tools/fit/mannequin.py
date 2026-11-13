"""The engine's mannequin, derived from the site's body: a curved back, then a low-poly body.

Every garment showed a straight back because the mannequin's back is straight: it varies by less than 2 cm between
glute, lumbar and shoulder blade. curved() pulls the lumbar in and pushes the shoulder blade and the glute out on
the dense body. joined() fits rings to that body as on a PS1 character (torso with 12 sides, head, arms and legs
with 8, sloped shoulder, flat hand, foot), with torso and arm in one mesh from the shoulder to the armpit: with the
arm as a part pushed into the torso, a sleeve came out as a block beside the garment's torso, with a step at the
shoulder. rounded() rounds the tip of the shoulder. All are derived, never stored: engine.py builds them from
site/assets/body/pose-b.glb and pose-c.glb on every run, so they cannot drift from the body. measures() and check()
hold the mannequin to the recorded one: its measures and its shape, surface against surface (mannequin.json).
usage: python3 tools/fit/mannequin.py B|C DENSE_OUT.glb LOWPOLY_OUT.glb
       python3 tools/fit/mannequin.py --record WORK   (rewrites mannequin.json from the bodies engine.py built in WORK)"""
import sys, os, json, numpy as np, trimesh
from scipy.spatial import cKDTree, ConvexHull
from landmarks import limb
from paths import BODY

# (shift in z, height, spread) in meters. The lumbar goes in by 0.8 cm only: at 3 cm the back curved but the waist
# read as too thin (girth at 1.06 m: 68.0 cm on the site's body, 63.5 with 3 cm, 66.7 with 0.8)
LUMBAR, BLADE, GLUTE = (.008, 1.05, .08), (-.022, 1.36, .07), (-.02, .88, .06)
GREY = [235, 235, 240, 255]
SHOULDER_X = .175      # m: above the armpit the torso's part ends here
ARM_UP = (1.30, 1.36)  # m: rings of the arm above the armpit, before it bends over the shoulder
POINT, OVER = .012, .004   # m: past the body's skin on the shoulder; past the shoulder of the mannequin in parts
ROUND = 3              # passes of smoothing on the tip of the shoulder
MIRROR = np.array([-1, 1, 1.0])
WAIST_Y = 1.06
# the shape itself: every vertex and face of the low-poly body, per pose, recorded in mannequin.json. A body whose
# surface lies further than this from the recorded one's, either way, is another mannequin (a rounder shoulder, wider legs, a chest
# further out), whatever the measures below say
RECORD = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'mannequin.json')
SHAPE = 1.0            # mm
# what check() holds, in both poses
APPROVED = {
    'point_cm': 1.7,
    'waist_cm': 70.8,
    'shoulder_width_cm': 47.5,
    'overhang_cm2': 31,
    'triangles': 1316,
}


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


def in_parts(dense):
    """The mannequin as separate parts pushed into one another. Its shoulder is the contour joined() keeps."""
    v = np.asarray(dense.vertices); lab = limb(v); parts = []
    torso = lab == 0
    # torso: from the hip to the shoulder, which slopes down to the base of the neck
    neck = lambda y: torso & (np.abs(v[:, 0]) < (0.16 if y < 1.55 else 0.07))
    # above the armpit the torso stops at the shoulder; the deltoid goes with the arm (a torso that swallowed it made a
    # flap over the arm)
    torso_ring = lambda y: (torso & (np.abs(v[:, 0]) < (0.30 if y < 1.30 else SHOULDER_X))) if y < 1.52 else neck(y)
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
    # arms: from the shoulder (deltoid included) to the wrist, flat hand down to the fingertips
    for m in (1, 2):
        s = lab == m; ys = v[s, 1]; lo = ys.min(); sg = 1 if m == 1 else -1; tip = v[s][ys < lo + 0.01].mean(0)
        s = s | (torso & (v[:, 0] * sg > SHOULDER_X - 0.01) & (v[:, 1] < 1.52))       # the arm goes up to the shoulder
        col = s & (np.abs(v[:, 1] - 1.40) < 0.06); cx = np.median(v[col, 0]); cz = np.median(v[col, 2])
        yt = v[torso & (np.abs(v[:, 0] - cx) < 0.025) & (np.abs(v[:, 2] - cz) < 0.04), 1].max()
        parts.append(part(v, s, [lo + 0.025, 0.725, 0.765, 0.80, 0.86, 0.93, 1.00, 1.04, 1.10, 1.17, 1.24, 1.30, 1.36, 1.41, yt - 0.035], 8, base=tip, top=[cx - sg * 0.02, yt - 0.012, cz]))
    # legs: from the foot (toe forward) up into the hip
    for m in (3, 4):
        sg = 1 if m == 3 else -1
        side = lambda y, m=m, sg=sg: ((lab == m) | ((lab == 0) & (y > 0.76))) & (v[:, 0] * sg > 0.0)
        parts.append(part(v, side, [0.012, 0.05, 0.09, 0.13, 0.22, 0.32, 0.42, 0.48, 0.54, 0.64, 0.74, 0.84, 0.90], 8, base=v[(lab == m) & (v[:, 1] < .015)].mean(0)))
    out = trimesh.util.concatenate(parts); out.merge_vertices(); out.visual = material()
    return out


def joined(dense, ref):
    """The approved mannequin: torso (12 sides) and arm (8 sides) are one mesh from the shoulder to the armpit, so
    a garment's shoulder runs into its sleeve over one surface. The arm's tube goes up to ARM_UP, bends inward over
    the shoulder in two leaning rings and meets a socket of 8 vertices of the torso. Head and legs are parts, as in
    in_parts(). The body is mirrored first (its right side), so both sides come out equal; no vertex of the shoulder
    leaves the body's skin by more than POINT nor the contour of ref (in_parts) by more than OVER."""
    v = np.asarray(dense.vertices); N = np.asarray(dense.vertex_normals)
    r_, l_ = v[:, 0] >= 0, v[:, 0] > 0; v = np.vstack([v[r_], v[l_] * MIRROR]); N = np.vstack([N[r_], N[l_] * MIRROR])
    lab = limb(v); torso = lab == 0; kd_body = cKDTree(v); V, F = [], []
    def rings(sel, heights, k, band=0.02, center=None):
        out = []
        for y in heights:
            p = v[(sel(y) if callable(sel) else sel) & (np.abs(v[:, 1] - y) < band)]
            out.append(ring(p, np.r_[p[:, 0].mean() if center is None else center, y, p[:, 2].mean()], k))
        return out
    def add(pts):
        i0 = sum(len(x) for x in V); V.append(np.atleast_2d(pts)); return np.arange(i0, i0 + len(V[-1]))
    def quad(a, b, c, d): F.extend([(a, b, c), (a, c, d)])
    def tube(ids):
        for A, B in zip(ids[:-1], ids[1:]):
            for j in range(len(A)): quad(A[j], A[(j + 1) % len(A)], B[(j + 1) % len(A)], B[j])
    def fan(loop, p):
        for j in range(len(loop)): F.append((loop[j], loop[(j + 1) % len(loop)], p))
    # torso: the arm's socket is on the rings at 1.38, 1.45 and 1.49
    sel_t = lambda y: torso & (np.abs(v[:, 0]) < (0.30 if y < 1.30 else SHOULDER_X if y < 1.52 else 0.16 if y < 1.55 else 0.07))
    RT = rings(sel_t, [0.82, 0.90, 0.98, 1.06, 1.14, 1.22, 1.30, 1.38, 1.45, 1.49, 1.52, 1.545, 1.57], 12, center=0.0)
    up = v[torso & (v[:, 1] > 1.36)]; kd = cKDTree(up[:, [0, 2]])
    for r in RT:                                         # sloped shoulder: down to the top surface of the body's shoulder
        for p in r:
            if p[1] > 1.40:
                near = kd.query_ball_point(p[[0, 2]], 0.03)
                if near: p[1] = min(p[1], up[near, 1].max() + 0.004)
    T = [add(r) for r in RT]; r6, r7, r8 = 7, 8, 9
    hole = {(r6, 8), (r6, 9), (r7, 8), (r7, 9), (r6, 2), (r6, 3), (r7, 2), (r7, 3)}       # (ring, column) of the quads the arm takes
    for i in range(len(T) - 1):
        for j in range(12):
            if (i, j) not in hole: quad(T[i][j], T[i][(j + 1) % 12], T[i + 1][(j + 1) % 12], T[i + 1][j])
    fan(T[0][::-1], add([0.0, 0.78, 0.0])[0]); fan(T[-1], add(np.vstack(V)[T[-1]].mean(0))[0])
    # head and neck
    yh = v[:, 1].max(); head = torso & (np.abs(v[:, 0]) < 0.09)
    C = [add(r) for r in rings(head, [1.56, 1.60, 1.645, 1.69, 1.735, 1.775, 1.805], 8)]
    tube(C); fan(C[-1], add([0.0, yh, v[v[:, 1] > yh - .02, 2].mean()])[0]); fan(C[0][::-1], add(np.vstack(V)[C[0]].mean(0))[0])
    # arms
    ang8 = np.pi / 2 + np.arange(8) * np.pi / 4
    def deltoid(A, S, sg, f):
        """A leaning ring between the top of the arm (level, f = 0) and the socket (upright, f = 1); its outer side
        goes out to the body's skin."""
        P = np.vstack(V); th = f * np.pi / 2; cA, cS = P[A].mean(0), P[S].mean(0); c = cA + (cS - cA) * f
        n = np.r_[-sg * np.sin(th), np.cos(th), 0.0]; e1 = np.r_[np.cos(th), sg * np.sin(th), 0.0]; z = np.r_[0, 0, 1.0]
        lin = P[A] + (P[S] - P[A]) * f; out = []; w = v - c; plane = np.abs(w @ n) < 0.012
        for i, a in enumerate(ang8):
            d = np.cos(a) * e1 + np.sin(a) * z; rl = max(np.linalg.norm(lin[i] - c), 0.02); r = rl
            if np.cos(a) * sg > -0.3:
                t = w @ d; lat = np.linalg.norm(w - np.outer(w @ n, n) - np.outer(t, d), axis=1)
                q = plane & (t > 0) & (lat < 0.6 * t * np.tan(np.pi / 8) + 0.01) & (t < 0.14)
                if q.sum() > 5: r = np.clip(np.percentile(t[q], 97), rl, 2.0 * rl)
            out.append(c + d * r)
        return add(np.array(out))
    for m, sg in ((1, 1), (2, -1)):
        s = lab == m; ys = v[s, 1]; lo = ys.min(); tip = v[s][ys < lo + 0.01].mean(0)
        sa = s | (torso & (v[:, 0] * sg > SHOULDER_X - 0.01) & (v[:, 1] < 1.52))
        A = [add(r) for r in rings(sa, [lo + 0.025, 0.725, 0.765, 0.80, 0.86, 0.93, 1.00, 1.04, 1.10, 1.17, 1.24] + list(ARM_UP), 8)]
        tube(A); fan(A[0][::-1], add(tip)[0])
        # side of the arm's ring (angle 90 + 45 i) -> (ring, column) of the socket (angle 90 + 30 j)
        if sg > 0: to = {6: (r8, 9), 7: (r8, 10), 0: (r7, 10), 1: (r6, 10), 2: (r6, 9), 3: (r6, 8), 4: (r7, 8), 5: (r8, 8)}
        else: to = {2: (r8, 3), 1: (r8, 2), 0: (r7, 2), 7: (r6, 2), 6: (r6, 3), 5: (r6, 4), 4: (r7, 4), 3: (r8, 4)}
        S = np.array([T[to[i][0]][to[i][1]] for i in range(8)])
        tube([A[-1], deltoid(A[-1], S, sg, 1 / 3), deltoid(A[-1], S, sg, 2 / 3), S])
    # legs: from the foot up into the hip
    for m, sg in ((3, 1), (4, -1)):
        side = lambda y, sg=sg, m=m: ((lab == m) | ((lab == 0) & (y > 0.76))) & (v[:, 0] * sg > 0.0)
        L = [add(r) for r in rings(side, [0.012, 0.05, 0.09, 0.13, 0.22, 0.32, 0.42, 0.48, 0.54, 0.64, 0.74, 0.84, 0.90], 8)]
        tube(L); fan(L[0][::-1], add(v[(lab == m) & (v[:, 1] < .015)].mean(0))[0]); fan(L[-1], add(np.vstack(V)[L[-1]].mean(0))[0])
    # no point at the junction of arm and torso: on the shoulder and the shoulder blade nothing leaves the body's skin by more than POINT
    P = np.vstack(V); zone = (P[:, 1] > 1.15) & (P[:, 1] < 1.55) & (np.abs(P[:, 0]) > 0.08)
    _, j = kd_body.query(P[zone]); out = ((P[zone] - v[j]) * N[j]).sum(1); mv = out > POINT; idx = np.flatnonzero(zone)[mv]
    P[idx] = v[j[mv]] + N[j[mv]] * POINT
    # the shoulder stays inside the contour of the mannequin in parts (no trapezius of the body over the shoulder)
    zone = np.flatnonzero((P[:, 1] > 1.24) & (np.abs(P[:, 0]) > 0.05)); inside = np.zeros(len(zone), bool)
    for c in ref.split(only_watertight=False):
        if c.is_watertight: inside |= c.contains(P[zone])
    cp, dist, _ = trimesh.proximity.closest_point(ref, P[zone]); mv = ~inside & (dist > OVER); idx = zone[mv]
    P[idx] = cp[mv] + (P[idx] - cp[mv]) / dist[mv, None] * OVER
    F = np.array(F); used = np.unique(F); new = -np.ones(len(P), int); new[used] = np.arange(len(used))
    out = trimesh.Trimesh(P[used], new[F], process=False); trimesh.repair.fix_winding(out); out.fix_normals(); out.merge_vertices()
    return trimesh.util.concatenate([c for c in out.split(only_watertight=False) if len(c.faces) > 10])


def rounded(m, passes):
    """Rounds the tip of the shoulder: Taubin smoothing (it does not shrink) on the shoulder's vertices only, each
    averaged with its mirrored pair so both sides stay equal."""
    v = np.asarray(m.vertices).copy(); sel = (v[:, 1] > 1.30) & (v[:, 1] < 1.56) & (np.abs(v[:, 0]) > 0.14); nb = m.vertex_neighbors
    _, pair = cKDTree(v).query(v * MIRROR); assert (pair[pair] == np.arange(len(v))).all(), 'a vertex without its mirrored pair'
    even = lambda x: (x + x[pair] * MIRROR) / 2
    v = even(v)
    for _ in range(passes):
        for lam in (0.5, -0.53):
            lap = np.array([v[n].mean(0) - v[i] if n else 0 * v[i] for i, n in enumerate(nb)]); v[sel] += lam * lap[sel]
    out = trimesh.Trimesh(even(v), m.faces, process=False); out.visual = material()
    return out


def shape_mm(low, pose):
    """Furthest the surface of the body lies from the recorded body's, either way, in mm: every vertex and every
    middle of a triangle of one against the surface of the other. It reads the surface, not the list of faces: two
    machines may split the same quad along the other diagonal or list the same triangles in another order."""
    r = json.load(open(RECORD))[pose]; rec = trimesh.Trimesh(np.array(r['v']), np.array(r['f']), process=False)
    far = lambda a, b: float(trimesh.proximity.closest_point(b, np.vstack([a.vertices, a.triangles_center]))[1].max())
    return round(1e3 * max(far(low, rec), far(rec, low)), 2)


def record(work):
    """Rewrites mannequin.json from WORK/low-B.glb and low-C.glb: per pose, the vertices as the GLB holds them (32-bit
    floats, written so that they read back the same) and the faces, one pose per line."""
    out = {}
    for p in 'BC':
        m = trimesh.load(f'{work}/low-{p}.glb', force='mesh', process=False)
        out[p] = {'v': [[float(str(x)) for x in row] for row in np.asarray(m.vertices, np.float32)], 'f': np.asarray(m.faces).tolist()}
    open(RECORD, 'w').write('{\n' + ',\n'.join(f' "{p}": {json.dumps(v, separators=(",", ":"))}' for p, v in out.items()) + '\n}\n')


def measures(low, dense, pose=None):
    """What was approved in the mannequin, read on the low-poly body against the dense one."""
    v = np.asarray(low.vertices); d = np.asarray(dense.vertices); N = np.asarray(dense.vertex_normals)
    far, _ = cKDTree(v).query(v * MIRROR)
    zone = (v[:, 1] > 1.15) & (v[:, 1] < 1.55) & (np.abs(v[:, 0]) > 0.08); _, j = cKDTree(d).query(v[zone])
    cut = lambda y: np.asarray(low.section(plane_origin=[0, y, 0], plane_normal=[0, 1, 0]).vertices)
    w = cut(WAIST_Y)[:, [0, 2]]; w = w[np.abs(w[:, 0]) < 0.16]
    c, n = low.triangles_center, low.face_normals; under = (np.abs(c[:, 0]) > 0.15) & (c[:, 1] > 1.25) & (c[:, 1] < 1.50) & (n[:, 1] < -0.6)
    return {'asymmetry_cm': round(100 * float(far.max()), 2), 'point_cm': round(100 * float(((v[zone] - d[j]) * N[j]).sum(1).max()), 2),
            'waist_cm': round(100 * float(ConvexHull(w).area), 1), 'shoulder_width_cm': round(200 * float(np.abs(cut(1.42)[:, 0]).max()), 1),
            'overhang_cm2': round(1e4 * float(low.area_faces[under].sum())), 'triangles': int(len(low.faces)), 'closed': bool(low.is_watertight),
            **({'shape_mm': shape_mm(low, pose)} if pose else {})}


def check(rep):
    """The mannequin is the approved one: both sides equal, no point on the shoulder past the body's skin, the
    shoulder's width and the waist's girth as approved, no overhang of the torso over the arm past the approved one."""
    return [f'pose {p}: {x}' for p, m in rep['mannequin'].items() for x in differs(m)]


def differs(m):
    a = APPROVED; bad = []
    if m['asymmetry_cm'] > 0: bad.append(f"sides differ by {m['asymmetry_cm']} cm")
    if m['point_cm'] > a['point_cm']: bad.append(f"a vertex of the shoulder {m['point_cm']} cm past the skin, limit {a['point_cm']}")
    if m['overhang_cm2'] > a['overhang_cm2']: bad.append(f"overhang {m['overhang_cm2']} cm2, approved {a['overhang_cm2']}")
    for k in ('waist_cm', 'shoulder_width_cm'):
        if abs(m[k] - a[k]) > 0.5: bad.append(f'{k} {m[k]}, approved {a[k]}')
    if m.get('shape_mm', 0) > SHAPE: bad.append(f"the surface {m['shape_mm']} mm from the recorded shape, limit {SHAPE}")
    if m['triangles'] != a['triangles'] or not m['closed']: bad.append(f"{m['triangles']} triangles, closed {m['closed']}; approved {a['triangles']}, closed")
    return bad


def build(pose, dense_path, low_path):
    """Writes the dense and the low-poly body of a pose. Returns the low-poly body's triangles and how far it was
    built from the recorded one, in mm. Two processors do not round alike, and a low-poly body a hundredth of a
    millimetre apart, or with the same surface cut into other triangles, gave every garment another mesh on the other
    machine (the loose hoods past their baselines): a body built within SHAPE of the recorded one is written as the
    recorded one, vertices and faces, the same on every machine. One built further is written as built, and check()
    fails it."""
    d = curved(pose); d.export(dense_path)
    low = rounded(joined(d, in_parts(d)), ROUND); built = shape_mm(low, pose)
    if built <= SHAPE:
        r = json.load(open(RECORD))[pose]; low = trimesh.Trimesh(np.array(r['v']), np.array(r['f']), process=False); low.visual = material()
    low.export(low_path)
    return len(low.faces), built


if __name__ == '__main__':
    if sys.argv[1] == '--record': record(sys.argv[2])
    else: print('low-poly triangles, mm from the recorded shape:', *build(*sys.argv[1:4]))
