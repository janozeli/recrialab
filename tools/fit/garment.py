"""Reads and writes every vertex of a garment GLB in world coordinates (body B), leaving textures and UVs alone."""
import numpy as np, trimesh
from glb_patch import read, write, get_vec3, set_vec3, accessor_view


def trs(n):
    if 'matrix' in n:
        return np.array(n['matrix']).reshape(4, 4).T
    T = np.eye(4); T[:3, 3] = n.get('translation', [0, 0, 0])
    q = n.get('rotation', [0, 0, 0, 1])
    R = np.eye(4); R[:3, :3] = trimesh.transformations.quaternion_matrix([q[3], q[0], q[1], q[2]])[:3, :3]
    S = np.diag(list(n.get('scale', [1, 1, 1])) + [1])
    return T @ R @ S


class Garment:
    def __init__(self, path):
        self.js, self.bin = read(path)
        js = self.js
        self.world = {}
        def walk(i, M):
            M = M @ trs(js['nodes'][i]); self.world[i] = M
            for c in js['nodes'][i].get('children', []): walk(c, M)
        for r in js['scenes'][js.get('scene', 0)]['nodes']: walk(r, np.eye(4))
        self.parts = []  # (accessor, matrix, primitive)
        seen = {}
        for i, M in self.world.items():
            n = js['nodes'][i]
            if 'mesh' not in n: continue
            for p in js['meshes'][n['mesh']]['primitives']:
                a = p['attributes']['POSITION']
                assert a not in seen, 'mesh instanced twice'
                seen[a] = 1
                self.parts.append((a, M, p))
        self.local = [get_vec3(js, self.bin, a) for a, _, _ in self.parts]
        self.sizes = [len(v) for v in self.local]

    def vertices(self):
        return np.vstack([(np.c_[v, np.ones(len(v))] @ M.T)[:, :3] for v, (_, M, _) in zip(self.local, self.parts)])

    def mesh(self, verts=None):
        verts = self.vertices() if verts is None else verts
        faces, off = [], 0
        for (a, M, p), n in zip(self.parts, self.sizes):
            ia = self.js['accessors'][p['indices']]; _, s, _ = accessor_view(self.js, self.bin, p['indices'])
            dt = {5121: '<u1', 5123: '<u2', 5125: '<u4'}[ia['componentType']]
            idx = np.frombuffer(bytes(self.bin[s:s + ia['count'] * np.dtype(dt).itemsize]), dt).reshape(-1, 3)
            faces.append(idx.astype(np.int64) + off); off += n
        return trimesh.Trimesh(verts, np.vstack(faces), process=False)

    def save(self, path, verts, before=None):
        """Writes positions. With `before` (the original positions) the normals turn with the surface: the site
        lights the stored normals, so without this the shading keeps the old orientation."""
        R = None if before is None else rotations(self.mesh(before), self.mesh(verts))
        off = 0
        for (a, M, p), n in zip(self.parts, self.sizes):
            w = verts[off:off + n]
            loc = (np.c_[w, np.ones(n)] @ np.linalg.inv(M).T)[:, :3]
            acc = set_vec3(self.js, self.bin, a, loc)
            acc['min'] = loc.min(0).tolist(); acc['max'] = loc.max(0).tolist()
            if R is not None and 'NORMAL' in p['attributes']:
                A = M[:3, :3]; nl = get_vec3(self.js, self.bin, p['attributes']['NORMAL'])
                nw = nl @ np.linalg.inv(A); nw /= np.linalg.norm(nw, axis=1, keepdims=True) + 1e-12
                nw = np.einsum('nij,nj->ni', R[off:off + n], nw)
                nl = nw @ A; nl /= np.linalg.norm(nl, axis=1, keepdims=True) + 1e-12
                set_vec3(self.js, self.bin, p['attributes']['NORMAL'], nl)
            off += n
        write(path, self.js, self.bin)


def kernel(X, radius):
    """Gaussian average in space (width `radius`, cut at 2 radii) with normalized rows. Applied to a displacement
    field, lining and outer fabric that are close in space but far apart on the mesh move together
    (displacement_field.py, hood.py)."""
    from scipy.spatial import cKDTree
    from scipy.sparse import coo_matrix, diags
    pairs = cKDTree(X).query_pairs(2 * radius, output_type='ndarray')
    i = np.r_[pairs[:, 0], pairs[:, 1], np.arange(len(X))]; j = np.r_[pairs[:, 1], pairs[:, 0], np.arange(len(X))]
    K = coo_matrix((np.exp(-(np.linalg.norm(X[i] - X[j], axis=1) / radius) ** 2), (i, j)), shape=(len(X),) * 2).tocsr()
    return diags(1 / np.asarray(K.sum(1)).ravel()) @ K


def rotations(m0, m1):
    """Per-vertex rotation taking the old geometric normal to the new one (seam vertices welded)."""
    _, inv = np.unique(np.round(m0.vertices, 5), axis=0, return_inverse=True); inv = inv.ravel()
    def normals(m):
        fn = np.cross(m.vertices[m.faces[:, 1]] - m.vertices[m.faces[:, 0]], m.vertices[m.faces[:, 2]] - m.vertices[m.faces[:, 0]])
        acc = np.zeros((inv.max() + 1, 3)); np.add.at(acc, inv[m.faces].ravel(), np.repeat(fn, 3, axis=0))
        return (acc / (np.linalg.norm(acc, axis=1, keepdims=True) + 1e-12))[inv]
    a, b = normals(m0), normals(m1)
    v = np.cross(a, b); c = np.einsum('ij,ij->i', a, b)
    K = np.zeros((len(a), 3, 3))
    K[:, 0, 1], K[:, 0, 2], K[:, 1, 2] = -v[:, 2], v[:, 1], -v[:, 0]
    K[:, 1, 0], K[:, 2, 0], K[:, 2, 1] = v[:, 2], -v[:, 1], v[:, 0]
    return np.eye(3) + K + K @ K / np.maximum(1 + c, 1e-6)[:, None, None]
