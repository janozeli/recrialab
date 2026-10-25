"""Separates the two legs of the pants Tripo generated stuck together and closes the inner side of each one.

The pose C pants came from Tripo's mannequin with the legs together, and the mesh goes from one leg to the other
through two strips of cloth, one at the front and one at the back, from the crotch to the hem. Without the strips each
leg is a "C" open on the inside, and the body shows through it. On the neutral body the legs stand farther apart, and
moving the legs apart with the strips whole stretches the bridge. Here the strips are cut in the
middle (each triangle stays with the leg on whose side it is) and each leg gets an inner wall: a zipper of triangles
between the front and the back cut edges, from the crotch to the hem. Above CROTCH nothing changes. The wall uses a
single cloth colour (the UV of a leg vertex with the median colour), and the two sides of the cut sit CUT m apart so
the weld by position (pant_leg_cloth.weld, garment.rotations) does not sew them back.
After this the legs move apart without stretching anything: pant_leg_cloth.py dresses the separated piece (original
and input separated with the same mesh). The measure (stretch.py) compares against the original separated the same way.
usage: python3 tools/fit/separate_legs.py ORIGINAL.glb IN.glb ORIGINAL_SEP.glb IN_SEP.glb"""
import sys, numpy as np, trimesh
from garment import Garment
from glb_patch import read, write, accessor_view
from texture import read_texture, uv_and_faces

CROTCH = .78     # whole faces below this belong to the legs (the bridge starts just below it)
HEM = .22        # below this the gap is the hem opening
CUT = 5e-5       # each side of the cut moves CUT m to its own side


def face_sides(P, F):
    """Side (1, -1) of each face below CROTCH, 0 above. Faces that do not cross x = 0 follow the leg they are
    connected to; those that cross (the strips) go to the side of their own center."""
    _, inv = np.unique(np.round(P, 5), axis=0, return_inverse=True); inv = inv.ravel(); FF = inv[F]
    X = np.zeros((inv.max() + 1, 3)); X[inv] = P
    low = X[FF, 1].max(1) < CROTCH
    sx = np.sign(X[FF, 0]); strip = (sx.min(1) < 0) & (sx.max(1) > 0) & low
    rest = np.flatnonzero(low & ~strip)
    adj = trimesh.Trimesh(X, FF[rest], process=False).face_adjacency
    side = np.zeros(len(F), int)
    for c in trimesh.graph.connected_components(adj, nodes=np.arange(len(rest)), min_len=1):
        side[rest[c]] = 1 if X[FF[rest[c]]].mean((0, 1))[0] > 0 else -1
    side[strip] = np.where(X[FF[strip]].mean(1)[:, 0] > 0, 1, -1)
    # a piece the cut leaves loose (connected to neither leg) goes whole to the leg it borders most: otherwise it
    # stays in the middle, held by both, and stretches when they move apart
    adj = trimesh.Trimesh(X, FF, process=False).face_adjacency
    for _ in range(5):
        a_, b_ = adj[(side[adj[:, 0]] == side[adj[:, 1]]) & (side[adj[:, 0]] != 0)].T
        cs = trimesh.graph.connected_components(np.c_[a_, b_], nodes=np.flatnonzero(side != 0), min_len=1)
        cs = sorted(cs, key=len, reverse=True)
        if len(cs) <= 2: break
        for c in cs[2:]:
            inside = np.zeros(len(F), bool); inside[c] = True
            nb = adj[inside[adj[:, 0]] ^ inside[adj[:, 1]]]; nb = np.where(inside[nb[:, 0]], nb[:, 1], nb[:, 0])
            v = side[nb]; v = v[v != 0]
            if len(v): side[c] = 1 if (v == 1).sum() >= (v == -1).sum() else -1
    return side, strip


