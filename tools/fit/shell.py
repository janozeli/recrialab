"""A garment as a displaced skin of the low-poly mannequin (the part of a garment that wears the body).

For each vertex of the low-poly mannequin, a ray along the normal looks for the generated garment. Where it finds
it, the vertex is covered and displaced out to the garment, between a minimum and a maximum clearance. The shell
inherits the mannequin's topology: the body cannot poke through it, it is never smaller than the body and it opens
no gap. The texture is baked from the generated garment, one ray per texel.

Two rules of the fit engine sit on top (engine.py):
- bottom: the upper cut follows the garment's own waistband around the body (edge), with its lowest point on the
  waistband line of register.py; a top's hem follows the garment's hem the same way. A level cut fits and no longer
  looks like the garment;
- top: it hangs (drape): cloth runs straight between the points that hold it out and does not follow the body
  into the lumbar or the waist;
- top: it stays outside the set of ALL the bottoms (the envelope) plus RISE, not outside one of them, so any top
  layers over any bottom without a table per pair.
What hangs loose (skirt below the hip, hem below it, hood) is not shell: tube.py and loose_hood.py.
usage: python3 tools/fit/shell.py bottom|top NNN GARMENT.glb DENSE_BODY.glb LOWPOLY.glb OUT_DIR
       (a bottom writes OUT_DIR/env/NNN.npy; a top reads every one of them)"""
import sys, os, io, json, glob, struct, numpy as np, trimesh, xatlas
from scipy.spatial import cKDTree
from scipy import ndimage
from PIL import Image
import landmarks as L
import register as R

MIN_CLEAR = 0.006      # m: the shell is never closer than this to the body
BACK_OFF = 0.03        # m: the ray starts this far inside the body, to catch cloth that sank into it
WALL = 0.015           # m: thickest double wall (lining + outer face) of a generated garment
TEX = 512              # px: side of the baked texture
NEAR_PART = 0.05       # m: a top clears the bottoms' surface on every part of the mannequin within this distance
PART_RISE = 0.012      # m: ... and by this much, since facets of two parts do not line up between their rings
RISE = 0.004           # m: a top stays this far outside the envelope of the bottoms
DEEP = 0.08            # m: second try of a texture ray that found nothing, starting this far inside the body
# the print is read only from faces seen from outside: the inside of a generated garment (lining, the far side of a
# fold, the wall seen through an opening) is painted one flat colour, and a ray that stopped there left a solid patch
# (shorts 008: grey shards over a fifth of the garment). FIT_TEXTURE_OUTER=0 bakes as before, to compare
TEXTURE_OUTER = os.environ.get('FIT_TEXTURE_OUTER', '1') == '1'
# m: for the print, how far past the first outward face the outer face is looked for on the torso. Jersey 030 carries
# a grey inner layer facing outward (what was left of the generator's mannequin) 2 to 3 cm behind the cloth: with WALL
# the ray stopped on it and the front hem came out as a grey patch
TEXTURE_WALL = 0.035
LIMB_WALL = 0.04       # m: on a limb the outer face is looked for over folds this deep
LIMB_BLEND = 0.04      # m: width of the blend between torso rays and limb rays in the texture bake
EDGE_SECTORS = 24      # sectors around the body in which a waistband's or a hem's height is read
WAIST_DIP = 0.0        # m: the lowest point of a waistband's curve sits this far under the waistband line; the curve rises from there
WAIST_TOP = 0.01       # m: ... up to this far under the waist
TORSO_IN = 0.08        # m: half width of the torso that is inside every top; a sleeve's inner wall is further out than this
IN_ARM = 0.003         # m: cloth this deep under the skin of an arm cuts through the arm
ISLAND = 8             # vertices: a bare patch of the mannequin up to this size, with cloth all around, is covered
BURIED = .03           # m: a vertex of the mannequin this far from the body's skin is the middle of a lid
SHOULDER_HOLDS = 1.34  # m: above this the mannequin's shoulder is one of the points a top hangs from
SHOULDER_OUT, SHOULDER_TOP = .18, 1.52   # m: beyond this |x| and below this height the mannequin's shoulder is its arm, bent over it
ARMHOLE = 0.10         # m: under the armpit, the height over which a top's side goes from hanging off the armpit to hanging off the shoulder
SLIVER = 0.02          # m: a top's hem that ends less than this far over the waistband line comes down to just under it
HEM_RISE = 0.02        # m: the hem of a top that reaches its line rises at most this far over it (WAIST_DIP + HEM_RISE < register.OVERLAP)
DRAPE_TO, DRAPE_COLUMNS = 1.43, 12   # a top hangs from this height down; columns around the torso (the mannequin's torso has 12 sides)
HEM_TO = 1.25          # m: a top's hem is looked for on the torso below this height
WAIST_FROM = 0.06      # m above the crotch from where a bottom's torso is cut at the waistband line


def ceiling(pid):
    """Maximum clearance (torso, limb) in meters: bottoms hug the hip, knits are loose, jackets looser. A safety
    bound, not the fit: under it the shell takes the clearance the garment has."""
    n = int(pid)
    return (.03, .03) if n <= 15 else (.12, .06) if n <= 32 else (.14, .08)


def load_body(path):
    m = trimesh.load(path).to_geometry()
    m = trimesh.Trimesh(m.vertices, m.faces, process=False)
    m.merge_vertices(digits_vertex=5)
    return m


