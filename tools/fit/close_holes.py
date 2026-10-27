"""Closes the small holes the 3D generator left in a garment's hem, and checks that the bottoms have none.

A hole is a boundary loop shorter than MAX_PERIMETER within HEM of the piece's lowest point (the hem and leg openings
themselves are far longer; higher up, the short loops are belt loops and rivets, made that way). Each loop is filled
with a fan of triangles over its own vertices, wound like the faces around it, so nothing moves and no vertex is added:
the new triangles take the print of the loop's edge. Made for trousers 002, whose hem has a hole the shop photo does
not have; dressed whole as cloth (pant_leg_cloth.py --whole), the body shows through it from behind (visual QA,
measure `tear`), and before that main's 002 had the same hole and passed every check (calibration case hem-hole-002).
--check counts the holes of each bottom: none, or up to AS_IS while the known issue hem-holes names the piece (the
frayed hems of 007, 008 and 015 are counted too: the check cannot tell a fringe from a hole).
usage: python3 tools/fit/close_holes.py INPUT.glb OUTPUT.glb
       python3 tools/fit/close_holes.py --check [IDs]   (no IDs: the 15 bottoms)"""
import os, sys, numpy as np
from collections import defaultdict
from garment import Garment
from glb_patch import write, accessor_view
from paths import GARMENTS
from texture import replace_view
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '../visual-qa'))
from known_issues import FILE as KNOWN_ISSUES, known_issues  # noqa: E402

MAX_PERIMETER = .12   # m
HEM = .12             # m above the piece's lowest point
BOTTOMS = [f'{i:03d}' for i in range(1, 16)]
# piece: holes in the hem held while the known issue hem-holes names it (the count may only go down)
AS_IS = {
    '001': 3,
    '003': 1,
    '004': 4,
    '006': 9,
    '007': 24,
    '008': 20,
    '012': 22,
    '015': 14,
}


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


def holes(P, F, low):
    """The holes in the hem of the mesh P, F of a piece whose lowest point is at `low`: (perimeter, indices in P of the
    loop's vertices, one per position)."""
    _, first, inv = np.unique(np.round(P, 5), axis=0, return_index=True, return_inverse=True); inv = inv.ravel()
    out = []
    for loop in loops(inv[F]):
        v = first[np.array(loop)]; per = np.linalg.norm(P[v] - P[np.roll(v, -1)], axis=1).sum()
        if per < MAX_PERIMETER and P[v, 1].max() <= low + HEM: out.append((per, v))
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
    g = Garment(src); js, b = g.js, g.bin; done = 0; low = g.vertices()[:, 1].min()
    for (a, M, p), local in zip(g.parts, g.local):
        P = (np.c_[local, np.ones(len(local))] @ M.T)[:, :3]
        ia = js['accessors'][p['indices']]; _, s, _ = accessor_view(js, b, p['indices'])
        dt = {5121: '<u1', 5123: '<u2', 5125: '<u4'}[ia['componentType']]
        F = np.frombuffer(bytes(b[s:s + ia['count'] * np.dtype(dt).itemsize]), dt).reshape(-1, 3).astype(np.int64)
        new = []
        for per, v in holes(P, F, low):   # one GLB vertex per position: the print of the edge
            new += [[v[0], v[j], v[j + 1]] for j in range(1, len(v) - 1)]
            print(f'hole of {len(v)} vertices, {100 * per:.1f} cm around, at y {P[v, 1].min():.2f}-{P[v, 1].max():.2f} m: closed')
        if not new: continue
        F = np.vstack([F, new]); done += len(new)
        b = set_indices(js, b, p['indices'], F.astype(dt).tobytes())
    if not done: return print(f'{src}: no hole below {100 * MAX_PERIMETER:.0f} cm in the hem')
    write(dst, js, b)


def check(pieces):
    issues = known_issues()
    bad = [f'{pid}: hem-holes is not an open known issue naming it in {KNOWN_ISSUES}'
           for pid in AS_IS if pid not in issues.get('hem-holes', ())]
    for pid in pieces:
        g = Garment(GARMENTS + f'{pid}.glb'); P = g.vertices(); h = holes(P, g.mesh(P).faces, P[:, 1].min())
        n = AS_IS.get(pid, 0)
        print(f'{pid}: {len(h)} holes in the hem' + ''.join(f', {100 * per:.1f} cm at y {P[v, 1].min():.2f}' for per, v in h))
        if len(h) > n: bad.append(f'{pid}: {len(h)} holes in the hem, up to {n} (close them with close_holes.py)')
        elif len(h) < n: bad.append(f'{pid}: {len(h)} holes in the hem, fewer than the {n} held: lower AS_IS')
    if bad: sys.exit('\n'.join(bad))


if __name__ == '__main__':
    if sys.argv[1] == '--check':
        check(sys.argv[2:] or BOTTOMS)
    else:
        close(*sys.argv[1:3])