def mesh_legs(P, F, below=.70):
    """Side (1, -1) of each vertex by the mesh leg it belongs to, if the legs are separated below `below`
    (separate_legs.py); otherwise None. A vertex of the left leg may be at x > 0 (the cut bridge)."""
    _, inv = np.unique(np.round(P, 5), axis=0, return_inverse=True); inv = inv.ravel(); FF = inv[F]
    X = np.zeros((inv.max() + 1, 3)); X[inv] = P
    low = np.flatnonzero(X[FF, 1].max(1) < below)
    cs = sorted(trimesh.graph.connected_components(trimesh.Trimesh(X, FF[low], process=False).face_adjacency,
                nodes=np.arange(len(low)), min_len=1), key=len, reverse=True)
    if len(cs) < 2 or len(cs[1]) < .2 * len(low): return None
    lw = np.zeros(len(X), int)
    for c in cs[:2]:
        v = np.unique(FF[low[c]]); lw[v] = 1 if X[v, 0].mean() > 0 else -1
    return np.where(lw[inv] != 0, lw[inv], np.where(P[:, 0] >= 0, 1, -1))


def leg_side(P, F):
    """Side of each vertex: the mesh leg (separated legs) or the sign of x."""
    side = mesh_legs(P, F)
    return np.where(P[:, 0] >= 0, 1, -1) if side is None else side


def chains(F, side, s, cut):
    """Cut edges on side s, each from the crotch (higher y) to the hem: lists of indices."""
    f = F[side == s]; e = np.sort(np.vstack([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]]), 1)
    u, c = np.unique(e, axis=0, return_counts=True); b = u[(c == 1) & cut[u].all(1)]
    return [x for x in trimesh.graph.connected_components(b, min_len=2)], b


def order(b, nodes, y):
    nb = {}
    for i, j in b:
        if i in nodes and j in nodes: nb.setdefault(i, []).append(j); nb.setdefault(j, []).append(i)
    ends = [n for n in nodes if len(nb.get(n, [])) == 1]
    if len(ends) != 2: return None
    a = max(ends, key=lambda n: y[n]); out = [a]; prev = -1
    while len(out) < len(nodes):
        nxt = [n for n in nb[out[-1]] if n != prev]
        if not nxt: break
        prev = out[-1]; out.append(nxt[0])
    return out if len(out) == len(nodes) else None


def zip_chains(A, B, X):
    """Triangles between chains A and B (same direction), walking by the fraction of each one's length. Walking by
    the shortest diagonal instead makes long slivers on crooked edges (the back edge of 006) and leaves slits."""
    t, i, j = [], 0, 0
    frac = lambda C: np.r_[0, np.cumsum(np.linalg.norm(np.diff(X[C], axis=0), axis=1))] / max(
        np.linalg.norm(np.diff(X[C], axis=0), axis=1).sum(), 1e-9)
    fa, fb = frac(A), frac(B)
    while i < len(A) - 1 or j < len(B) - 1:
        if j == len(B) - 1 or (i < len(A) - 1 and fa[i + 1] <= fb[j + 1]):
            t.append((A[i], A[i + 1], B[j])); i += 1
        else:
            t.append((A[i], B[j + 1], B[j])); j += 1
    return t


