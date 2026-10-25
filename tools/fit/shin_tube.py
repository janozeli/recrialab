"""Rebuilds the shin of the pants whose legs Tripo stuck together: a new tube around the neutral body's leg.

On 013 and 011, separate_legs.py cuts the bridge between the legs, but from the ankle down to the sneaker the wall and
the leftovers of the bridge stay in the middle of the gap (tools/fit/cuff.py), a strip hanging down to the sneaker.
That cloth cannot be pulled onto the leg without stretching the print: it is fold over fold, layers the generator
invented.
Here, below TOP, the faces of each leg go away and a tube of rings every DY comes in: each ring is the section of the
body's leg (above SHOE) grown evenly to the perimeter of the old cloth at the same height (the gathering above the cuff
and the elastic), between the body's with SLACK and with WIDE. The edge left behind is the first ring (same position):
no tear. The tube has its own texture (TEXEL per leg, cylindrical UV, material shin-NNN without a normal map): each
texel looks, from the leg axis outward, at the outer layer of the old cloth at the same height and copies its colour,
and the print (the letters of 011) stays continuous around the leg, which copying the old cloth's UV triangle by
triangle would break. Refuses (writes nothing) if more than MAX_MISS of the texels find no old cloth
along the ray. The original gets the same tube, and pant_leg_cloth.py measures the stretch from there.
The material name shin-NNN is stored in the published GLBs; stretch.py recognizes the tube by it.
usage: python3 tools/fit/shin_tube.py ORIGINAL_SEP.glb IN_SEP.glb ORIGINAL_SHIN.glb IN_SHIN.glb NNN   (between separate_legs.py
       and leg_shape.py --again: separate, shin, legs, dress)"""
import sys, io, json, numpy as np, trimesh
from PIL import Image
from glb_patch import write
from scipy.spatial import cKDTree, ConvexHull
from garment import Garment
from separate_legs import rewrite, leg_side
from pant_leg_cloth import uvs, weld
from metric import body, POSE_C

TOP = .30            # from the knee down (at 0.30 m the wall of separate_legs.py is 2 cm; below it the strip grows)
DY = .01             # between rings
SHOE = .17           # below this the body is the sneaker: the ring follows the ankle section
SLACK = .008         # cuff slack around the ankle
MARGIN = .002        # from the tube's UV to the edge of its half of the image (filtering does not pull in the other leg)
MAX_MISS = .35       # texels with no old cloth along the ray, coloured from the nearest old triangle (011 14 to 16%, 013 29%)
TEXEL = (128, 256)   # texture of each leg's tube: height x around (px)
WIDE = .03           # never wider than this around the leg (penetration.py counts the gap above 4 cm)


def edge_loop(FF, X, s, side):
    """Loop of the lower edge of leg s after the cut (welded vertices, in order)."""
    e = np.sort(np.vstack([FF[:, [0, 1]], FF[:, [1, 2]], FF[:, [2, 0]]]), 1)
    u, c = np.unique(e, axis=0, return_counts=True); b = u[c == 1]
    b = b[(side[b] == s).all(1) & (X[b, 1].max(1) < TOP + .05)]
    cs = sorted(trimesh.graph.connected_components(b, min_len=3), key=len, reverse=True)
    nodes = set(cs[0]); nb = {}
    for i, j in b:
        if i in nodes: nb.setdefault(i, []).append(j); nb.setdefault(j, []).append(i)
    assert all(len(v) == 2 for v in nb.values()), f'side {s}: the cut edge is not a simple loop'
    loop = [cs[0][0]]; prev = -1
    while True:
        p = [n for n in nb[loop[-1]] if n != prev][0]
        if p == loop[0]: break
        prev = loop[-1]; loop.append(p)
    return np.array(loop)