def Low(path):
    m = trimesh.load(path, process=False).to_geometry()
    return trimesh.Trimesh(m.vertices, m.faces, process=False)


def load_glb(path):
    """trimesh.load that tolerates an orphan accessor running past its bufferView (011 has one; three.js ignores it)."""
    try:
        return trimesh.load(path)
    except ValueError:
        b = open(path, 'rb').read(); n = struct.unpack('<I', b[12:16])[0]; j = json.loads(b[20:20 + n])
        used = {i for m in j['meshes'] for p in m['primitives'] for i in [*p['attributes'].values(), p.get('indices')] if i is not None}
        size = {5120: 1, 5121: 1, 5122: 2, 5123: 2, 5125: 4, 5126: 4}; comp = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}
        for i, a in enumerate(j['accessors']):
            bv = j['bufferViews'][a['bufferView']]
            end = a.get('byteOffset', 0) + a['count'] * size[a['componentType']] * comp[a['type']]
            if i not in used and end > bv['byteLength']: a['count'] = 0; a.pop('max', None); a.pop('min', None)
        js = json.dumps(j).encode(); js += b' ' * (-len(js) % 4)
        rest = b[20 + n:]
        glb = b[:8] + struct.pack('<I', 12 + 8 + len(js) + len(rest)) + struct.pack('<I', len(js)) + b'JSON' + js + rest
        return trimesh.load(io.BytesIO(glb), file_type='glb')


class Piece:
    """A generated garment: its meshes as one, with uv and texture per triangle, and rays."""
    def __init__(self, path):
        scene = load_glb(path)
        vs, fs, uvs, self.img, self.face_img = [], [], [], [], []
        off = 0
        for node in scene.graph.nodes_geometry:
            T, gname = scene.graph[node]
            g = scene.geometry[gname]
            v = trimesh.transform_points(g.vertices, T)
            vs.append(v); fs.append(g.faces + off); off += len(v)
            uvs.append(g.visual.uv if getattr(g.visual, 'uv', None) is not None else np.zeros((len(v), 2)))
            mat = g.visual.material
            img = getattr(mat, 'baseColorTexture', None) or getattr(mat, 'image', None)
            color = getattr(mat, 'baseColorFactor', None)
            if img is None:
                c = (np.array(color[:3]) if color is not None else np.array([200, 200, 200])).astype(np.uint8)
                img = Image.fromarray(np.full((4, 4, 3), c, np.uint8))
            self.img.append(np.asarray(img.convert('RGB'), np.float32))
            self.face_img.append(np.full(len(g.faces), len(self.img) - 1))
        self.v = np.vstack(vs); self.f = np.vstack(fs); self.uv = np.vstack(uvs); self.face_img = np.concatenate(self.face_img)
        self.mesh = trimesh.Trimesh(self.v, self.f, process=False)
        self.ray = trimesh.ray.ray_pyembree.RayMeshIntersector(self.mesh)
        self.sample_p, self.sample_f = trimesh.sample.sample_surface(self.mesh, 150000, seed=1)
        self.sample_n = self.mesh.face_normals[self.sample_f]; self.sample_kd = cKDTree(self.sample_p)

    def color(self, tri, pts):
        """Texture color at the points pts of the triangles tri (bilinear)."""
        b = trimesh.triangles.points_to_barycentric(self.v[self.f[tri]], pts)
        uv = np.einsum('ij,ijk->ik', b, self.uv[self.f[tri]])
        out = np.zeros((len(tri), 3), np.float32)
        for k, img in enumerate(self.img):
            s = self.face_img[tri] == k
            if not s.any(): continue
            h, w = img.shape[:2]
            x = (uv[s, 0] % 1) * (w - 1); y = (1 - uv[s, 1] % 1) * (h - 1)
            x0 = np.floor(x).astype(int); y0 = np.floor(y).astype(int); x1 = np.minimum(x0 + 1, w - 1); y1 = np.minimum(y0 + 1, h - 1)
            fx = (x - x0)[:, None]; fy = (y - y0)[:, None]
            out[s] = (img[y0, x0] * (1 - fx) + img[y0, x1] * fx) * (1 - fy) + (img[y1, x0] * (1 - fx) + img[y1, x1] * fx) * fy
        return out


def probe(piece, body_kd, body_v, p, n, reach, outer=False):
    """For each body point p with normal n: distance (from the body surface) to the outer face of the garment, and
    the triangle and point hit. nan where the garment does not cover."""
    o = p - n * BACK_OFF
    loc, ir, it = piece.ray.intersects_location(o, n, multiple_hits=True)
    t = np.einsum('ij,ij->i', loc - o[ir], n[ir]) - BACK_OFF
    ok = t < reach
    if outer: ok &= np.einsum('ij,ij->i', piece.mesh.face_normals[it], n[ir]) > 0   # for the print: only faces seen from outside (TEXTURE_OUTER)
    # the point hit must be cloth that wears THIS part of the body: the body nearest to it is near p
    _, near = body_kd.query(loc)
    ok &= np.linalg.norm(body_v[near] - p[ir], axis=1) < np.maximum(0.03, 1.2 * np.abs(t) + 0.015)
    loc, ir, it, t = loc[ok], ir[ok], it[ok], t[ok]
    d = np.full(len(p), np.nan); tri = np.full(len(p), -1); pt = np.zeros((len(p), 3))
    if len(ir) == 0: return d, tri, pt
    order = np.lexsort((t, ir)); ir, it, t, loc = ir[order], it[order], t[order], loc[order]
    start = np.r_[0, np.flatnonzero(np.diff(ir)) + 1]; first = np.repeat(t[start], np.diff(np.r_[start, len(ir)]))
    inside = t <= first + WALL                       # same wall (lining + outer face)
    last = np.zeros(len(ir), bool)
    idx = np.flatnonzero(inside); end = np.r_[np.flatnonzero(np.diff(ir[idx])), len(idx) - 1]
    last[idx[end]] = True
    d[ir[last]] = t[last]; tri[ir[last]] = it[last]; pt[ir[last]] = loc[last]
    return d, tri, pt


