"""Hood and collar as a loose part in few polygons.

A shell (shell.py) follows the body, so it flattens a hood onto the back and paints it there. The loose part is the
cloth of the generated garment that the shell cannot hold: around the neck and on the upper back, what stands away
from the body as a hood's bump does (further out the lower it hangs, because every garment hangs looser below the
neck) or stands over the shell as a collar does. The choice is closed and smoothed along the garment and cut on a
line, not triangle by triangle, so the border is clean; of it only the faces a camera can see are kept (a lining
pressed against the back comes dark from the generator and would show through the outer face once both are
simplified), and only pieces that hang from the neck. Where the shell passes over it, the loose part is lifted
onto the shell, so it never shows in shards. It is simplified to TARGET triangles and painted from the same faces
it came from, each texel from the nearest point of them that faces the same way: the print of a hood is the
garment's own. A garment with too little cloth outside its shell (a jersey's collar) gets no loose part.

measure() compares the result with the garment as generated, from cameras around it, one ray per RAY² of area:
- dark_cm2: the loose part in view much darker than the garment at the same place (a hole showing the lining);
- off_cm2: the loose part in view with nothing of the garment within NEAR behind or in front of it (a sliver);
- edge_cm: length of the loose part's border (a ragged cut, a shard);
- lost_cm2: the garment's cloth around the neck and on the upper back in view where the rebuilt garment (shell and
  loose part) shows nothing: against the background (the hood or the collar lost its outline), or in front of the
  body where the low-poly mannequin is now bare (bare_cm2, a part of lost_cm2).
build() returns them, engine.py keeps them in its report, and check(report) fails on what rose above loose_hood.json.
usage: python3 tools/fit/loose_hood.py DENSE_BODY.glb GARMENT.glb OUT.glb [SHELL.glb]
       python3 tools/fit/loose_hood.py --check [WORK]     (no WORK: runs the engine on the hooded garments first)
       python3 tools/fit/loose_hood.py --write WORK       (records the measures of WORK/report.json as the baseline)"""
import sys, os, json, tempfile, numpy as np, trimesh, xatlas, fast_simplification
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy import ndimage
from PIL import Image
import shell as S

NECK, BASE, SHOULDERS = 1.47, 1.20, .19   # m: neck line; lowest height; half width kept
FAR = .03              # m: cloth this far from the body is hood or collar, not back or shoulder
SEED = .012            # m: cloth this far outside the shell is not held by it
CLOSE, SMOOTH = 2, 3   # edges of the garment: holes of the choice closed; passes that smooth its border
SLOPE = .15            # m per m: below the neck a garment hangs looser, and a hood has to stand further out to be one
HANGS = 1.42           # m: a loose piece that does not reach this height hangs from nothing
EDGE = .3              # of 1: where the smoothed choice is cut; under one half, a thin collar is not eaten by the smoothing
LIFT = .004            # m: the loose part stays this far over the shell
OVER_BODY = .003       # m: the loose part stays this far over the low-poly mannequin
IN_BODY = .002         # m: cloth this deep in the low-poly mannequin is inside it
MIN_AREA = .004        # m²: a kept piece smaller than this is a sliver
MIN_LOOSE = .025       # m²: less cloth than this outside the shell is no hood: the shell alone holds the garment
TARGET = 260           # triangles
TEX = 256              # px: side of the baked texture
NEAR = .05             # m: two surfaces this close along a ray are the same cloth (the shell may move it this much)
DARK = 45              # of 255: darker than the garment by this much, a hole
RAY = .005             # m: side of the area one ray stands for
BASELINE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'loose_hood.json')
SLACK = {'edge_cm': 5, 'dark_cm2': 5, 'off_cm2': 10, 'lost_cm2': 10}   # cm, cm² summed over the cameras: below this, noise of the rays


def directions():
    """Cameras around the garment: 12 around, level, from above and from a little below."""
    return np.array([[np.sin(a) * np.cos(e), np.sin(e), np.cos(a) * np.cos(e)]
                     for e in np.radians([-15, 15, 45]) for a in np.arange(12) * np.pi / 6])