def around(Q, c):
    """Order of the points Q (xz) around c from the front (+z), in a fixed direction, and the arc fraction of each."""
    a = np.arctan2(Q[:, 0] - c[0], Q[:, 1] - c[1])
    k = int(np.argmin(np.abs(a)))
    o = np.r_[np.arange(k, len(Q)), np.arange(k)]
    if np.sin(a[o[1]] - a[o[0]]) < 0: o = np.r_[o[0], o[1:][::-1]]   # growing angle
    Q = Q[o]; s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(np.vstack([Q, Q[:1]]), axis=0), axis=1))]
    return o, s[:-1] / s[-1], s[-1]


def section(b, y, s):
    """Section of the body's leg s at height y (xz, closed) and its center."""
    for l in b.section([0, 1, 0], [0, max(y, SHOE), 0]).discrete:
        if l[:, 0].mean() * s > 0 and len(l) > 8:
            Q = l[:-1][:, [0, 2]] if np.allclose(l[0], l[-1]) else l[:, [0, 2]]
            return Q, Q.mean(0)
    raise ValueError(f'leg {s} has no section at {y}')


def perimeter(Q):
    return np.linalg.norm(np.diff(np.vstack([Q, Q[:1]]), axis=0), axis=1).sum()


def grow(Q, c, per):
    """Q grown along the normal up to perimeter per."""
    n = Q - c; n /= np.linalg.norm(n, axis=1, keepdims=True)
    p = lambda d: perimeter(Q + d * n)
    lo, hi = -.01, .2
    for _ in range(40):
        m = (lo + hi) / 2; lo, hi = (m, hi) if p(m) < per else (lo, m)
    return Q + lo * n


def sample(Q, c, t):
    """Points of Q (closed) at the arc fractions t, from the front."""
    o, tq, _ = around(Q, c); Q = Q[o]
    Qc = np.vstack([Q, Q[:1]]); tq = np.r_[tq, 1]
    return np.c_[np.interp(t, tq, Qc[:, 0]), np.interp(t, tq, Qc[:, 1])]


