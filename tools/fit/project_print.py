"""Builds a bottom from a shape Tripo generated on the neutral mannequin and the print of the piece's earlier model.

The pants Tripo made from the shop photo came shaped on its own mannequin, with thinner legs: on the neutral body the
waist, hip and thigh of 014 sat inside the body (70, 46 and 17% of the area) and pulling the cloth out stretched the
print (known issue waist-014). Here the shape comes from a Tripo model generated on the neutral mannequin itself (three
views of the trousers dressed on renders of pose C, front, left and back, then multiview-to-model without texture),
and the print is painted on the final shape, so no later move stretches it:
  1. align: height, turn about y and ICP on the bare torso, which is the mannequin itself;
  2. remove the mannequin: what lies within BODY of the body above the crotch, the sneakers with the hem moulded over
     them (below FEET: shoe.py), and what the hands fused to the hip; keep the largest piece, cut above the waistband
     (TOP), fill the holes the hands leave and level the hem;
  3. shape: each leg's axis onto the body's leg from the knee down (the shin came 5 cm behind), the legs parted at the
     middle (PART: the inner walls crossed below the knee and showed through each other), the waistband gathered to
     GATHER from the waist (the elastic came 4.3 cm off all around), the gap eased under 4 cm (GAP; below ANKLE, the gap
     to the leg, not to the sneaker the hem flared over), whatever is closer than SLACK pushed out;
  4. print: UV unwrap (xatlas) and each texel takes the colour of the print source at the same place of its unrolled
     cloth: per side of x = 0 (the other leg's stripes never reach this one), the same relative height (hem to
     waistband) and the angle around an axis that goes smoothly from each leg's to the hip's (BLEND: one angle, no seam
     where the hip meets the legs), on the outermost layer of the old cloth. Around the outer side a band of BAND keeps
     its length, so the stripes keep their width on the wider legs, and is taken from where the source has the stripes
     in that row (21-24° behind the side seam, wavering): they come out straight on the side, as in the photo. White
     below the crotch away from the stripes is a smudge of the generator and is painted over (clean); below
     SOURCE_HEM the source folds over the shoe, and the row above the fold carries on to the hem.
The output is in the site's format (WebP texture, no normal map, single-sided like the piece it replaces) and is also
the stretch reference (reference/originals/tripo/NNN.glb): the print is laid on this shape, and stretch.py measures
what later tools move; print_check.py measures the projection against the print source.
usage: python3 tools/fit/project_print.py SHAPE.glb PRINT_SOURCE.glb OUT.glb
       (014: SHAPE = reference/originals/tripo-shape/014.glb, PRINT_SOURCE = reference/originals/print-source/014.glb)"""
import io, sys, numpy as np, trimesh, xatlas, fast_simplification
from PIL import Image
from scipy import ndimage
from scipy.ndimage import gaussian_filter1d
from scipy.spatial import cKDTree
from garment import Garment
from glb_patch import write
from metric import body

BODY = .008       # mannequin skin: closer than this to the body above the crotch
FEET = .11        # below this, the sneakers: the generated hem wrapped them up to the instep (a boot cover); cut above
CROTCH = .83      # the neutral body's crotch
HAND = .03        # cloth within this of a hand (|x| > ARM_X, below ARM_TOP) is the hand fused to the hip
ARM_X, ARM_TOP = .19, 1.3
TORSO_X = .165    # the arm starts past this (the gap between torso and arm runs from .14-.16 to .17-.21 m up to 1.3 m)
TOP = 1.04        # waistband top (the piece it replaces reached 1.031)
SPLIT = .80       # below this each leg's axis moves onto the body's
BLEND = (.74, .92)   # print frame: each leg's axis below the first, the hip's above the second
BAND = .05        # metres of arc around the stripes that keep their length (the rest of the girth takes the difference)
MAP = (1024, 2048)   # unrolled print of the old cloth: rows (height) by columns (angle)
KNEE = (.72, .48)  # leg axis: untouched above the first, onto the body's below the second
PART = (.004, .003)   # each leg this far from x = 0 (soft over the second value)
PART_Y = (.62, .74)   # parted fully below the first height, not above the second
GATHER = (.012, .72, 1.0)   # waistband gap, from where to where (a short ramp left the hip wider than the waist: a step)
SLACK = .004
ANKLE = .25       # below this the gap is eased against the leg above the sneaker
GAP = (.026, .009)  # gap eased from the first value towards the sum: penetration.py does not let the gap above 4 cm grow
FACES = 14000     # garment budget: 16 000 (site/integrity.test.ts)
TEX = 1024
STRIPES = np.radians([-70, 30])   # where the source's side stripes are, from the outer side (front positive)
WHITE = 150       # the stripes: every channel above this
SOURCE_HEM = .16  # the source's lowest rows (relative height) fold over the shoe: stripes sideways, the shoe's colours
SMUDGE_T = .7     # below this relative height (the crotch) white off the stripes is a smudge