def axes(v):
    """Center of each limb per 2 cm slice: {label: (heights, centers)}."""
    lab = L.limb(v); out = {}
    for m in (1, 2, 3, 4):
        s = lab == m; ys = np.floor(v[s, 1] / 0.02).astype(int); ks = np.unique(ys)
        out[m] = (ks * 0.02 + 0.01, np.array([v[s][ys == k].mean(0) for k in ks]))
    return out


def limb_weight(p):
    """0 on the torso, 1 well inside an arm or a leg, smooth in between: the texture rays turn from the body's normal
    to the limb's radius little by little. A hard switch at the limb's border tears the print along it (the side of
    the back, the armpit)."""
    step = lambda x: np.clip(x, 0, 1) ** 2 * (3 - 2 * np.clip(x, 0, 1))
    arm = step((np.abs(p[:, 0]) - L.ARM_X) / LIMB_BLEND) * step((L.ARM_TOP - p[:, 1]) / LIMB_BLEND)
    return np.maximum(arm, step((L.LEG_TOP - p[:, 1]) / LIMB_BLEND) * (arm == 0))


def probe_blend(piece, ax, base, nor, reach, back_off=BACK_OFF):
    """Triangle and point of the garment for each texel: one ray per texel, along the body's normal on the torso and
    from the limb's axis through the point on arms and legs, blended by limb_weight. It finds the sleeve wall even
    where the sleeve cuts through the arm, with no jump between the two."""
    lab = L.limb(base); w = limb_weight(base) * (lab > 0); rad = nor.copy(); dist = np.full(len(base), back_off)
    for m in (1, 2, 3, 4):
        i = np.flatnonzero(lab == m)
        if not len(i) or m not in ax: continue
        yk, ck = ax[m]
        c = np.c_[np.interp(base[i, 1], yk, ck[:, 0]), base[i, 1], np.interp(base[i, 1], yk, ck[:, 2])]
        r = base[i] - c; dist[i] = np.linalg.norm(r, axis=1); rad[i] = r / (dist[i][:, None] + 1e-9)
    d = (1 - w)[:, None] * nor + w[:, None] * rad; d /= np.linalg.norm(d, axis=1)[:, None] + 1e-9
    back = (1 - w) * back_off + w * dist; wall = (1 - w) * TEXTURE_WALL + w * LIMB_WALL
    o = base - d * back[:, None]
    loc, ir, it = piece.ray.intersects_location(o, d, multiple_hits=True)
    tri = np.full(len(base), -1); pt = np.zeros((len(base), 3))
    if not len(ir): return tri, pt
    t = np.einsum('ij,ij->i', loc - o[ir], d[ir]) - back[ir]; ok = t < reach
    if TEXTURE_OUTER: ok &= np.einsum('ij,ij->i', piece.mesh.face_normals[it], d[ir]) > 0
    loc, ir, it, t = loc[ok], ir[ok], it[ok], t[ok]
    if not len(ir): return tri, pt
    order = np.lexsort((t, ir)); ir, it, t, loc = ir[order], it[order], t[order], loc[order]
    start = np.r_[0, np.flatnonzero(np.diff(ir)) + 1]; first = np.repeat(t[start], np.diff(np.r_[start, len(ir)]))
    idx = np.flatnonzero(t <= first + wall[ir]); end = idx[np.r_[np.flatnonzero(np.diff(ir[idx])), len(idx) - 1]]   # outer face, over lining and folds
    tri[ir[end]] = it[end]; pt[ir[end]] = loc[end]
    return tri, pt


def smooth(value, adj, it):
    x = value.copy()
    for _ in range(it):
        x = np.array([x[a].mean() if len(a) else x[i] for i, a in enumerate(adj)])
    return x


def cone(n, degrees=45, k=8):
    """The normal and k directions tilted around it."""
    t = np.cross(n, [0, 1, 0]); bad = np.linalg.norm(t, axis=1) < 1e-3; t[bad] = np.cross(n[bad], [1, 0, 0])
    t /= np.linalg.norm(t, axis=1)[:, None]; b = np.cross(n, t)
    c, s = np.cos(np.radians(degrees)), np.sin(np.radians(degrees))
    return [n] + [c * n + s * (np.cos(a) * t + np.sin(a) * b) for a in np.arange(k) * 2 * np.pi / k]