def shin(orig, src, dst_orig, dst_src, pid):
    go = Garment(orig); Po = go.vertices()
    g = Garment(src); P = g.vertices(); assert len(P) == len(Po), 'original and input with different meshes (separate_legs.py)'
    F = g.mesh(P).faces; UV = np.vstack(uvs(g))
    X, inv, FF = weld(P, F); side = leg_side(X, FF)
    b = body('C' if pid in POSE_C else 'B')
    out = (X[FF, 1].max(1) < TOP) & (side[FF] == side[FF][:, :1]).all(1)
    old = trimesh.Trimesh(P, F[out], process=False)   # the cloth that goes away (where the colour comes from)
    plain = (UV[F] == UV[F][:, :1]).all((1, 2))
    fv = np.flatnonzero(out); sidef = side[FF[out, 0]]
    keep = ~out; Fk, FFk = F[keep], FF[keep]
    newP, newO, newUV, newF, imgs = [], [], [], [], []
    nfp = [g.js['accessors'][p['indices']]['count'] // 3 for _, _, p in g.parts]
    materials = np.repeat([p.get('material', 0) for _, _, p in g.parts], nfp)
    textures = {m: material_texture(g, m) for m in np.unique(materials)}
    rep = np.zeros(inv.max() + 1, int); rep[inv[::-1]] = np.arange(len(inv))[::-1]   # one mesh vertex per welded one
    base = len(P)
    for s in (1, -1):
        loop = edge_loop(FFk, X, s, side)
        Lp = X[loop]; c0 = Lp[:, [0, 2]].mean(0)
        o, t, _ = around(Lp[:, [0, 2]], c0); loop = loop[o]
        per0 = ConvexHull(Lp[:, [0, 2]]).area   # perimeter of the edge without the zigzag (in 2D, area is the perimeter)
        src_faces = (sidef == s) & ~plain[fv]   # the colour comes from the printed cloth, not from the plain-colour walls
        source = old.submesh([np.flatnonzero(src_faces)], append=True)
        fface = fv[src_faces]
        y0 = X[loop, 1].mean(); y1 = X[FF[out][sidef == s], 1].min()
        ys = np.arange(y0 - DY, y1 - 1e-6, -DY); ys = np.r_[ys, y1] if ys[-1] - y1 > DY / 2 else ys
        # perimeter of each ring: the old cloth's at the same height (the gathering above the cuff and the elastic),
        # between the body's with SLACK and the edge's; at both ends, the edge and the old cloth's cuff
        def hull(y):
            try:
                V = source.section([0, 1, 0], [0, y, 0]).vertices[:, [0, 2]]; return ConvexHull(V).area
            except Exception: return np.nan
        perv = np.array([hull(y) for y in ys]); ok = ~np.isnan(perv)
        perv = np.interp(ys, ys[ok][::-1], perv[ok][::-1])
        pc = np.array([perimeter(section(b, y, s)[0]) for y in ys]); snug, wide = pc + 2 * np.pi * SLACK, pc + 2 * np.pi * WIDE
        target_p = np.convolve(np.r_[per0, np.clip(perv, snug, per0), perv[-1:].clip(snug[-1:])], np.ones(3) / 3, 'valid')
        target_p = np.clip(target_p, snug, wide)
        rings = [X[loop]]
        for y, pa in zip(ys, target_p):
            Qb, cb = section(b, y, s)
            Q = sample(grow(Qb, cb, pa), cb, t)
            rings.append(np.c_[Q[:, 0], np.full(len(Q), y), Q[:, 1]])
        A = np.stack(rings); R, n = A.shape[:2]
        Ao = A.copy(); Ao[0] = Po[rep[loop]]   # on the original, the first ring sits where its edge is (pant_leg_cloth.py's weld)
        if not np.cross(A[1, 1] - A[0, 0], A[1, 0] - A[0, 0]) @ (A[0, 0] - A[0].mean(0)) > 0:   # normal pointing out of the leg
            A, Ao = A[:, ::-1], Ao[:, ::-1]
        # the tube's own texture (cylindrical UV): each texel looks, from the leg axis outward, at the outer layer of
        # the old cloth at the same height and copies its colour; the print stays continuous around the leg
        Ac = np.concatenate([A, A[:, :1]], 1); Aoc = np.concatenate([Ao, Ao[:, :1]], 1)   # column repeated at the seam
        side_i = len(newP); u0 = .5 * side_i
        tc = np.r_[0, np.cumsum(np.linalg.norm(np.diff(Ac, axis=1), axis=2), 1).mean(0)]; tc /= tc[-1]
        U = np.stack(np.meshgrid(u0 + MARGIN + tc * (.5 - 2 * MARGIN), MARGIN + np.linspace(0, 1, R) * (1 - 2 * MARGIN)), 2)
        img = bake(Ac, tc, source, UV[F[fface]], textures, materials[fface])
        imgs.append(img)
        k = np.arange(R * (n + 1)).reshape(R, n + 1)
        quads = np.stack([k[:-1, :-1], k[:-1, 1:], k[1:, 1:], k[1:, :-1]], 2).reshape(-1, 4)
        tris = np.r_[quads[:, [0, 1, 2]], quads[:, [0, 2, 3]]] + sum(len(p) for p in newP)
        newP.append(Ac.reshape(-1, 3)); newO.append(Aoc.reshape(-1, 3)); newUV.append(U.reshape(-1, 2)); newF.append(tris)
        print(f'side {s:+d}: edge of {n} vertices at {y0:.3f} m (perimeter {100 * per0:.1f} cm), {R - 1} rings down to '
              f'{y1:.3f} m (cuff {100 * target_p[-1]:.1f} cm)')
    # vertices with no face after the cut go away (the order of the rest does not change: stretch.match only walks forward)
    nv = g.sizes
    fprim = np.repeat(np.arange(len(nfp)), nfp)[keep]
    used = np.zeros(len(P), bool); used[Fk] = True
    new = np.cumsum(used) - 1; lim = np.cumsum([0] + nv)
    nv2 = [int(used[lim[i]:lim[i + 1]].sum()) for i in range(len(nv))]
    nf2 = [int((fprim == i).sum()) for i in range(len(nfp))]
    Fk2 = new[Fk]
    pr = int(np.bincount(np.repeat(np.arange(len(nfp)), nfp)[out]).argmax())   # the tube goes on the mesh of the cloth that left
    tP, tO, tUV, tF = np.vstack(newP), np.vstack(newO), np.vstack(newUV), np.vstack(newF)
    img = Image.fromarray(np.concatenate(imgs, 1))
    print(f'{pid}: {out.sum()} triangles out, {len(tF)} in; tube texture {img.size[0]} x {img.size[1]} px')
    for gg, Pk, Pt, dst in ((g, P[used], tP, dst_src), (go, Po[used], tO, dst_orig)):   # the original gets the same tube
        rewrite(gg, Pk, UV[used], Fk2, [], dst, nf=nf2, nv=nv2)
        attach(dst, Pk, Fk2, Pt, tUV, tF, img, pr, pid)


def material_texture(g, m):
    """Colour image of material m (RGB)."""
    js = g.js; t = js['textures'][js['materials'][m]['pbrMetallicRoughness']['baseColorTexture']['index']]
    v = js['bufferViews'][js['images'][t.get('source', t.get('extensions', {}).get('EXT_texture_webp', {}).get('source'))]['bufferView']]
    o = v.get('byteOffset', 0)
    return np.asarray(Image.open(io.BytesIO(bytes(g.bin[o:o + v['byteLength']]))).convert('RGB'), float)


def bake(Ac, tc, source, Uf, textures, mats):
    """Colour of each texel of the tube (rows: rings from top to bottom; columns: around, from tc 0 to 1)."""
    R = len(Ac); H, W = TEXEL
    rr = np.linspace(0, R - 1, H); cc = np.linspace(0, 1, W)
    i0 = np.clip(np.floor(rr).astype(int), 0, R - 2); fr = (rr - i0)[:, None, None]
    lin = Ac[i0] * (1 - fr) + Ac[i0 + 1] * fr                       # H x (n+1) x 3
    pts = np.stack([np.stack([np.interp(cc, tc, lin[h, :, k]) for k in range(3)], 1) for h in range(H)])   # H x W x 3
    cen = lin[:, :-1].mean(1)
    org = np.repeat(cen[:, None], W, 1).reshape(-1, 3); d = pts.reshape(-1, 3) - org; d[:, 1] = 0
    d /= np.linalg.norm(d, axis=1, keepdims=True) + 1e-12
    loc, ri, tri = source.ray.intersects_location(org, d, multiple_hits=True)
    target = np.full(len(org), -1); dist = np.full(len(org), -1.); hit = np.zeros_like(org)
    for p_, r_, t_ in zip(loc, ri, tri):
        dd = np.linalg.norm(p_ - org[r_])
        if dd > dist[r_]: dist[r_], target[r_], hit[r_] = dd, t_, p_
    miss = target < 0
    if miss.any():   # a hole in the old cloth: the triangle nearest to the tube point
        _, target[miss] = cKDTree(source.triangles_center).query(pts.reshape(-1, 3)[miss])
        hit[miss] = source.triangles_center[target[miss]]
    bc = trimesh.triangles.points_to_barycentric(source.triangles[target], hit)
    uv = np.einsum('ij,ijk->ik', bc, Uf[target])
    colour = np.zeros((len(org), 3))
    for m, tex in textures.items():
        k = mats[target] == m
        if k.any(): colour[k] = bilinear(tex, uv[k])
    print(f'  texture: {miss.mean() * 100:.0f}% of texels with no old cloth along the ray (the nearest one)')
    if miss.mean() > MAX_MISS: sys.exit(f'tube texture: {miss.mean() * 100:.0f}% with no old cloth along the ray; nothing written')
    return np.clip(colour.reshape(H, W, 3), 0, 255).astype(np.uint8)


def bilinear(tex, uv):
    h, w = tex.shape[:2]   # glTF: v grows downward in the image
    x = (uv[:, 0] % 1) * w - .5; y = (uv[:, 1] % 1) * h - .5
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int); fx, fy = (x - x0)[:, None], (y - y0)[:, None]
    at = lambda yy, xx: tex[yy % h, xx % w]
    return (at(y0, x0) * (1 - fx) * (1 - fy) + at(y0, x0 + 1) * fx * (1 - fy) + at(y0 + 1, x0) * (1 - fx) * fy
            + at(y0 + 1, x0 + 1) * fx * fy)