def build_mesh(g, P, F):
    """New mesh: vertices (world), UV, normals and faces per primitive, with the cut and the walls."""
    uv, _, _ = uv_and_faces(g)
    side, strip = face_sides(P, F)
    used = {s: np.zeros(len(P), bool) for s in (0, 1, -1)}
    for s in (0, 1, -1): used[s][F[side == s].ravel()] = True
    # a welded vertex (by position) with faces on both sides: side -1 gets copies
    _, inv = np.unique(np.round(P, 5), axis=0, return_inverse=True); inv = inv.ravel()
    ws = {s: np.zeros(inv.max() + 1, bool) for s in (0, 1, -1)}
    for s in (0, 1, -1): ws[s][inv[used[s]]] = True
    cutW = ws[1] & ws[-1] & ~ws[0]
    cut = cutW[inv]
    P = P.copy(); P2 = [P]; uv2 = [uv]; F = F.copy(); n = len(P)
    dup = np.flatnonzero(cut & used[1] & used[-1])
    new = np.full(len(P), -1); new[dup] = n + np.arange(len(dup)); n += len(dup)
    P2.append(P[dup]); uv2.append(uv[dup]); source = np.r_[np.arange(len(P)), dup]
    k = side == -1; Fk = F[k]; Fk = np.where(new[Fk] >= 0, new[Fk], Fk); F[k] = Fk
    X = np.vstack(P2); UV = np.vstack(uv2)
    side_v = np.zeros(len(X), int)
    for s in (1, -1): side_v[F[side == s].ravel()] = s
    cutv = np.r_[cut, np.ones(len(dup), bool)]
    X[cutv, 0] += CUT * side_v[cutv]
    # wall colour: the leg vertex with the median texture colour
    tex = read_texture(g.js, g.bin); h, w = tex.shape[:2]
    rgb = lambda u: tex[np.clip((u[:, 1] % 1 * h).astype(int), 0, h - 1), np.clip((u[:, 0] % 1 * w).astype(int), 0, w - 1)].astype(float)
    walls, info = [], []
    for s in (1, -1):
        _, wi = np.unique(np.round(X, 5), axis=0, return_inverse=True); wi = wi.ravel()   # edges on the welded mesh
        rep = np.zeros(wi.max() + 1, int); rep[wi[::-1]] = np.arange(len(wi))[::-1]
        cw = np.zeros(wi.max() + 1, bool); cw[wi[:len(cutv)][cutv]] = True
        cs, b = chains(wi[F], side, s, cw)
        cs = sorted(cs, key=len, reverse=True)[:2]
        if len(cs) < 2: info.append(f'side {s}: without both edges'); continue
        A, B = (order(b, set(c), X[rep, 1]) for c in cs)
        if A is None or B is None: info.append(f'side {s}: branching edge'); continue
        A, B = rep[A], rep[B]
        if X[A[0], 1] < CROTCH / 2:   # 006: the larger edge is a U (from the front hem, through the crotch, to the back
            k = int(np.argmax(X[A, 1])); A, B = A[k::-1], A[k:]   # hem) and the other a piece at the crotch: front and back are the U
        if X[A, 2].mean() < X[B, 2].mean(): A, B = B, A        # A at the front
        # from the whole leg: near the cut the cloth is the area the generator did not see, painted almost black
        near = np.flatnonzero((side_v == s) & (X[:, 1] > .3) & (X[:, 1] < CROTCH))
        # the texel closest to the per-channel median colour (the one of median brightness can lose the hue)
        c = rgb(UV[near]); colour = UV[near[np.argmin(np.linalg.norm(c - np.median(c, 0), axis=1))]]
        base = len(X); ids = np.r_[A, B]; m = {v: base + i for i, v in enumerate(ids)}
        X = np.vstack([X, X[ids]]); UV = np.vstack([UV, np.repeat(colour[None], len(ids), 0)]); source = np.r_[source, source[ids]]
        side_v = np.r_[side_v, np.full(len(ids), s)]
        T = np.array([[m[a] for a in t] for t in zip_chains(list(A), list(B), X)])
        nrm = np.cross(X[T[:, 1]] - X[T[:, 0]], X[T[:, 2]] - X[T[:, 0]])
        if (nrm[:, 0] * -s).sum() < 0: T = T[:, ::-1]     # wall facing the other leg
        # where the front and back edges already touch through a mesh edge the leg is closed: there the zipper
        # would repeat that edge (three or four faces on it, and the wall becomes a loose piece)
        _, wj = np.unique(np.round(X, 5), axis=0, return_inverse=True); wj = wj.ravel()
        there = {tuple(sorted(e)) for e in wj[np.vstack([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])]}
        there -= {tuple(sorted((wj[c[i]], wj[c[i + 1]]))) for c in (A, B) for i in range(len(c) - 1)}   # the edge itself stays
        T = T[[not any(tuple(sorted((wj[t[k]], wj[t[(k + 1) % 3]]))) in there for k in range(3)) for t in T]]
        walls.append(T); info.append(f'side {s}: edges of {len(A)} and {len(B)} vertices, wall of {len(T)} triangles')
    # the gap left over (at the top, between the top of the walls and the crotch; where the edges touch in the middle):
    # a fan cap from the center; the hem opening (below HEM) stays open
    _, wi = np.unique(np.round(X, 5), axis=0, return_inverse=True); wi = wi.ravel()
    rep = np.zeros(wi.max() + 1, int); rep[wi[::-1]] = np.arange(len(wi))[::-1]
    every = wi[np.vstack([F] + walls)]
    d = np.vstack([every[:, [0, 1]], every[:, [1, 2]], every[:, [2, 0]]])
    u, c = np.unique(np.sort(d, 1), axis=0, return_counts=True); border = {tuple(e) for e in u[c == 1]}
    seg = [e for e in d if tuple(sorted(e)) in border]
    fresh = np.zeros(wi.max() + 1, bool)
    fresh[wi[np.flatnonzero(np.r_[cutv, np.ones(len(X) - len(cutv), bool)])]] = True
    nxt = {}
    for a_, b_ in seg: nxt.setdefault(int(a_), []).append(int(b_))   # a pinched vertex has two ways out
    loops = []
    for v0 in list(nxt):
        while fresh[v0] and nxt[v0]:
            loop = [v0]
            while nxt.get(loop[-1]) and len(loop) < 2000:
                v = nxt[loop[-1]].pop()
                if v in loop:   # closed a loop (at a pinch, a loop inside the path): it comes out whole
                    k = loop.index(v); loops.append(loop[k:]); loop = loop[:k + 1]
                    if k == 0: break
                else: loop.append(v)
    for loop in loops:
        if X[rep[loop], 1].min() < HEM: continue
        base = len(X); r = rep[loop]
        X = np.vstack([X, X[r], X[r].mean(0)[None]]); UV = np.vstack([UV, np.repeat(colour[None], len(r) + 1, 0)])
        source = np.r_[source, source[r], source[r[0]]]
        k = len(r); T = np.array([[base + (i + 1) % k, base + i, base + k] for i in range(k)])
        walls.append(T); info.append(f'cap of {k} vertices')
    return X, UV, F, walls, info, source