def coverage(piece, dense, radius, kind):
    """Covered or not at each vertex of the dense body: the garment blocks most of a cone of rays leaving the
    vertex (it holds for a wide sleeve and for cloth bridging the armpit). Arms and legs vote per ring."""
    v, n = np.asarray(dense.vertices), np.asarray(dense.vertex_normals)
    blocked = np.zeros(len(v))
    dirs = cone(n)
    for d in dirs:
        o = v - d * BACK_OFF
        loc, ir, _ = piece.ray.intersects_location(o, d, multiple_hits=False)
        blocked[ir[np.linalg.norm(loc - o[ir], axis=1) < radius + BACK_OFF]] += 1
    cov = blocked / len(dirs) >= 0.5
    # closes small holes of the generated mesh and drops islands: majority among the neighbors
    adj = dense.vertex_neighbors
    for _ in range(6):
        cov = np.array([(cov[a].mean() if len(a) else cov[i]) > 0.5 for i, a in enumerate(adj)])
    lab = L.limb(v)
    ys = np.floor(v[:, 1] / 0.02).astype(int)
    for m in (1, 2, 3, 4):
        s = lab == m
        sign = 1 if m in (1, 3) else -1
        outer = s & (n[:, 0] * sign > -0.2)             # not facing the torso or the other leg
        rings = {}; side = set()
        for y in np.unique(ys[s]):
            ring = s & (ys == y); vote = np.flatnonzero(outer & (ys == y))
            if len(vote) < 3: continue
            # rays from the limb axis outward: they hold even where the generated sleeve runs inside the arm
            c = v[ring].mean(0); r = v[vote] - c; dist = np.linalg.norm(r, axis=1); r /= dist[:, None]
            loc, ir, _ = piece.ray.intersects_location(np.repeat(c[None], len(vote), 0), r, multiple_hits=False)
            hit = np.linalg.norm(loc - c, axis=1)
            rings[y] = (hit < dist[ir] + radius).sum() / len(vote) > 0.5
            # an arm that hangs through the side of a top that is wide or sits off centre has cloth around it too, and
            # it is the body of the top, not a sleeve: most of that cloth cuts through the arm, and no wall stands
            # between the arm and the torso. The ring wears nothing (a polo's short sleeve went on down to the elbow,
            # painted with the top's lining). One ring like it alone is a fold of a sleeve
            if rings[y] and kind == 'top' and m in (1, 2) and (hit < dist[ir] - IN_ARM).sum() / len(vote) > 0.5:
                loc, _, _ = piece.ray.intersects_location(c[None], np.array([[-sign, 0., 0.]]), multiple_hits=True)
                if not (loc[:, 0] * sign > TORSO_IN).any(): side.add(y)
        for y in side:
            if y + 1 in side or y - 1 in side: rings[y] = False
        # a sleeve or a pant leg covers from the shoulder or hip down to its end: the lowest covered ring (with a
        # covered neighbor right above) closes every ring above it
        keys = sorted(rings)
        end = next((y for y in keys if rings[y] and rings.get(y + 1, True)), None)
        if kind == 'top' and m in (3, 4): end = None
        for y in keys:
            cov[s & (ys == y)] = end is not None and y >= end
    # torso between crotch and armpit: straight hem and waistband, at the height where most of the ring changes
    torso = (lab == 0) & (v[:, 1] > 0.80) & (v[:, 1] < 1.25)
    keys = sorted(np.unique(ys[torso])); vote = {y: cov[torso & (ys == y)].mean() > 0.5 for y in keys}
    if kind == 'top':
        end = next((y for y in keys if vote[y] and vote.get(y + 1, True)), None)
        for y in keys: cov[torso & (ys == y)] = end is not None and y >= end
    else:
        end = next((y for y in reversed(keys) if vote[y] and vote.get(y - 1, True)), None)
        for y in keys: cov[torso & (ys == y)] = end is not None and y <= end
    return cov


def edge(S, center, q, v, sides=True):
    """Height of a garment's edge (percentile q of the points S per sector around center) at the angle of each
    vertex of v, smoothed around the body."""
    ang, h = L.sectors(S, center, EDGE_SECTORS, q)
    if sides is False:                                    # under the arms the torso's cloth is hidden by the sleeve: read front and back only
        ok = np.abs(np.sin(ang)) > .5; h = np.interp(ang, ang[ok], h[ok], period=2 * np.pi)
    for _ in range(2): h = np.convolve(np.r_[h[-1], h, h[0]], [.25, .5, .25], mode='valid')
    return np.interp(np.arctan2(v[:, 2] - center[1], v[:, 0] - center[0]), ang, h, period=2 * np.pi)


def hull(y, r):
    """Upper convex hull of r over y, read at each y: a string pulled tight over the points."""
    o = np.argsort(y); k = []
    for i in o:
        while len(k) > 1 and (r[k[-1]] - r[k[-2]]) * (y[i] - y[k[-2]]) <= (r[i] - r[k[-2]]) * (y[k[-1]] - y[k[-2]]): k.pop()
        k.append(i)
    return np.interp(y, y[k], r[k])