def load(path, faces=60000):
    s = trimesh.load(path, process=False)
    m = trimesh.util.concatenate(list(s.dump())) if isinstance(s, trimesh.Scene) else s
    m = trimesh.Trimesh(m.vertices, m.faces)
    return simplify(m, faces)


def simplify(m, faces):
    if len(m.faces) > faces:
        v, f = fast_simplification.simplify(m.vertices, m.faces, 1 - faces / len(m.faces))
        m = trimesh.Trimesh(v, f)
    return m


def align(m, B):
    v = m.vertices.copy()
    v = (v - [0, v[:, 1].min(), 0]) * (B.vertices[:, 1].max() / np.ptp(v[:, 1]))
    v[:, [0, 2]] -= v[:, [0, 2]].mean(0) - B.vertices[:, [0, 2]].mean(0)
    torso = B.vertices[B.vertices[:, 1] > 1.1]; tree = cKDTree(torso); c = B.vertices[:, [0, 2]].mean(0)
    best = None
    for k in range(4):
        R = trimesh.transformations.rotation_matrix(k * np.pi / 2, [0, 1, 0])
        w = v.copy(); w[:, [0, 2]] -= c; w = (np.c_[w, np.ones(len(w))] @ R.T)[:, :3]; w[:, [0, 2]] += c
        d = tree.query(w[w[:, 1] > 1.1])[0].mean()
        if best is None or d < best[0]: best = (d, w)
    v = best[1]
    M, _, _ = trimesh.registration.icp(v[v[:, 1] > 1.1], torso, max_iterations=60, scale=True, reflection=False)
    return trimesh.Trimesh((np.c_[v, np.ones(len(v))] @ M.T)[:, :3], m.faces, process=False)


def keep(m, faces):
    m = trimesh.Trimesh(m.vertices, m.faces[faces], process=False)
    m.remove_unreferenced_vertices()
    return max(m.split(only_watertight=False), key=lambda p: p.area)


def without_mannequin(m, B):
    c = m.triangles_center
    q, d, _ = trimesh.proximity.closest_point(B, c)
    outside = trimesh.proximity.signed_distance(B, c) < 0
    hand = (np.abs(q[:, 0]) > ARM_X) & (q[:, 1] < ARM_TOP) & (d < HAND)
    drop = ((d < BODY) | ~outside) & (c[:, 1] > CROTCH) | (c[:, 1] < FEET) | hand | (c[:, 1] > TOP)
    return keep(m, ~drop)


def loops(m):
    """Boundary loops, as vertex index arrays."""
    e = m.edges[trimesh.grouping.group_rows(m.edges_sorted, require_count=1)]
    g = trimesh.graph.nx.Graph(); g.add_edges_from(e)
    return [np.array(list(c)) for c in trimesh.graph.nx.connected_components(g)]


def fill_holes(m):
    """Closes every boundary loop but the waistband (the highest) and the two hems (the lowest): a fan from the loop's
    centre, then the new vertex and the loop's ring settle (Laplacian)."""
    L = sorted(loops(m), key=lambda l: m.vertices[l, 1].mean())
    holes = L[2:-1]
    V, F = list(m.vertices), list(m.faces)
    for l in holes:
        e = m.edges[trimesh.grouping.group_rows(m.edges_sorted, require_count=1)]
        e = e[np.isin(e[:, 0], l) & np.isin(e[:, 1], l)]
        c = len(V); V.append(m.vertices[l].mean(0))
        for a, b in e: F.append([b, a, c])   # boundary edges run the other way in the hole's triangle
    out = trimesh.Trimesh(np.array(V), np.array(F), process=False)
    trimesh.repair.fix_winding(out)
    print(f'holes filled: {len(holes)}')
    return out


