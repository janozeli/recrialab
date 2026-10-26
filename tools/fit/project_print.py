"""Builds a bottom from a shape Tripo generated on the neutral mannequin and the print of the piece's earlier model.

The pants Tripo made from the shop photo came shaped on its own mannequin, with thinner legs: on the neutral body the
waist, hip and thigh of 014 sat inside the body (70, 46 and 17% of the area) and pulling the cloth out stretched the
print (known issue waist-014). Here the shape comes from a Tripo model generated on the neutral mannequin itself (three
views of the trousers dressed on renders of pose C, front, left and back, then multiview-to-model without texture),
and the print is painted on the final shape, so no later move stretches it:
  1. align: height, turn about y and ICP on the bare torso, which is the mannequin itself;
  2. remove the mannequin: what lies within BODY of the body above the crotch, the feet, and what the hands fused to
     the hip; keep the largest piece, cut above the waistband (TOP), fill the holes the hands leave and level the hem;
  3. shape: each leg's axis onto the body's leg from the knee down (the shin came 5 cm behind), the waistband gathered
     to GATHER from the waist (the elastic came 4.3 cm off all around), the gap eased under 4 cm (GAP), whatever is
     closer than SLACK pushed out;
  4. print: UV unwrap (xatlas) and each texel takes the colour of the print source at the same stripe: the same
     relative height (hem to waistband), the same angle around the leg axis (above the crotch, the hip axis), on the
     outer layer of the old cloth. The nearest point smeared the stripes: the new trousers are wider than the old.
     The source model has the stripes 21-24° behind the side seam, which on the wider legs shows them on the back
     and hides them from the front; the photo has them on the side, so the sides turn by TURN (TURN·cos θ: the
     centres of the front and back stay put).
The output is in the site's format (WebP texture, no normal map, single-sided like the piece it replaces) and is also
the stretch reference (reference/originals/tripo/NNN.glb): the print is laid on this shape, and stretch.py measures
what later tools move.
usage: python3 tools/fit/project_print.py SHAPE.glb PRINT_SOURCE.glb OUT.glb
       (014: SHAPE = reference/originals/tripo-shape/014.glb, PRINT_SOURCE = reference/originals/print-source/014.glb)"""
import io, json, sys, numpy as np, trimesh, xatlas, fast_simplification
from PIL import Image
from scipy import ndimage
from scipy.ndimage import gaussian_filter1d
from scipy.spatial import cKDTree
from trimesh.ray.ray_pyembree import RayMeshIntersector
from garment import Garment
from glb_patch import write
from metric import body

BODY = .008       # mannequin skin: closer than this to the body above the crotch
FEET = .07        # below this, the sneakers
CROTCH = .83      # the neutral body's crotch
HAND = .03        # cloth within this of a hand (|x| > ARM_X, below ARM_TOP) is the hand fused to the hip
ARM_X, ARM_TOP = .19, 1.3
TORSO_X = .165    # the arm starts past this (the gap between torso and arm runs from .14-.16 to .17-.21 m up to 1.3 m)
TOP = 1.04        # waistband top (the piece it replaces reached 1.031)
SPLIT = .80       # below this each leg has its own axis
KNEE = (.72, .48)  # leg axis: untouched above the first, onto the body's below the second
GATHER = (.012, .72, 1.0)   # waistband gap, from where to where (a short ramp left the hip wider than the waist: a step)
SLACK = .004
GAP = (.026, .009)  # gap eased from the first value towards the sum: penetration.py does not let the gap above 4 cm grow
FACES = 14000     # garment budget: 16 000 (site/integrity.test.ts)
TEX = 1024
TURN = np.radians(22)   # the print source has the stripes 21-24° behind the side seam; the photo shows them on the side


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
    replace (tools/fit/penetration.json only lets it go down)."""
    (a, b), V = GAP, m.vertices.copy()
    q, d, _ = trimesh.proximity.closest_point(T, V)
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


def sample(old, uv, img, P, new):
    """Colour of each point P of the new piece at the same stripe of the old one (see the module docstring)."""
    Vn, Vo = new.vertices, old.vertices
    n0, n1 = Vn[:, 1].min(), Vn[:, 1].max(); o0, o1 = Vo[:, 1].min(), Vo[:, 1].max()
    ys = np.arange(min(n0, o0), max(n1, o1) + .01, .01)
    yo = o0 + (P[:, 1] - n0) * (o1 - o0) / (n1 - n0)
    origin = np.zeros_like(P); dirs = np.zeros_like(P)
    for leg, k in ((0, P[:, 1] >= SPLIT), (1, (P[:, 1] < SPLIT) & (P[:, 0] > 0)), (-1, (P[:, 1] < SPLIT) & (P[:, 0] <= 0))):
        cn, co = axes(Vn, ys, leg), axes(Vo, ys, leg)
        th = np.arctan2(P[k, 2] - np.interp(P[k, 1], ys, cn[:, 1]), P[k, 0] - np.interp(P[k, 1], ys, cn[:, 0]))
        th = th - TURN * np.cos(th)   # sides turned, front and back centres (cos 0) unmoved: no seam at x = 0
        origin[k] = np.c_[np.interp(yo[k], ys, co[:, 0]), yo[k], np.interp(yo[k], ys, co[:, 1])]
        dirs[k] = np.c_[np.cos(th), np.zeros(k.sum()), np.sin(th)]
    loc, ir, it = RayMeshIntersector(old).intersects_location(origin, dirs, multiple_hits=True)
    d = np.einsum('ij,ij->i', loc - origin[ir], dirs[ir])
    tri = np.full(len(P), -1); hit = P.copy(); o = np.argsort(d)   # the farthest hit of each ray stays: the outer layer
    tri[ir[o]] = it[o]; hit[ir[o]] = loc[o]
    miss = tri < 0
    if miss.any():
        q, _, t = trimesh.proximity.closest_point(old, P[miss]); hit[miss] = q; tri[miss] = t
    bc = trimesh.triangles.points_to_barycentric(old.triangles[tri], hit)
    u = np.einsum('ij,ijk->ik', bc, uv[old.faces[tri]])
    h, w = img.shape[:2]
    x = np.clip((u[:, 0] % 1) * (w - 1), 0, w - 1).astype(int); y = np.clip((u[:, 1] % 1) * (h - 1), 0, h - 1).astype(int)
    print(f'texels found on the old cloth along the axis ray: {(~miss).mean() * 100:.0f}%')
    return img[y, x]


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
    m = push_out(ease_gap(gather(center_legs(m, B), T), T), T)
    m = drop_crumbs(push_out(simplify(m, FACES), T, rounds=3))
    old, uv, img = print_source(source)
    V, F, UV, image = bake(m, old, uv, img)
    save(out, V, F, UV, image)
    print(f'{out}: {len(F)} triangles, top {V[:, 1].max():.3f} m, hem {V[:, 1].min():.3f} m')


if __name__ == '__main__':
    main(*sys.argv[1:4])