def attach(dst, Pk, Fk, Pt, UVt, Ft, img, pr, pid):
    """Puts the tube in a new primitive of primitive pr's mesh, with its own material (the baked texture, without a
    normal map: the garment's follows another UV). Normals smoothed together with the garment's edge."""
    g = Garment(dst); js, b = g.js, bytearray(g.bin)
    _, M, p0 = g.parts[pr]
    mesh = next(m for m in js['meshes'] if any(q is p0 for q in m['primitives']))
    X = np.vstack([Pk, Pt]); F = np.vstack([Fk, Ft + len(Pk)])
    _, inv = np.unique(np.round(X, 5), axis=0, return_inverse=True); inv = inv.ravel()
    fn = np.cross(X[F[:, 1]] - X[F[:, 0]], X[F[:, 2]] - X[F[:, 0]])
    acc = np.zeros((inv.max() + 1, 3)); np.add.at(acc, inv[F].ravel(), np.repeat(fn, 3, axis=0))
    N = (acc / (np.linalg.norm(acc, axis=1, keepdims=True) + 1e-12))[inv][len(Pk):]
    pos = (np.c_[Pt, np.ones(len(Pt))] @ np.linalg.inv(M).T)[:, :3]
    nl = N @ M[:3, :3]; nl /= np.linalg.norm(nl, axis=1, keepdims=True) + 1e-12
    def put(data, **kw):
        nonlocal b
        b += b'\0' * (-len(b) % 4); js['bufferViews'].append({'buffer': 0, 'byteOffset': len(b), 'byteLength': len(data), **kw})
        b += data; return len(js['bufferViews']) - 1
    vv = put(np.hstack([pos, nl, UVt]).astype('<f4').tobytes(), byteStride=32, target=34962)
    iv = put(Ft.astype('<u4').tobytes(), target=34963)
    buf = io.BytesIO(); img.save(buf, 'WEBP', quality=90); im = put(buf.getvalue())
    ac = lambda **kw: (js['accessors'].append(kw), len(js['accessors']) - 1)[1]
    a_p = ac(bufferView=vv, byteOffset=0, componentType=5126, count=len(pos), type='VEC3', min=pos.min(0).tolist(), max=pos.max(0).tolist())
    a_n = ac(bufferView=vv, byteOffset=12, componentType=5126, count=len(pos), type='VEC3')
    a_u = ac(bufferView=vv, byteOffset=24, componentType=5126, count=len(pos), type='VEC2')
    a_i = ac(bufferView=iv, byteOffset=0, componentType=5125, count=Ft.size, type='SCALAR')
    js['images'].append({'name': f'shin-{pid}', 'mimeType': 'image/webp', 'bufferView': im})
    t0 = js['textures'][js['materials'][p0.get('material', 0)]['pbrMetallicRoughness']['baseColorTexture']['index']]
    js['textures'].append({**{k: v for k, v in t0.items() if k not in ('source', 'extensions')},
                           'extensions': {'EXT_texture_webp': {'source': len(js['images']) - 1}}})
    mat = json.loads(json.dumps(js['materials'][p0.get('material', 0)])); mat.pop('normalTexture', None)
    mat['name'] = f'shin-{pid}'; mat['doubleSided'] = True
    mat['pbrMetallicRoughness']['baseColorTexture'] = {'index': len(js['textures']) - 1}
    js['materials'].append(mat)
    mesh['primitives'].append({'attributes': {'POSITION': a_p, 'NORMAL': a_n, 'TEXCOORD_0': a_u}, 'mode': 4,
                                'material': len(js['materials']) - 1, 'indices': a_i})
    js['buffers'][0]['byteLength'] = len(b)
    write(dst, js, b)


if __name__ == '__main__':
    shin(*sys.argv[1:6])