def rewrite(g, X, UV, F, walls, dst, nf=None, nv=None, prim=0):
    """Writes the new mesh (more vertices and triangles) in place of g's primitives, with the buffer repacked. F comes
    in primitive order, nf triangles and nv vertices for each (g's, if None); the walls go to primitive prim."""
    js, b = g.js, g.bin
    nf = nf or [js['accessors'][p['indices']]['count'] // 3 for _, _, p in g.parts]
    lim_v = np.cumsum([0] + (nv or g.sizes)); lim_f = np.cumsum([0] + nf)
    m = trimesh.Trimesh(X, np.vstack([F] + walls), process=False)
    _, inv = np.unique(np.round(X, 5), axis=0, return_inverse=True); inv = inv.ravel()
    acc = np.zeros((inv.max() + 1, 3)); np.add.at(acc, inv[m.faces].ravel(), np.repeat(np.cross(
        X[m.faces[:, 1]] - X[m.faces[:, 0]], X[m.faces[:, 2]] - X[m.faces[:, 0]]), 3, axis=0))
    N = (acc / (np.linalg.norm(acc, axis=1, keepdims=True) + 1e-12))[inv]
    # a new vertex (copy from the cut or the wall) goes to the primitive of the triangles that use it
    owner = np.full(len(X), -1)
    for pi in range(len(g.parts)): owner[lim_v[pi]:lim_v[pi + 1]] = pi
    every = np.vstack([F] + walls); fprim = np.r_[np.repeat(np.arange(len(nf)), nf), np.full(sum(len(t) for t in walls), prim)]
    for pi in range(len(nf)):
        fi = every[fprim == pi]
        owner[np.unique(fi[owner[fi] == -1])] = pi
    views = {}
    empty = []
    for pi, (a, M, p) in enumerate(g.parts):
        vs = np.flatnonzero(owner == pi); remap = np.full(len(X), -1); remap[vs] = np.arange(len(vs))
        if not len(vs):   # a primitive that went away whole (shin_tube.py on the hem of 011): leaves the mesh
            empty.append(p); continue
        fi = every[fprim == pi]; assert (remap[fi] >= 0).all(), 'triangle with vertices from different primitives'
        Mi = np.linalg.inv(M); A = M[:3, :3]
        pos = (np.c_[X[vs], np.ones(len(vs))] @ Mi.T)[:, :3]
        nl = N[vs] @ A; nl /= np.linalg.norm(nl, axis=1, keepdims=True) + 1e-12
        attrs = p['attributes']; ap, an, au = attrs['POSITION'], attrs['NORMAL'], attrs['TEXCOORD_0']
        (vi,) = {js['accessors'][x]['bufferView'] for x in attrs.values()}
        assert len(attrs) == 3 and js['bufferViews'][vi]['byteStride'] == 32 and [js['accessors'][x].get('byteOffset', 0) for x in (ap, an, au)] == [0, 12, 24]
        rows = np.hstack([pos, nl, UV[vs]]).astype('<f4')
        views[vi] = rows.tobytes()
        for x in (ap, an, au): js['accessors'][x]['count'] = len(vs)
        js['accessors'][ap]['min'] = pos.min(0).tolist(); js['accessors'][ap]['max'] = pos.max(0).tolist()
        for x in (an, au): js['accessors'][x].pop('min', None); js['accessors'][x].pop('max', None)
        ia = js['accessors'][p['indices']]; idx = remap[fi].ravel()
        ia['count'] = len(idx); ia.pop('min', None); ia.pop('max', None)
        assert idx.max() < {5121: 256, 5123: 65536, 5125: 2 ** 32}[ia['componentType']]
        data = idx.astype({5121: '<u1', 5123: '<u2', 5125: '<u4'}[ia['componentType']]).tobytes()
        shared = views.setdefault(ia['bufferView'], b'')   # the primitives' indices may share a bufferView
        shared += b'\0' * (-len(shared) % 4); ia['byteOffset'] = len(shared); views[ia['bufferView']] = shared + data
    for m in js['meshes']: m['primitives'] = [q for q in m['primitives'] if not any(q is v for v in empty)]
    out = bytearray()
    for i, v in enumerate(js['bufferViews']):
        s = v.get('byteOffset', 0); data = views.get(i, bytes(b[s:s + v['byteLength']]))
        out += b'\0' * (-len(out) % 4); v['byteOffset'] = len(out); v['byteLength'] = len(data); out += data
    js['buffers'][0]['byteLength'] = len(out)
    write(dst, js, out)


def separate(orig, src, dst_orig, dst_src):
    """Cuts along the ORIGINAL and writes both (original and input) with the input's mesh: a triangle the input lost
    later (islands.py, slivers.py) also leaves the original, found by UV (pant_leg_cloth.correspondence)."""
    from pant_leg_cloth import correspondence
    go, g = Garment(orig), Garment(src)
    Po, P = go.vertices(), g.vertices(); F = g.mesh(P).faces
    if len(Po) != len(P) or len(go.mesh(Po).faces) != len(F) or (go.mesh(Po).faces != F).any():
        Po = Po[correspondence(go, g)]
    X, UV, F2, walls, info, source = build_mesh(g, Po, F)      # the cut comes from the original: the same on both
    rewrite(g, X, UV, F2, walls, dst_orig)
    rewrite(Garment(src), P[source] + (X - Po[source]), UV, F2, walls, dst_src)   # the input with the same copies and walls
    print(f'{orig}: {len(source) - len(Po)} new vertices; ' + '; '.join(info))

if __name__ == '__main__':
    separate(*sys.argv[1:5])
