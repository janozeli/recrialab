"""Removes loose garment pieces from the mesh: components (vertices welded by position) smaller than ISLAND_CM2,
other than the body of the piece. The 3D generator leaves crumbs on the frayed hem of the trousers and the cuffs of
the jackets; on the site they show as slivers floating in the air (visual QA, measure `loose`). Only triangles
disappear: position, UV and print of the rest stay the same. The CI check is `site/fit.test.ts` (same limit).
usage: python3 tools/fit/islands.py [001 002 ...]   (without arguments: all 38; then run install.py)"""
import os, sys, numpy as np, trimesh
from garment import Garment
from glb_patch import write, accessor_view
from paths import GARMENTS

ISLAND_CM2 = 20.0
# Piece with its own limit: the lining ring inside the right cuff of 036 (about 30 cm²) goes too, because seen from
# below it floats inside the cuff opening. The rings of 037 stay: on screen they touch the cuff.
ISLAND_PIECE = {'036': 30.0}


def loose(g, limit=ISLAND_CM2):
    """Per-triangle mask (Garment.mesh() order) of what belongs to an island to remove."""
    P = g.vertices(); m = g.mesh(P)
    _, inv = np.unique(np.round(P, 5), axis=0, return_inverse=True); inv = inv.ravel()
    X = np.zeros((inv.max() + 1, 3)); X[inv] = P
    F = inv[m.faces]; t = trimesh.Trimesh(X, F, process=False)
    # connected by edges of exactly 2 faces (trimesh.face_adjacency), as in site/fit.test.ts: a crumb attached to the
    # piece by a single vertex, or by an edge of 3 faces or more, is loose too
    lab = trimesh.graph.connected_component_labels(t.face_adjacency, len(F))
    area = np.bincount(lab, t.area_faces) * 1e4
    drop = area < limit; drop[np.argmax(area)] = False
    out = drop[lab]
    return out, len(np.unique(lab[out])), float(area[drop].sum())


def clean(path, limit=ISLAND_CM2):
    g = Garment(path)
    out, n, cm2 = loose(g, limit)
    if not out.any():
        return
    remove(g, out, path)
    print(f'{os.path.basename(path)}: {n} islands, {cm2:.1f} cm², {out.sum()} triangles removed')


def remove(g, out, path):
    """Writes to path the piece g without the triangles marked in out (Garment.mesh() order)."""
    js, off, empty = g.js, 0, set()
    for _, _, p in g.parts:   # per primitive: the triangles and vertices that stay move to the start of its own range
        ia = js['accessors'][p['indices']]; k = ia['count'] // 3
        _, s, _ = accessor_view(js, g.bin, p['indices'])
        dt = np.dtype({5121: '<u1', 5123: '<u2', 5125: '<u4'}[ia['componentType']])
        idx = np.frombuffer(bytes(g.bin[s:s + ia['count'] * dt.itemsize]), dt).reshape(-1, 3)
        keep = idx[~out[off:off + k]]; off += k
        if not keep.size:
            empty.add(id(p)); continue
        used, new = np.unique(keep, return_inverse=True)
        g.bin[s:s + keep.size * dt.itemsize] = new.astype(dt).tobytes(); ia['count'] = keep.size
        attrs = [js['accessors'][a] for a in p['attributes'].values()]
        (vi,) = {a['bufferView'] for a in attrs}
        assert sum(js['accessors'][a]['bufferView'] == vi for _, _, q in g.parts for a in q['attributes'].values()) == len(attrs), 'vertices of different primitives in the same bufferView'
        v = js['bufferViews'][vi]; st, base = v['byteStride'], v.get('byteOffset', 0)
        R = np.frombuffer(bytes(g.bin[base:base + attrs[0]['count'] * st]), np.uint8).reshape(-1, st)[used]
        g.bin[base:base + R.size] = R.tobytes(); v['byteLength'] = R.size
        for a in attrs:
            a['count'] = len(used)
            if 'min' in a:
                w = {'VEC2': 2, 'VEC3': 3, 'VEC4': 4}[a['type']]; c = R[:, a.get('byteOffset', 0):a.get('byteOffset', 0) + 4 * w].copy().view('<f4')
                a['min'], a['max'] = c.min(0).tolist(), c.max(0).tolist()
    # a primitive that was only island leaves the mesh; a mesh without primitives leaves the file
    for m in js['meshes']:
        m['primitives'] = [p for p in m['primitives'] if id(p) not in empty]
    index = {}
    for i, m in enumerate(js['meshes']):
        if m['primitives']: index[i] = len(index)
    js['meshes'] = [m for m in js['meshes'] if m['primitives']]
    for nd in js['nodes']:
        if 'mesh' in nd:
            if nd['mesh'] in index: nd['mesh'] = index[nd['mesh']]
            else: del nd['mesh']
    write(path, js, g.bin)


if __name__ == '__main__':
    for pid in sys.argv[1:] or [f'{i:03d}' for i in range(1, 39)]:
        clean(GARMENTS + f'{pid}.glb', ISLAND_PIECE.get(pid, ISLAND_CM2))