def nearest(mesh, P, n=150000):
    """For each point: signed distance to an open surface (negative on its inner side, positive past its rim), and
    the nearest point of the surface with its normal."""
    p, f = trimesh.sample.sample_surface_even(mesh, n, seed=1); d, k = cKDTree(p).query(P); nor = mesh.face_normals[f][k]
    return np.where(np.einsum('ij,ij->i', P - p[k], nor) > -.3 * d, d, -d), p[k], nor


def merged(piece):
    """The garment with its vertices welded, triangle for triangle the same as the piece's."""
    m = trimesh.Trimesh(piece.v, piece.f, process=False); n = len(m.faces); m.merge_vertices(digits_vertex=4)
    assert len(m.faces) == n
    return m


def around_neck(body, P):
    """Per point: it is where a hood or a collar lives (above the neck line, or behind the back above BASE, between
    the shoulders), and its distance to the body."""
    bp, bf = trimesh.sample.sample_surface_even(body, 200000, seed=1); d, j = cKDTree(bp).query(P)
    return ((P[:, 1] > NECK) | ((bp[j, 2] - P[:, 2] > .01) & (P[:, 1] > BASE))) & (np.abs(P[:, 0]) < SHOULDERS), d


def spread(sel, E, rings, grow=True):
    sel = sel.copy()
    for _ in range(rings):
        a, b = sel[E[:, 0]], sel[E[:, 1]]
        if grow: sel[E[a & ~b, 1]] = True; sel[E[b & ~a, 0]] = True
        else: sel[E[a & ~b, 0]] = False; sel[E[b & ~a, 1]] = False
    return sel


def loose(piece, body, shell):
    """The loose part as cut from the garment: vertices, triangles, and the garment's triangles it came from.
    None when the shell holds the whole garment."""
    m = merged(piece); P = np.asarray(m.vertices); F = np.asarray(m.faces); E = m.edges_unique
    zone, d = around_neck(body, P); sd, _, _ = nearest(shell, P)
    sel = zone & ((d > FAR + SLOPE * np.maximum(0, HANGS - P[:, 1])) | ((P[:, 1] > NECK) & (sd > SEED)))   # a hood's bump, a collar standing over the shell
    if m.area_faces[(zone & (sd > SEED))[F].any(1)].sum() < MIN_LOOSE: return None
    sel = spread(spread(sel, E, CLOSE), E, CLOSE, grow=False)      # closes the holes and notches of the choice
    g = sel.astype(float); A = coo_matrix((np.ones(2 * len(E)), (np.r_[E[:, 0], E[:, 1]], np.r_[E[:, 1], E[:, 0]])), shape=(len(P), len(P))).tocsr()
    deg = np.maximum(np.asarray(A.sum(1)).ravel(), 1)
    for _ in range(SMOOTH): g = .5 * g + .5 * (A @ g) / deg       # a smooth border instead of one triangle in, one out
    cand = np.flatnonzero((g[F] > EDGE).any(1))
    V, Fc, _ = S.cut(P, F[cand], g - EDGE, [])
    c = trimesh.Trimesh(V, Fc, process=False); c.remove_unreferenced_vertices()
    c.update_faces(seen(c, piece, body)); c.remove_unreferenced_vertices()
    parts = [p for p in c.split(only_watertight=False) if p.area > MIN_AREA and p.vertices[:, 1].max() > HANGS]   # a hood hangs from the neck
    if not parts: return None
    c = trimesh.util.concatenate(parts)
    return np.asarray(c.vertices), np.asarray(c.faces), cand


def seen(c, piece, body):
    """Per triangle of the cut cloth c: a camera sees its outer face (the garment and the body in the way)."""
    world = trimesh.util.concatenate([piece.mesh, trimesh.Trimesh(body.vertices, body.faces, process=False)])
    out = np.zeros(len(c.faces), bool); n = c.face_normals; tri = c.triangles
    for w in ((1, 1, 1), (4, 1, 1), (1, 4, 1), (1, 1, 4)):
        p = np.einsum('k,ikj->ij', np.array(w) / sum(w), tri) + n * .002
        for d in directions():
            front = np.flatnonzero((n @ d > .1) & ~out)
            if not len(front): continue
            out[front[~world.ray.intersects_any(p[front], np.repeat(d[None], len(front), 0))]] = True
    return out