def level_hem(m):
    """The hem cut through the sneakers is jagged: below the 80th percentile of each hem loop, vertices rise to it."""
    V = m.vertices.copy()
    for l in sorted(loops(m), key=lambda l: m.vertices[l, 1].mean())[:2]:
        line = np.percentile(V[l, 1], 80); side = np.sign(V[l, 0].mean())
        k = (np.sign(V[:, 0]) == side) & (V[:, 1] < line)
        V[k, 1] = line
    top = sorted(loops(m), key=lambda l: m.vertices[l, 1].mean())[-1]
    V[top, 1] = np.median(V[top, 1])
    return trimesh.Trimesh(V, m.faces, process=False)


def axes(V, ys, leg):
    """(x, z) centre of the bounding box of each 2 cm slice; leg = 1, -1 (side in x) or 0 (both)."""
    out = np.full((len(ys), 2), np.nan)
    for i, y in enumerate(ys):
        k = (np.abs(V[:, 1] - y) < .01) & ((V[:, 0] * leg > 0) if leg else True)
        if k.sum() > 3: out[i] = (V[k][:, [0, 2]].min(0) + V[k][:, [0, 2]].max(0)) / 2
    ok = ~np.isnan(out[:, 0])
    for j in range(2): out[:, j] = np.interp(ys, ys[ok], out[ok, j])
    return out


def center_legs(m, B):
    V = m.vertices.copy(); ys = np.arange(0, SPLIT, .01)
    legs = B.vertices[(np.abs(B.vertices[:, 0]) < .16) & (B.vertices[:, 1] > .08)]
    w = np.clip((KNEE[0] - ys) / (KNEE[0] - KNEE[1]), 0, 1); w = w * w * (3 - 2 * w)
    for s in (1, -1):
        d = gaussian_filter1d(axes(legs, ys, s) - axes(V, ys, s), 4, axis=0) * w[:, None]
        k = V[:, 0] * s > 0
        for j, c in ((0, 0), (1, 2)): V[k, c] += np.interp(V[k, 1], ys, d[:, j], right=0)
    return trimesh.Trimesh(V, m.faces, process=False)