def drape(P, v, n, raw, measured, torso, s, adj, holds):
    """A top hangs: cloth runs straight between the points that hold it out (shoulder blade and glute, chest and
    belly, armpit and hip) and does not follow the body into the lumbar or the waist. A shell that does reads as the
    print painted on the body, the torso narrowing from the shoulders to the hem. Per column of the torso (an angle
    around its axis), the shell goes out to the string pulled tight over it, less what the garment itself goes in
    (a fitted waist stays fitted). holds: vertices that hold the string and are not moved."""
    P = P.copy(); on = torso & (s > -.03) & (v[:, 1] < DRAPE_TO)
    if on.sum() < 8: return P
    c = v[on][:, [0, 2]].mean(0); ang = np.arctan2(v[:, 2] - c[1], v[:, 0] - c[0]); col = np.round(ang / (2 * np.pi / DRAPE_COLUMNS)).astype(int) % DRAPE_COLUMNS
    radius = lambda Q: np.hypot(Q[:, 0] - c[0], Q[:, 2] - c[1])
    move = np.zeros(len(v)); r = radius(P); G = v + n * np.where(measured, raw, 0)[:, None]; rg = np.where(measured, radius(G), np.nan)
    for j in range(DRAPE_COLUMNS):
        i = np.flatnonzero(on & (col == j))
        if len(i) < 3: continue
        own = np.zeros(len(i)); m = ~np.isnan(rg[i])
        if m.sum() > 2: own[m] = hull(v[i][m, 1], rg[i][m]) - rg[i][m]          # how far the garment itself goes in
        move[i] = np.maximum(hull(v[i, 1], r[i]) - own, r[i]) - r[i]
    # one column pushed out and its neighbor not would kink a stripe: the push is evened out around the torso
    idx = np.flatnonzero(on); pos = {k: a for a, k in enumerate(idx)}; near = [[pos[k] for k in adj[i] if k in pos] for i in idx]
    out = move[idx]
    for _ in range(3): out = np.array([(out[i] + out[a].sum()) / (1 + len(a)) for i, a in enumerate(near)])
    d = np.c_[P[idx, 0] - c[0], P[idx, 2] - c[1]]; d /= np.linalg.norm(d, axis=1)[:, None] + 1e-9
    out = np.where(holds[idx], 0, out)                   # what only holds the string stays where it is
    P[idx, 0] += d[:, 0] * out; P[idx, 2] += d[:, 1] * out
    return P


def out_of_fold(P, v, low, adj, above):
    """In a fold of the mannequin (the armpit, where the arm's inner side faces the torso) a vertex's normal points into
    another part of the body, and the shell went in with it: the body showed through the cloth. Above the waist (mask
    above; below it the parts that overlap are the hip and the legs, which the clearances already deal with), a shell
    vertex that ends up inside the mannequin stands off its own vertex of the mannequin the way its neighbors that
    are outside stand off theirs."""
    P = P.copy(); parts = [c for c in low.split(only_watertight=False) if c.is_watertight]
    inside = np.zeros(len(P), bool)
    for c in parts: inside |= c.contains(P)
    inside &= above; left = inside.copy()
    for _ in range(4):
        done = []
        for i in np.flatnonzero(left):
            a = [j for j in adj[i] if not left[j]]
            if a: P[i] = v[i] + (P[a] - v[a]).mean(0); done.append(i)
        left[done] = False
    return P


def cut(v, f, s, attrs):
    """Cuts the mesh at the line s = 0 and keeps the side s > 0. attrs: per-vertex arrays interpolated at the cut."""
    v = list(map(np.asarray, v)); attrs = [list(a) for a in attrs]; s = list(s)
    cache = {}; out = []
    def mid(a, b):
        k = (min(a, b), max(a, b))
        if k not in cache:
            t = s[a] / (s[a] - s[b])
            v.append(v[a] + t * (v[b] - v[a])); s.append(0.0)
            for at in attrs: at.append(at[a] + t * (at[b] - at[a]))
            cache[k] = len(v) - 1
        return cache[k]
    for a, b, c in f:
        pos = [s[a] > 0, s[b] > 0, s[c] > 0]; k = sum(pos)
        if k == 3: out.append((a, b, c))
        elif k == 1:
            i = pos.index(True); p, q, r = (a, b, c)[i], (a, b, c)[(i + 1) % 3], (a, b, c)[(i + 2) % 3]
            out.append((p, mid(p, q), mid(p, r)))
        elif k == 2:
            i = pos.index(False); p, q, r = (a, b, c)[i], (a, b, c)[(i + 1) % 3], (a, b, c)[(i + 2) % 3]
            m1, m2 = mid(p, q), mid(p, r)
            out.append((m1, q, r)); out.append((m1, r, m2))
    return np.array(v), np.array(out, int), [np.array(a) for a in attrs]