def simplify(V, F, target=TARGET):
    """The cut down to target triangles. Where a tangled cut stops the collapse, vertices closer than a cell are
    welded first, in cells that grow."""
    for cell in (0, .01, .015, .02, .03, .04, .06):
        if len(F) <= target: break
        if cell:
            _, first, inv = np.unique(np.round(V / cell).astype(int), axis=0, return_index=True, return_inverse=True)
            V, F = V[first], inv.ravel()[F]; F = F[(F[:, 0] != F[:, 1]) & (F[:, 1] != F[:, 2]) & (F[:, 0] != F[:, 2])]
            F = F[np.unique(np.sort(F, axis=1), axis=0, return_index=True)[1]]
        for agg in (3, 7):
            if len(F) > target: V, F = fast_simplification.simplify(np.asarray(V, np.float32), F, target_count=target - 1, agg=agg)   # the collapse may stop one triangle over
    return np.asarray(V, float), np.asarray(F)


def lift(V, shell):
    """Vertices under the shell, or closer than LIFT over it, go to LIFT over it: the loose part is never hidden in
    pieces by the shell it lies on."""
    sd, q, n = nearest(shell, V); low = sd < LIFT
    V = V.copy(); V[low] = q[low] + n[low] * LIFT
    return V


def split(V, F, hit):
    """The triangles `hit` split in four at the middle of their edges, and their neighbors along the split edges, so
    no edge is left with a vertex in the middle of it."""
    V = list(V); mid = {}
    def m(a, b):
        k = (min(a, b), max(a, b))
        if k not in mid: V.append((V[a] + V[b]) / 2); mid[k] = len(V) - 1
        return mid[k]
    for a, b, c in F[hit]: m(a, b), m(b, c), m(c, a)
    out = []
    for t in F:
        t = [int(x) for x in t]; cut = [mid.get((min(t[i], t[(i + 1) % 3]), max(t[i], t[(i + 1) % 3]))) for i in range(3)]; n = sum(x is not None for x in cut)
        if n == 0: out.append(t)
        elif n == 3: out += [(t[0], cut[0], cut[2]), (cut[0], t[1], cut[1]), (cut[2], cut[1], t[2]), (cut[0], cut[1], cut[2])]
        elif n == 1:
            i = [x is not None for x in cut].index(True); a, b, c = t[i], t[(i + 1) % 3], t[(i + 2) % 3]
            out += [(a, cut[i], c), (cut[i], b, c)]
        else:
            i = [x is None for x in cut].index(True); a, b, c = t[i], t[(i + 1) % 3], t[(i + 2) % 3]   # edge a-b whole
            bc, ca = cut[(i + 1) % 3], cut[(i + 2) % 3]
            out += [(a, b, bc), (a, bc, ca), (ca, bc, c)]
    return np.array(V), np.array(out, int)


def outside(V, F, low_body):
    """The loose part without what cuts through the neck of the low-poly mannequin, which is what the garment is
    worn on and where it counts as body crossing the garment (below the neck line the loose part lies on the shell,
    and lift() keeps it over). The vertices of a triangle that crosses are brought to OVER_BODY over the mannequin's
    surface; one that still bridges through it is split and its new vertices brought out too, so the cloth stays in
    view; only what bridges after that is dropped."""
    def out_of_body(V, F):                                     # only the vertices of triangles that cross: the rest stays as cut
        sd, q, n = nearest(low_body, V); deep = (sd < 0) & np.isin(np.arange(len(V)), F)
        V = V.copy(); V[deep] = q[deep] + n[deep] * OVER_BODY
        return V
    def inside(V, F):
        P = V[F]; hit = np.zeros(len(F), bool)
        for w in ((1, 1, 1), (2, 1, 0), (0, 2, 1), (1, 0, 2), (1, 2, 0), (0, 1, 2), (2, 0, 1)):
            hit |= nearest(low_body, np.einsum('k,ikj->ij', np.array(w) / 3, P))[0] <= -IN_BODY
        return hit & (P[:, :, 1].min(1) > NECK)
    hit = inside(V, F)
    if not hit.any(): return V, F
    V = out_of_body(V, F[hit]); hit = inside(V, F)
    if hit.any():
        V, F = split(V, F, hit); V = out_of_body(V, F); F = F[~inside(V, F)]
    return V, F