def side(m):
    """Leg of each vertex (1, -1): the nearer, along the cloth, of the vertices clearly on each side (more than 7 cm from
    the middle). The sign of x fails where the inner walls crossed the middle."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import dijkstra
    E = m.edges_unique; L = m.edges_unique_length; n = len(m.vertices)
    G = coo_matrix((L, (E[:, 0], E[:, 1])), shape=(n, n)).tocsr()
    d = [dijkstra(G, directed=False, indices=np.flatnonzero((m.vertices[:, 0] * s > .07) & (m.vertices[:, 1] < PART_Y[1])), min_only=True)
         for s in (1, -1)]
    return np.where(d[0] <= d[1], 1., -1.)


def part_legs(m):
    """The wide legs of the generated trousers stand on legs 4-6 cm apart: below the knee the inner walls met and crossed
    (2 cm at the ankle), and from the side the wall of one leg showed through the other, back faces that the site
    does not draw. Each leg keeps to its side of x = 0 by PART: a soft floor on the distance to the middle, full below
    the first height of PART_Y and none above the second."""
    V = m.vertices.copy(); s = side(m)
    u = s * V[:, 0]; gap, soft = PART
    floor = gap + soft * np.logaddexp(0, (u - gap) / soft)
    w = smooth((PART_Y[1] - V[:, 1]) / (PART_Y[1] - PART_Y[0]))
    V[:, 0] = s * (u + (floor - u) * w)
    print(f'legs parted: {(u < gap).sum()} vertices across the middle')
    return trimesh.Trimesh(V, m.faces, process=False)


def gather(m, T):
    gap, lo, hi = GATHER
    V = m.vertices.copy()
    q, d, _ = trimesh.proximity.closest_point(T, V)
    w = np.clip((V[:, 1] - lo) / (hi - lo), 0, 1); w = w * w * (3 - 2 * w)
    new = np.where(d > gap, gap + (d - gap) * (1 - w), d)
    return trimesh.Trimesh(q + (V - q) * (new / np.maximum(d, 1e-9))[:, None], m.faces, process=False)


def ease_gap(m, T):
    """Below the waistband, cloth farther than GAP[0] from the body comes closer, easing towards GAP[0] + GAP[1] (under
    4 cm): the wide legs of the generated trousers stood up to 6 cm off the shin, above the gap of the piece they
    replace (tools/fit/penetration.json only lets it go down). Below ANKLE the gap is to the leg, not to the sneaker."""
    (a, b), V = GAP, m.vertices.copy()
    q, d, _ = trimesh.proximity.closest_point(T, V)
    low = V[:, 1] < ANKLE   # near the hem the nearest body is the sneaker: the hem flared over it, far from the ankle
    leg = T.submesh([np.flatnonzero(T.triangles_center[:, 1] > FEET)], append=True)
    q[low], d[low], _ = trimesh.proximity.closest_point(leg, V[low])
    new = np.where(d > a, a + b * (1 - np.exp(-(d - a) / b)), d)
    return trimesh.Trimesh(q + (V - q) * (new / np.maximum(d, 1e-9))[:, None], m.faces, process=False)


def push_out(m, T, rounds=8):
    V = m.vertices.copy(); nb = m.vertex_neighbors
    for _ in range(rounds):
        q, _, t = trimesh.proximity.closest_point(T, V)
        n = T.face_normals[t]; inside = np.einsum('ij,ij->i', V - q, n) < SLACK
        D = np.zeros_like(V); D[inside] = q[inside] + n[inside] * SLACK - V[inside]
        for _ in range(3):
            D = np.array([D[i] if inside[i] else D[v].mean(0) * .5 for i, v in enumerate(nb)])
        V += D
    return trimesh.Trimesh(V, m.faces, process=False)


def drop_crumbs(m, limit=20.):
    """After simplification, bits joined to the piece only by a vertex or by an edge of 3 faces or more: removed below
    islands.ISLAND_CM2, the same rule as site/fit.test.ts (the edges must have exactly 2 faces)."""
    lab = trimesh.graph.connected_component_labels(m.face_adjacency, len(m.faces))
    area = np.bincount(lab, m.area_faces) * 1e4
    drop = area < limit; drop[np.argmax(area)] = False
    out = trimesh.Trimesh(m.vertices, m.faces[~drop[lab]], process=False); out.remove_unreferenced_vertices()
    print(f'crumbs removed: {drop.sum()} ({area[drop].sum():.1f} cm²)')
    return out


def without_arms(B):
    """The body without the arms, for gather and push_out: the nearest body point of the waistband's side was the
    forearm, and the waistband went to it in a flap."""
    c = B.triangles_center
    return trimesh.Trimesh(B.vertices, B.faces[(np.abs(c[:, 0]) < TORSO_X) | (c[:, 1] > ARM_TOP)], process=False)


def print_source(path):
    g = Garment(path); old = g.mesh()
    uv = np.vstack([np.array(_uv(g, p)) for _, _, p in g.parts])
    img = g.js['images'][[i for i, im in enumerate(g.js['images']) if not im.get('name', '').startswith('Normal')][0]]
    v = g.js['bufferViews'][img['bufferView']]; o = v.get('byteOffset', 0)
    return old, uv, np.array(Image.open(io.BytesIO(bytes(g.bin[o:o + v['byteLength']]))).convert('RGB'))


def _uv(g, p):
    from glb_patch import accessor_view
    import struct
    a, start, stride = accessor_view(g.js, g.bin, p['attributes']['TEXCOORD_0'])
    stride = g.js['bufferViews'][a['bufferView']].get('byteStride', 8)
    return [struct.unpack_from('<2f', g.bin, start + i * stride) for i in range(a['count'])]


def smooth(x):
    x = np.clip(x, 0, 1)
    return x * x * (3 - 2 * x)


class Frame:
    """Cylindrical coordinates of a piece, one frame per side (s = 1, -1): relative height t (hem to waistband), angle
    phi around the axis measured from the outer side (front positive, both sides alike) and the radius r. The axis is
    each leg's below BLEND[0], the hip's above BLEND[1], and blends between them: one continuous angle, no seam where
    the hip meets the legs."""
    def __init__(self, V):
        self.y0, self.y1 = V[:, 1].min(), V[:, 1].max()
        self.ys = np.arange(self.y0 - .01, self.y1 + .02, .01)
        w = smooth((self.ys - BLEND[0]) / (BLEND[1] - BLEND[0]))[:, None]
        hip = axes(V, self.ys, 0)
        self.c = {s: axes(V, self.ys, s) * (1 - w) + hip * w for s in (1, -1)}
        self.R = {}
        for s in (1, -1):
            k = V[:, 0] * s > 0; _, _, r = self.polar(V[k], s)
            self.R[s] = np.array([np.median(r[np.abs(V[k, 1] - y) < .01]) if (np.abs(V[k, 1] - y) < .01).sum() > 3 else np.nan
                                  for y in self.ys])
            ok = ~np.isnan(self.R[s]); self.R[s] = np.interp(self.ys, self.ys[ok], self.R[s][ok])

    def polar(self, P, s):
        cx, cz = (np.interp(P[:, 1], self.ys, self.c[s][:, j]) for j in (0, 1))
        dx, dz = s * (P[:, 0] - cx), P[:, 2] - cz
        return (P[:, 1] - self.y0) / (self.y1 - self.y0), np.arctan2(dz, dx), np.hypot(dx, dz)

    def radius(self, t, s):
        return np.interp(self.y0 + t * (self.y1 - self.y0), self.ys, self.R[s])


def turn(phi, an, ao, c):
    """Angle on the old cloth for the angle phi on the new one: around the outer side, a band of BAND metres keeps its
    length (the stripes keep their width: the new legs are wider) and its middle goes to c, where the stripes of that
    row of the source are (21-24° behind the side seam, wavering from row to row: each row taken from its own centre,
    the stripes come out straight on the side, as in the photo); the front and back centres (±90°) and the inner side
    (±180°) stay put. Monotone and continuous, piecewise linear between those points."""
    one = np.ones_like(phi)
    P = np.stack([-np.pi * one, -np.pi / 2 * one, -an, 0 * one, an, np.pi / 2 * one, np.pi * one], 1)
    Q = np.stack([-np.pi * one, -np.pi / 2 * one, c - ao, c, c + ao, np.pi / 2 * one, np.pi * one], 1)
    i = np.clip((P[:, 1:-1] <= phi[:, None]).sum(1), 0, 5); r = np.arange(len(phi))
    a, b = P[r, i], P[r, i + 1]; f = np.clip((phi - a) / np.maximum(b - a, 1e-9), 0, 1)
    return Q[r, i] + f * (Q[r, i + 1] - Q[r, i])


def stripes(cmap):
    """Per row of the unrolled print, the angle of the middle of the side stripes (the white within STRIPES of the outer
    side), lightly smoothed; rows without them take the neighbours'."""
    NT, NA = cmap.shape[:2]; a = np.linspace(-np.pi, np.pi, NA)
    w = (cmap.min(2) > WHITE) & (a >= STRIPES[0]) & (a <= STRIPES[1])
    n = w.sum(1); c = np.where(n > 3, (w * a).sum(1) / np.maximum(n, 1), np.nan)
    ok = ~np.isnan(c)
    if not ok.any(): return np.zeros(NT)
    c = np.interp(np.arange(NT), np.flatnonzero(ok), c[ok])
    return gaussian_filter1d(c, 3)