def bake(piece, kd, body_v, P, B, N, F, reach, limbs=True, trace=None):
    """New texture of the shape P, F: xatlas charts; each texel casts a ray from its base point B along N to the
    garment (2x2 per texel). limbs=False for a shape that is not on the body's limbs (tube, hood). trace, a dict,
    receives where each texel lies on the new shape and on the garment (identity.py measures the map between them)."""
    atlas = xatlas.Atlas(); atlas.add_mesh(P.astype(np.float32), F.astype(np.uint32))
    po = xatlas.PackOptions(); po.padding = 4; po.resolution = TEX
    atlas.generate(pack_options=po)
    vm, F2, UV = atlas[0]
    V2, B2, N2 = P[vm], B[vm], N[vm]; F2 = F2.astype(int)
    SS = 2; W = H = TEX * SS
    px = UV * [W, H]
    oy, ox, ob, of = [], [], [], []
    for fi, (a, b, c) in enumerate(F2):
        A, Bb, C = px[a], px[b], px[c]
        x0, x1 = int(np.floor(min(A[0], Bb[0], C[0]))), int(np.ceil(max(A[0], Bb[0], C[0])))
        y0, y1 = int(np.floor(min(A[1], Bb[1], C[1]))), int(np.ceil(max(A[1], Bb[1], C[1])))
        xs, ys = np.meshgrid(np.arange(x0, x1 + 1) + .5, np.arange(y0, y1 + 1) + .5)
        den = (Bb[1] - C[1]) * (A[0] - C[0]) + (C[0] - Bb[0]) * (A[1] - C[1])
        if abs(den) < 1e-9: continue
        w0 = ((Bb[1] - C[1]) * (xs - C[0]) + (C[0] - Bb[0]) * (ys - C[1])) / den
        w1 = ((C[1] - A[1]) * (xs - C[0]) + (A[0] - C[0]) * (ys - C[1])) / den
        w2 = 1 - w0 - w1
        m = (w0 >= -.05) & (w1 >= -.05) & (w2 >= -.05)
        if not m.any(): continue
        oy.append(ys[m].astype(int)); ox.append(xs[m].astype(int)); ob.append(np.c_[w0[m], w1[m], w2[m]]); of.append(np.full(m.sum(), fi))
    oy, ox, ob, of = np.concatenate(oy), np.concatenate(ox), np.vstack(ob), np.concatenate(of)
    inside = (ox >= 0) & (ox < W) & (oy >= 0) & (oy < H); oy, ox, ob, of = oy[inside], ox[inside], ob[inside], of[inside]
    base = np.einsum('ij,ijk->ik', ob, B2[F2[of]]); nor = np.einsum('ij,ijk->ik', ob, N2[F2[of]]); nor /= np.linalg.norm(nor, axis=1)[:, None] + 1e-9
    if limbs:
        tri, pt = probe_blend(piece, axes(body_v), base, nor, reach)
        f = np.flatnonzero(tri < 0)   # cloth sunk deeper into the body (shoulder, armpit): same ray, starting further in
        if len(f): tri[f], pt[f] = probe_blend(piece, axes(body_v), base[f], nor[f], reach, DEEP)
    else: _, tri, pt = probe(piece, kd, body_v, base, nor, reach)   # a tube: tube.outer_face reads its outer face
    ok = tri >= 0
    # where the ray found no garment: nearest sample of the outer face, up to 6 cm
    f = np.flatnonzero(~ok)
    if len(f):
        q = base[f] + nor[f] * 0.02
        dist, near = piece.sample_kd.query(q, k=6, distance_upper_bound=0.06)
        fin = np.isfinite(dist); near = np.where(fin, near, 0)
        facing = fin & (np.einsum('ijk,ik->ij', piece.sample_n[near], nor[f]) > 0.2)
        has = facing.any(1); first = facing.argmax(1)
        g = f[has]; chosen = near[has, first[has]]
        tri[g] = piece.sample_f[chosen]; pt[g] = piece.sample_p[chosen]; ok[g] = True
    if trace is not None:
        trace.update(x=ox[ok], y=oy[ok], size=W, new=np.einsum('ij,ijk->ik', ob, V2[F2[of]])[ok], tri=tri[ok], old=pt[ok], normal=nor[ok], shape=(V2, F2))
    color = np.zeros((len(base), 3), np.float32); color[ok] = piece.color(tri[ok], pt[ok])
    img = np.zeros((H, W, 3), np.float32); valid = np.zeros((H, W), bool); owned = np.zeros((H, W), bool)
    yy = H - 1 - oy
    owned[yy, ox] = True
    img[yy[ok], ox[ok]] = color[ok]; valid[yy[ok], ox[ok]] = True
    missing = float((owned & ~valid).sum() / max(owned.sum(), 1))
    # shrinks 2x2 weighting only the valid texels, then fills the rest with the nearest neighbor
    wv = valid.reshape(TEX, SS, TEX, SS).sum((1, 3)).astype(np.float32)
    img = (img * valid[..., None]).reshape(TEX, SS, TEX, SS, 3).sum((1, 3)) / np.maximum(wv, 1)[..., None]
    valid = wv > 0
    idx = ndimage.distance_transform_edt(~valid, return_distances=False, return_indices=True)
    img = img[idx[0], idx[1]]
    return V2, N2, UV, F2, Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)), missing


def export(path, V, F, N, UV, img, double_sided=False):
    m = trimesh.Trimesh(V, F, vertex_normals=N, process=False)
    m.visual = trimesh.visual.TextureVisuals(uv=UV, material=trimesh.visual.material.PBRMaterial(
        baseColorTexture=img, metallicFactor=0, roughnessFactor=1, doubleSided=double_sided))
    m.export(path)