def bake(piece, faces, V, F):
    """Texture of the shape V, F from the triangles `faces` of the garment: each texel takes the color of the nearest
    point of them that faces its way."""
    src = trimesh.Trimesh(piece.v, piece.f[faces], process=False)
    sp, sf = trimesh.sample.sample_surface(src, 200000, seed=1); sn = src.face_normals[sf]; kd = cKDTree(sp)
    atlas = xatlas.Atlas(); atlas.add_mesh(V.astype(np.float32), F.astype(np.uint32))
    po = xatlas.PackOptions(); po.padding = 4; po.resolution = TEX
    atlas.generate(pack_options=po)
    vm, F2, UV = atlas[0]; F2 = F2.astype(int); V2 = V[vm]
    N2 = np.asarray(trimesh.Trimesh(V, F, process=False).vertex_normals)[vm]
    px = UV * TEX; img = np.zeros((TEX, TEX, 3), np.float32); valid = np.zeros((TEX, TEX), bool)
    for a, b, c in F2:
        A, B, C = px[a], px[b], px[c]
        x0, y0 = np.floor(np.minimum(np.minimum(A, B), C)).astype(int); x1, y1 = np.ceil(np.maximum(np.maximum(A, B), C)).astype(int)
        xs, ys = np.meshgrid(np.arange(x0, x1 + 1) + .5, np.arange(y0, y1 + 1) + .5)
        den = (B[1] - C[1]) * (A[0] - C[0]) + (C[0] - B[0]) * (A[1] - C[1])
        if abs(den) < 1e-9: continue
        w0 = ((B[1] - C[1]) * (xs - C[0]) + (C[0] - B[0]) * (ys - C[1])) / den
        w1 = ((C[1] - A[1]) * (xs - C[0]) + (A[0] - C[0]) * (ys - C[1])) / den
        w = np.stack([w0, w1, 1 - w0 - w1], -1); ok = (w >= -.05).all(-1)
        x, y = xs[ok].astype(int), ys[ok].astype(int); ok2 = (x >= 0) & (x < TEX) & (y >= 0) & (y < TEX)
        x, y, w = x[ok2], y[ok2], np.clip(w[ok][ok2], 0, 1); w /= w.sum(1, keepdims=True)
        if not len(x): continue
        p = w @ V2[[a, b, c]]; n = np.cross(V2[b] - V2[a], V2[c] - V2[a]); n /= np.linalg.norm(n) + 1e-12
        _, near = kd.query(p, k=8)
        facing = sn[near] @ n > 0; first = np.where(facing.any(1), facing.argmax(1), 0); s = near[np.arange(len(p)), first]
        img[TEX - 1 - y, x] = piece.color(faces[sf[s]], sp[s]); valid[TEX - 1 - y, x] = True
    idx = ndimage.distance_transform_edt(~valid, return_distances=False, return_indices=True)
    return V2, N2, UV, F2, Image.fromarray(np.clip(img[idx[0], idx[1]], 0, 255).astype(np.uint8))