def print_map(old, uv, img, F, s):
    """The old cloth of side s unrolled: rows are the relative height, columns the angle from -180 to 180°; each cell
    keeps the outermost layer (largest radius), with the colour of the old texture at that point (bilinear). Only the
    faces on that side of x = 0: the other leg's stripes never reach this one. Cells no face covers take the nearest."""
    NT, NA = MAP
    k = old.triangles_center[:, 0] * s > 0
    t, a, r = F.polar(old.vertices, s)
    X = np.c_[t * (NT - 1), (a + np.pi) / (2 * np.pi) * (NA - 1)]
    depth = np.full(NT * NA, -1.); face = np.full(NT * NA, -1); bary = np.zeros((NT * NA, 3))
    for f in np.flatnonzero(k):
        tri = old.faces[f]; x = X[tri]
        if np.ptp(x[:, 1]) > NA / 2: continue    # wraps round the inner side
        lo = np.floor(x.min(0)).astype(int); hi = np.ceil(x.max(0)).astype(int)
        gy, gx = np.meshgrid(np.arange(lo[0], hi[0] + 1), np.arange(lo[1], hi[1] + 1), indexing='ij')
        gy, gx = gy.ravel(), gx.ravel(); ok = (gy >= 0) & (gy < NT) & (gx >= 0) & (gx < NA); gy, gx = gy[ok], gx[ok]
        T = np.c_[x, [0, 0, 0]]
        with np.errstate(all='ignore'):
            bc = trimesh.triangles.points_to_barycentric(np.repeat(T[None], len(gy), 0), np.c_[gy, gx, np.zeros(len(gy))])
        ok = (bc >= -1e-6).all(1) & np.isfinite(bc).all(1); bc, cell = bc[ok], gy[ok] * NA + gx[ok]
        d = bc @ r[tri]; better = d > depth[cell]
        cell, d, bc = cell[better], d[better], bc[better]
        depth[cell] = d; face[cell] = f; bary[cell] = bc
    got = face >= 0
    u = np.einsum('ij,ijk->ik', bary[got], uv[old.faces[face[got]]])
    col = np.zeros((NT * NA, 3)); col[got] = bilinear(img, u)
    _, (iy, ix) = ndimage.distance_transform_edt(~got.reshape(NT, NA), return_indices=True)
    return col.reshape(NT, NA, 3)[iy, ix], got.mean()