def generate(kind, pid, path, dense_path, low_path, out, trace=None):
    """Writes OUT/shell-NNN.glb and returns its report."""
    os.makedirs(out + '/env', exist_ok=True)
    mb = L.recorded(); waistband, hem_max = R.lines(mb)['waistband'], R.lines(mb)['top_hem_max']
    dense = load_body(dense_path)
    low = trimesh.load(low_path).to_geometry(); low = trimesh.Trimesh(low.vertices, low.faces, process=False)
    kd_dense = cKDTree(dense.vertices); v, n = np.asarray(low.vertices), np.asarray(low.vertex_normals); adj = low.vertex_neighbors
    clear, clear_limb = ceiling(pid); lab = L.limb(v)
    # on the mannequin the arm goes on over the shoulder, in one mesh with the torso: up there it is arm too
    up = (lab == 0) & (np.abs(v[:, 0]) > SHOULDER_OUT) & (v[:, 1] < SHOULDER_TOP); lab[up] = np.where(v[up, 0] > 0, 1, 2)
    top = np.where(lab > 0, clear_limb, clear); top = np.maximum(smooth(top, adj, 2), MIN_CLEAR)
    piece = Piece(path); reach = clear + 0.05
    cov = coverage(piece, dense, 0.12, kind)
    # signed distance to the edge of the coverage, measured on the dense body
    kd_c, kd_n = cKDTree(dense.vertices[cov]), cKDTree(dense.vertices[~cov])
    _, i = kd_dense.query(v); cov_low = cov[i]
    s = np.where(cov_low, kd_n.query(v)[0], -kd_c.query(v)[0])
    s = np.where(v[:, 1] > 1.30, smooth(s, adj, 4), s)
    # engine rule: the waistband sits on the line and the hem where the registration left it, each with the curve
    # the garment has around the body (a waistband that dips in front, a shirt tail); a level cut reads as another garment
    S = L.sample(path, 60000)
    if kind == 'bottom':
        tr = (lab == 0) & (v[:, 1] > mb['crotch'] + WAIST_FROM)
        line = edge(S, L.waist_center(S), 98, v); line = np.minimum(line - line[tr].min() + waistband - WAIST_DIP, mb['waist'] - WAIST_TOP)
        s = np.where(tr, line - v[:, 1], s); cov_low = np.where(tr, v[:, 1] < line + .03, cov_low)
        hip = (lab == 0) & ~tr; s = np.where(hip, np.maximum(s, .02), s); cov_low |= hip   # every bottom wears the hip: no pinhole where the leg's part meets the torso's
    else:
        torso = S[~np.isin(L.limb(dense.vertices)[kd_dense.query(S)[1]], (1, 2)) & (S[:, 1] < mb['armpit'])]
        tr = (lab == 0) & (v[:, 1] < HEM_TO)
        if len(torso) > 2000 and np.percentile(torso[:, 1], 2) < HEM_TO - .05:
            line = np.minimum(edge(torso, torso[:, [0, 2]].mean(0), 2, v, sides=False), HEM_TO - .03)
            if np.median(line[tr]) < hem_max + HEM_RISE: line = np.minimum(line, hem_max + HEM_RISE)   # a top that reaches its line keeps the waistband covered all around
            elif np.median(line[tr]) < waistband + SLIVER: line = np.minimum(line, waistband - WAIST_TOP)   # a hem that stops just over the waistband meets it: the strip of body between them read as a tear
            s = np.where(tr, v[:, 1] - line, s); cov_low = np.where(tr, v[:, 1] > line - .03, cov_low)
    # a part of the mannequin is closed by a lid inside the body, and the lid's middle is buried in it: it wears
    # nothing, and the ring around it goes straight out like an open rim. The hip has no lid (mannequin.joined_hip()
    # joins torso and legs there) and its band stands off the dense body's skin: read as buried, it left a hole in
    # every bottom at the hip
    buried = (kd_dense.query(v)[0] > BURIED) & (v[:, 1] > mb['waist']); s = np.where(buried, -1., s); cov_low &= ~buried
    # a few vertices left bare with cloth all around them (the fold of the armpit under a sleeve, where no ray meets the
    # garment) are a hole the body shows through, not an opening of the garment: they are covered
    bare = (s <= 0) & ~buried; seen = np.zeros(len(v), bool)
    for i in np.flatnonzero(bare):
        if seen[i]: continue
        isle = [i]; seen[i] = True
        for k in isle:
            for j in adj[k]:
                if bare[j] and not seen[j]: seen[j] = True; isle.append(j)
        if len(isle) <= ISLAND: s[isle] = MIN_CLEAR; cov_low[isle] = True
    # and the other way round, on the arm: cloth on a few of its vertices with bare body all around them (the end of a
    # sleeve that touches a ring at two or three vertices) is a scrap hanging by the garment, and wears nothing
    worn = s > 0; seen = np.zeros(len(v), bool)
    for i in np.flatnonzero(worn):
        if seen[i]: continue
        isle = [i]; seen[i] = True
        for k in isle:
            for j in adj[k]:
                if worn[j] and not seen[j]: seen[j] = True; isle.append(j)
        if len(isle) <= ISLAND and np.isin(lab[isle], (1, 2)).all(): s[isle] = -1.; cov_low[isle] = False
    d, _, _ = probe(piece, kd_dense, dense.vertices, v, n, reach)
    measured = ~np.isnan(d) & cov_low; raw = d.copy()
    d = np.where(measured, np.clip(d, MIN_CLEAR, top), np.nan)
    # where nothing was measured (hole, inner side of the arm): mean of the measured neighbors, spreading
    for _ in range(30):
        lacks = np.isnan(d)
        if not lacks.any(): break
        new = d.copy()
        for i in np.flatnonzero(lacks):
            a = [j for j in adj[i] if not np.isnan(d[j])]
            if a: new[i] = np.mean(d[a])
        d = new
    d = np.nan_to_num(d, nan=MIN_CLEAR); d = np.clip(smooth(d, adj, 2), MIN_CLEAR, top)
    # sleeve and leg become a tube: one clearance around the limb at each height, smooth along it (otherwise the
    # shell sinks where the generated sleeve cuts through the arm, and a step shows)
    for m in (1, 2, 3, 4):
        sm = (lab == m) & (s > -0.02)
        if sm.sum() < 6: continue
        ys = v[sm, 1]; bands = np.arange(ys.min(), ys.max() + 0.03, 0.03)
        med = np.array([np.median(d[sm][(ys >= a) & (ys < a + 0.03)]) if ((ys >= a) & (ys < a + 0.03)).any() else np.nan for a in bands])
        ok = ~np.isnan(med); med = np.interp(bands, bands[ok], med[ok])
        med = np.convolve(np.pad(med, 2, mode='edge'), np.ones(5) / 5, mode='valid')
        d[sm] = np.clip(np.interp(ys, bands + 0.015, med), MIN_CLEAR, top[sm])
    if kind == 'bottom':                                  # the envelope reaches two rings past the edge: a top's hem is cut between rings
        on = s > -.03
        for _ in range(2): on = np.array([on[i] or on[a].any() for i, a in enumerate(adj)])
        np.save(f'{out}/env/{pid}.npy', np.where(on, d, 0.0))
    else:                                                 # engine rule: outside every bottom
        envs = [np.load(f) for f in sorted(glob.glob(f'{out}/env/*.npy'))]
        if envs:
            env = np.max(envs, axis=0); d = np.where(env > 0, np.maximum(d, env + RISE), d)
            # the mannequin is built in parts: at the hip a bottom wears the leg's part too, which runs outside the
            # torso's. The top goes outside the bottoms' surface on any part near each of its vertices
            on = np.flatnonzero(env > 0); E = v[on] + n[on] * env[on, None]
            for i, near in enumerate(cKDTree(v[on]).query_ball_point(v, NEAR_PART)):
                j = on[near]; j = j[n[j] @ n[i] > .5]
                if len(j): d[i] = max(d[i], float(((v[j] + n[j] * env[j, None] - v[i]) @ n[i]).max()) + PART_RISE)
    # on the open rim of a part (the top of a leg, inside the hip) the normal leans along the limb: the shell goes
    # straight out, or the rim of the mannequin shows over the rim of the shell
    out_dir = n.copy(); e = np.sort(low.edges, axis=1); u, c = np.unique(e, axis=0, return_counts=True); rim = np.unique(u[c == 1])
    rim = np.union1d(rim, [j for i in np.flatnonzero(buried) for j in adj[i]]).astype(int)
    out_dir[rim, 1] = 0; out_dir[rim] /= np.linalg.norm(out_dir[rim], axis=1)[:, None] + 1e-9
    P = v + out_dir * d[:, None]
    # the shoulder holds the cloth out too: the side of a top hangs from it, not from the armpit
    # the shoulder holds the string and stays where it is: pushed out with the torso, the top of the sleeve sheared
    # sideways off the arm under it and the body showed at the armpit
    socket = (lab == 0) & (np.abs(v[:, 0]) > .1) & (n[:, 0] * v[:, 0] < 0)   # nor does the socket of the arm, which faces inward
    holds = (up & (v[:, 1] > SHOULDER_HOLDS)) | socket
    if kind == 'top':
        # a shoulder left bare (a sleeveless top, a cap sleeve) holds nothing around the armhole: the string ran from it
        # across the opening and the cloth beside the armpit stood off the body like a wing. From the armpit down the
        # side of the top keeps the width the shoulder gives it
        worn = (holds & (s > 0)) | socket
        hung, P = drape(P, v, n, raw, measured, (lab == 0) | holds, s, adj, holds), drape(P, v, n, raw, measured, (lab == 0) | worn, s, adj, worn)
        w = np.clip((mb['armpit'] - v[:, 1]) / ARMHOLE, 0, 1)[:, None]; P = P + w * (hung - P)
    P = out_of_fold(P, v, low, adj, v[:, 1] > mb['waist'])
    Pc, Fc, (Nc, Bc) = cut(P, low.faces, s, [n, v])
    used = np.unique(Fc); remap = -np.ones(len(Pc), int); remap[used] = np.arange(len(used))
    Pc, Nc, Bc, Fc = Pc[used], Nc[used], Bc[used], remap[Fc]
    Nc /= np.linalg.norm(Nc, axis=1)[:, None] + 1e-9
    V2, N2, UV, F2, img, missing = bake(piece, kd_dense, dense.vertices, Pc, Bc, Nc, Fc, reach, trace=trace)
    export(f'{out}/shell-{pid}.glb', V2, F2, N2, UV, img)
    b = raw[measured]
    return {'triangles_before': int(len(piece.f)), 'triangles': int(len(F2)), 'inside_body_before_pct': round(float((b < 0).mean() * 100), 1),
            'clearance_cm': [round(float(d[s > 0].min() * 100), 1), round(float(d[s > 0].max() * 100), 1)], 'texture_without_source_pct': round(missing * 100, 1)}


if __name__ == '__main__':
    kind, pid, path, dense_path, low_path, out = sys.argv[1:7]
    print(pid, json.dumps(generate(kind, pid, path, dense_path, low_path, out)))