def build(dense_path, src, dst, shell_path=None):
    """Writes the loose part of the garment src to dst, or nothing when the shell holds the whole garment.
    shell_path: the garment's shell as built; by default the one the engine wrote next to dst."""
    shell_path = shell_path or dst.replace('-hood.glb', '-shell.glb')
    if os.path.exists(dst): os.remove(dst)
    body = S.load_body(dense_path); piece = S.Piece(src)
    sh = trimesh.load(shell_path, process=False).to_geometry(); sh = trimesh.Trimesh(sh.vertices, sh.faces, process=False)
    low = S.load_body(low_path(dense_path))
    cloth = loose(piece, body, sh)
    if cloth is None: return measure(dense_path, src, [shell_path], dst)
    V0, F0, faces = cloth; before = len(F0); V0 = lift(V0, sh); target = TARGET
    while True:                                                # the cut on the mannequin adds triangles: simplify further until it fits
        V, F = simplify(V0, F0, target)
        V, F = outside(lift(V, sh), F, low)
        if len(F) <= TARGET or target < 60: break
        target -= len(F) - TARGET + 4
    m = trimesh.Trimesh(V, F, process=False); m.remove_unreferenced_vertices()
    V2, N2, UV, F2, img = bake(piece, faces, np.asarray(m.vertices), np.asarray(m.faces))
    S.export(dst, V2, F2, N2, UV, img, double_sided=True)
    return {**measure(dense_path, src, [shell_path], dst), 'triangles_before': int(before),
            'pieces': len(m.split(only_watertight=False)), 'area_cm2': int(m.area * 1e4)}


def low_path(dense_path):
    """The low-poly mannequin the engine wrote next to the dense one."""
    low = dense_path.replace('dense-', 'low-'); assert low != dense_path and os.path.exists(low), f'no low-poly mannequin for {dense_path}'
    return low


def open_edge(mesh):
    """Length of the border of a surface (m): a ragged cut and a sliver are mostly border."""
    m = trimesh.Trimesh(mesh.vertices, mesh.faces, process=False); m.merge_vertices(digits_vertex=5)
    e = np.sort(m.edges, axis=1); u, n = np.unique(e, axis=0, return_counts=True)
    return np.linalg.norm(m.vertices[u[n == 1, 0]] - m.vertices[u[n == 1, 1]], axis=1).sum()


class Look:
    """A surface with its texture, seen along rays."""
    def __init__(self, paths):
        self.pieces = [S.Piece(p) for p in paths]; self.off = np.cumsum([0] + [len(p.f) for p in self.pieces])
        self.mesh = trimesh.util.concatenate([p.mesh for p in self.pieces]) if len(paths) > 1 else self.pieces[0].mesh
        self.ray = trimesh.ray.ray_pyembree.RayMeshIntersector(self.mesh)

    def first(self, o, d):
        """Distance, triangle and point of the first hit of each ray (inf, -1 where none)."""
        loc, ir, it = self.ray.intersects_location(o, d, multiple_hits=False)
        t = np.full(len(o), np.inf); tri = np.full(len(o), -1); pt = np.zeros((len(o), 3))
        t[ir] = np.linalg.norm(loc - o[ir], axis=1); tri[ir] = it; pt[ir] = loc
        return t, tri, pt

    def luma(self, tri, pt):
        out = np.zeros(len(tri))
        for k, p in enumerate(self.pieces):
            s = (tri >= self.off[k]) & (tri < self.off[k + 1])
            if s.any(): out[s] = p.color(tri[s] - self.off[k], pt[s]) @ [.299, .587, .114]
        return out