def bilinear(img, u):
    h, w = img.shape[:2]
    x = (u[:, 0] % 1) * w - .5; y = (u[:, 1] % 1) * h - .5
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int); fx, fy = (x - x0)[:, None], (y - y0)[:, None]
    g = lambda yy, xx: img[np.clip(yy, 0, h - 1), np.clip(xx, 0, w - 1)].astype(float)
    return (g(y0, x0) * (1 - fx) + g(y0, x0 + 1) * fx) * (1 - fy) + (g(y0 + 1, x0) * (1 - fx) + g(y0 + 1, x0 + 1) * fx) * fy


def clean(cmap):
    """White below the crotch away from the side stripes (a smudge on the shin of the right leg) is the generator's:
    the photo has none. It takes the colour of the nearest cloth around it."""
    NT, NA = cmap.shape[:2]; a = np.linspace(-np.pi, np.pi, NA); t = np.linspace(0, 1, NT)[:, None]
    smudge = (cmap.min(2) > WHITE) & ((a < STRIPES[0]) | (a > STRIPES[1])) & (t < SMUDGE_T)
    smudge = ndimage.binary_dilation(smudge, iterations=3)
    _, (iy, ix) = ndimage.distance_transform_edt(smudge, return_indices=True)
    return cmap[iy, ix]


def sample(old, uv, img, P, new):
    """Colour of each point P of the new piece at the same place of the old one's unrolled print (see the module
    docstring): same side, same relative height, the angle through turn()."""
    Fn, Fo = Frame(new.vertices), Frame(old.vertices)
    NT, NA = MAP; out = np.zeros((len(P), 3))
    for s in (1, -1):
        k = P[:, 0] * s > 0 if s == 1 else P[:, 0] <= 0
        cmap, cover = print_map(old, uv, img, Fo, s)
        cmap = clean(cmap)
        t, phi, _ = Fn.polar(P[k], s)
        t = np.maximum(t, SOURCE_HEM)   # below, the row above the fold carries on: the stripes run straight to the hem
        c = np.interp(np.clip(t, 0, 1) * (NT - 1), np.arange(NT), stripes(cmap))
        an = np.minimum(BAND / Fn.radius(t, s), np.pi / 2 - .05)
        ao = np.minimum(BAND / Fo.radius(t, s), np.pi / 2 - np.abs(c) - .05)
        a = turn(phi, an, ao, c)
        out[k] = bilinear(cmap, np.c_[(a + np.pi) / (2 * np.pi), np.clip(t, 0, 1 - 1e-6)])
        print(f'side {s:+d}: old cloth covers {cover * 100:.0f}% of its unrolled print')
    return np.clip(out, 0, 255).astype(np.uint8)


