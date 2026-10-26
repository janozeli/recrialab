"""Closes the small holes the 3D generator left in a garment's mesh: boundary loops shorter than MAX_PERIMETER, in the
hem (below MAX_HEIGHT; the hem and leg openings themselves are far longer). Each loop is filled with a fan of triangles over its own
vertices, wound like the faces around it, so nothing moves and no vertex is added: the new triangles take the print
of the loop's edge. Made for trousers 002, whose hem has a hole the shop photo does not have; dressed whole as cloth
(pant_leg_cloth.py --whole), the body shows through it from behind (visual QA, measure `tear`).
usage: python3 tools/fit/close_holes.py INPUT.glb OUTPUT.glb"""
import sys, numpy as np
from collections import defaultdict
from garment import Garment
from glb_patch import write, accessor_view
from texture import replace_view

MAX_PERIMETER = .12   # m
MAX_HEIGHT = .30      # only in the hem: higher up, the short loops are belt loops and rivets, made that way


def loops(F):
    """Boundary loops of the mesh welded by position, each as the vertex order the filling faces must follow."""
    half = defaultdict(int)
    for f in F:
        for j in range(3): half[(f[j], f[(j + 1) % 3])] += 1
    nxt = {}
    for (a, b) in half:
        if (b, a) not in half: nxt[b] = a   # boundary half-edge a→b: the filling face runs b→a
    out, seen = [], set()
    for s in nxt:
        if s in seen: continue
        loop, v = [], s
        while v not in seen and v in nxt: seen.add(v); loop.append(v); v = nxt[v]
        if v == s: out.append(loop)
    return out


def set_indices(js, b, ai, data):
    """Writes the indices of accessor `ai`, rebuilding the bufferView it shares with the other primitives' indices."""
    vi = js['accessors'][ai]['bufferView']; v = js['bufferViews'][vi]; base = v.get('byteOffset', 0)
    out = bytearray()
    for i, a in sorted(((i, a) for i, a in enumerate(js['accessors']) if a.get('bufferView') == vi), key=lambda x: x[1].get('byteOffset', 0)):
        size = a['count'] * {5121: 1, 5123: 2, 5125: 4}[a['componentType']]
        chunk = data if i == ai else bytes(b[base + a.get('byteOffset', 0):base + a.get('byteOffset', 0) + size])
        out += b'\0' * (-len(out) % 4); a['byteOffset'] = len(out); out += chunk
        if i == ai: a['count'] = len(data) // {5121: 1, 5123: 2, 5125: 4}[a['componentType']]
    return replace_view(js, b, vi, bytes(out))


def close(src, dst):
    g = Garment(src); js, b = g.js, g.bin; done = 0
    for (a, M, p), local in zip(g.parts, g.local):
        P = (np.c_[local, np.ones(len(local))] @ M.T)[:, :3]
        ia = js['accessors'][p['indices']]; _, s, _ = accessor_view(js, b, p['indices'])
        dt = {5121: '<u1', 5123: '<u2', 5125: '<u4'}[ia['componentType']]
        F = np.frombuffer(bytes(b[s:s + ia['count'] * np.dtype(dt).itemsize]), dt).reshape(-1, 3).astype(np.int64)
        _, first, inv = np.unique(np.round(P, 5), axis=0, return_index=True, return_inverse=True); inv = inv.ravel()
        new = []
        for loop in loops(inv[F]):
            L = np.array(loop); per = np.linalg.norm(P[first[L]] - P[first[np.roll(L, -1)]], axis=1).sum()
            if per >= MAX_PERIMETER or P[first[L], 1].max() > MAX_HEIGHT: continue
            v = first[L]   # one GLB vertex per position: the print of the edge
            new += [[v[0], v[j], v[j + 1]] for j in range(1, len(v) - 1)]
            print(f'hole of {len(L)} vertices, {100 * per:.1f} cm around, at y {P[v, 1].min():.2f}-{P[v, 1].max():.2f} m: closed')
        if not new: continue
        F = np.vstack([F, new]); done += len(new)
        b = set_indices(js, b, p['indices'], F.astype(dt).tobytes())
    if not done: return print(f'{src}: no hole below {100 * MAX_PERIMETER:.0f} cm in the hem')
    write(dst, js, b)

if __name__ == '__main__':
    close(*sys.argv[1:3])