def measure(dense_path, src, shell_paths, hood_path):
    """The loose part against the garment as generated, in cm² summed over the cameras, and its triangles."""
    body = S.load_body(dense_path); body = trimesh.Trimesh(body.vertices, body.faces, process=False)
    worn = S.load_body(low_path(dense_path)); worn = trimesh.Trimesh(worn.vertices, worn.faces, process=False)
    old = Look([src]); cloth = around_neck(S.load_body(dense_path), old.pieces[0].v)[0][old.pieces[0].f].all(1)
    has = os.path.exists(hood_path); new = Look(list(shell_paths) + ([hood_path] if has else []))
    hood_from = new.off[-2] if has else len(new.mesh.faces)
    hm = new.pieces[-1].mesh if has else None
    out = {'triangles': int(len(hm.faces)) if has else 0, 'edge_cm': round(100 * float(open_edge(hm)), 1) if has else 0.0, 'dark_cm2': 0.0, 'off_cm2': 0.0, 'lost_cm2': 0.0, 'bare_cm2': 0.0}
    cm2 = RAY * RAY * 1e4
    for d in directions():
        r = np.cross([0, 1, 0], d); r /= np.linalg.norm(r); u = np.cross(d, r)
        a, b = (x.ravel() for x in np.meshgrid(np.arange(-.35, .35, RAY), np.arange(-.35, .35, RAY)))
        o = np.array([0, 1.4, 0]) + a[:, None] * r + b[:, None] * u + d * 3; dd = np.repeat(-d[None], len(o), 0)
        tb = body.ray.intersects_location(o, dd, multiple_hits=False); t_body = np.full(len(o), np.inf); t_body[tb[1]] = np.linalg.norm(tb[0] - o[tb[1]], axis=1)
        to, fo, po = old.first(o, dd); tn, fn, pn = new.first(o, dd)
        hood = (fn >= hood_from) & (tn < t_body)
        with np.errstate(invalid='ignore'): same = np.abs(tn - to) < NEAR
        out['off_cm2'] += cm2 * float((hood & ~same).sum())
        s = hood & same
        if s.any(): out['dark_cm2'] += cm2 * float((new.luma(fn[s], pn[s]) < old.luma(fo[s], po[s]) - DARK).sum())
        was = (fo >= 0) & cloth[np.maximum(fo, 0)] & ~np.isfinite(t_body)
        out['lost_cm2'] += cm2 * float((was & ~np.isfinite(tn)).sum())
        tw = worn.ray.intersects_location(o, dd, multiple_hits=False); t_worn = np.full(len(o), np.inf); t_worn[tw[1]] = np.linalg.norm(tw[0] - o[tw[1]], axis=1)
        bare = (fo >= 0) & cloth[np.maximum(fo, 0)] & (to < t_body) & np.isfinite(t_worn) & ~(tn < t_worn)
        out['bare_cm2'] += cm2 * float(bare.sum())
    out['lost_cm2'] += out['bare_cm2']
    return {k: round(v, 1) if isinstance(v, float) else v for k, v in out.items()}


def check(report):
    """Failures of an engine report against the baseline, which only goes down."""
    base = json.load(open(BASELINE)); fails = []
    for pid, was in sorted(base.items()):
        if pid not in report['garments']: continue             # a run of other garments
        now = report['garments'][pid].get('hood')
        if now is None: fails.append(f'{pid}: has a baseline and the engine built no loose part for it'); continue
        if now['triangles'] > TARGET: fails.append(f"{pid}: {now['triangles']} triangles in the loose part, above {TARGET}")
        fails += [f'{pid}: {k} {now[k]} above the baseline {was[k]}' for k, slack in SLACK.items() if now[k] > was[k] + slack]
    return fails


def write(report):
    base = json.load(open(BASELINE))
    new = {p: {k: report['garments'][p]['hood'][k] for k in ('triangles', *SLACK)} for p in base}
    for p, g in new.items():
        for k in SLACK:
            if not base[p]: continue
            assert g[k] <= base[p][k] + SLACK[k], f'{p}: {k} would go up'
            g[k] = min(g[k], base[p][k])                       # within the slack the recorded value stays: it never creeps up
    open(BASELINE, 'w').write('{\n' + ',\n'.join(f' "{p}": {json.dumps(g)}' for p, g in sorted(new.items())) + '\n}\n')


if __name__ == '__main__':
    if sys.argv[1] in ('--check', '--write'):
        if len(sys.argv) > 2: report = json.load(open(sys.argv[2] + '/report.json'))
        else:
            import engine
            report = engine.run(tempfile.mkdtemp(), sorted(json.load(open(BASELINE))))
        if sys.argv[1] == '--write': write(report)
        fails = check(report); print('\n'.join(fails) or 'ok'); sys.exit(1 if fails else 0)
    else: print(build(*sys.argv[1:5]))