def bake(m, old, uv, img):
    vmap, idx, uvn = xatlas.parametrize(m.vertices, m.faces)
    V = m.vertices[vmap]; P, K = [], []
    for f, t in enumerate(uvn[idx]):
        lo = np.floor(t.min(0) * TEX).astype(int); hi = np.ceil(t.max(0) * TEX).astype(int)
        gx, gy = np.meshgrid(np.arange(lo[0], hi[0] + 1), np.arange(lo[1], hi[1] + 1))
        gx, gy = gx.ravel().clip(0, TEX - 1), gy.ravel().clip(0, TEX - 1)
        T = np.c_[t, [0, 0, 0]]
        with np.errstate(all='ignore'):
            bc = trimesh.triangles.points_to_barycentric(np.repeat(T[None], len(gx), 0),
                                                         np.c_[(gx + .5) / TEX, (gy + .5) / TEX, np.zeros(len(gx))])
        ok = (bc >= -.02).all(1)
        if ok.any(): P.append(bc[ok] @ V[idx[f]]); K.append(gy[ok] * TEX + gx[ok])
    P, K = np.vstack(P), np.concatenate(K)
    out = np.zeros((TEX * TEX, 3), np.uint8); done = np.zeros(TEX * TEX, bool)
    out[K] = sample(old, uv, img, P, m); done[K] = True
    _, (iy, ix) = ndimage.distance_transform_edt(~done.reshape(TEX, TEX), return_indices=True)   # bleed past the islands
    return V, idx, uvn, out.reshape(TEX, TEX, 3)[iy, ix]


def save(path, V, F, UV, image):
    """GLB in the site's format: one mesh, normals, UV (glTF: v down, as the texel rows), a WebP base colour."""
    N = trimesh.Trimesh(V, F, process=False).vertex_normals
    buf = io.BytesIO(); Image.fromarray(image).save(buf, 'WEBP', quality=90); webp = buf.getvalue()
    parts = [V.astype('<f4').tobytes(), N.astype('<f4').tobytes(), UV.astype('<f4').tobytes(), F.astype('<u4').tobytes(), webp]
    views, off, b = [], 0, b''
    for p in parts:
        views.append({'buffer': 0, 'byteOffset': off, 'byteLength': len(p)}); b += p + b'\0' * (-len(p) % 4); off = len(b)
    acc = lambda v, n, t, c, **k: {'bufferView': v, 'componentType': c, 'count': n, 'type': t, **k}
    js = {'asset': {'version': '2.0', 'generator': 'tools/fit/project_print.py'}, 'scene': 0, 'scenes': [{'nodes': [0]}],
          'nodes': [{'mesh': 0}], 'extensionsUsed': ['EXT_texture_webp'], 'extensionsRequired': ['EXT_texture_webp'],
          'meshes': [{'primitives': [{'attributes': {'POSITION': 0, 'NORMAL': 1, 'TEXCOORD_0': 2}, 'indices': 3, 'material': 0}]}],
          'accessors': [acc(0, len(V), 'VEC3', 5126, min=V.min(0).tolist(), max=V.max(0).tolist()), acc(1, len(V), 'VEC3', 5126),
                        acc(2, len(V), 'VEC2', 5126), acc(3, F.size, 'SCALAR', 5125)],
          'bufferViews': views[:3] + [views[3]] + [views[4]],
          'buffers': [{'byteLength': len(b)}],
          'images': [{'name': 'print', 'mimeType': 'image/webp', 'bufferView': 4}],
          'samplers': [{}], 'textures': [{'sampler': 0, 'extensions': {'EXT_texture_webp': {'source': 0}}}],
          'materials': [{'name': 'print', 'pbrMetallicRoughness': {'baseColorTexture': {'index': 0}, 'metallicFactor': 0,
                                                                   'roughnessFactor': .9}}]}
    write(path, js, bytearray(b))


def main(shape, source, out):
    B = body('C'); T = without_arms(B)
    m = without_mannequin(align(load(shape), B), B)
    m = level_hem(fill_holes(m))
    m = push_out(ease_gap(gather(part_legs(center_legs(m, B)), T), T), T)
    m = drop_crumbs(push_out(simplify(m, FACES), T, rounds=3))
    old, uv, img = print_source(source)
    V, F, UV, image = bake(m, old, uv, img)
    save(out, V, F, UV, image)
    print(f'{out}: {len(F)} triangles, top {V[:, 1].max():.3f} m, hem {V[:, 1].min():.3f} m')


if __name__ == '__main__':
    main(*sys.argv[1:4])
