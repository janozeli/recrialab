"""Shortens a bottom by cutting the mesh at a height: what is below disappears, and the triangle that crosses the
line is clipped on it (position, normal and UV interpolated along the edge). The print does not stretch: the fabric
that stays is the same, in the same place of the texture. Made for skirt 009, which the 3D generator left at the
knee and which is a miniskirt in the shop photo.
usage: python3 tools/fit/hem.py INPUT.glb OUTPUT.glb HEIGHT   (height in meters, body B; only meshes with one primitive and
       interleaved vertices, like those of the collection)"""
import sys, numpy as np
from glb_patch import read, write
from texture import replace_view


def cut(src, dst, yc):
    js, b = read(src)
    (p,) = [p for m in js['meshes'] for p in m['primitives']]
    acc = js['accessors']; vw = js['bufferViews']
    pa = acc[p['attributes']['POSITION']]; v = vw[pa['bufferView']]
    stride = v['byteStride']; n = pa['count']; k = stride // 4
    assert all(acc[a]['bufferView'] == pa['bufferView'] for a in p['attributes'].values()), 'vertices not interleaved'
    R = np.frombuffer(bytes(b[v.get('byteOffset', 0):v.get('byteOffset', 0) + n * stride]), '<f4').reshape(n, k).copy()
    ia = acc[p['indices']]; iv = vw[ia['bufferView']]; dt = {5123: '<u2', 5125: '<u4'}[ia['componentType']]
    s = iv.get('byteOffset', 0) + ia.get('byteOffset', 0)
    F = np.frombuffer(bytes(b[s:s + ia['count'] * np.dtype(dt).itemsize]), dt).reshape(-1, 3).astype(np.int64)
    py = pa.get('byteOffset', 0) // 4 + 1                      # column of the position's y in the record
    nc = acc[p['attributes']['NORMAL']].get('byteOffset', 0) // 4 if 'NORMAL' in p['attributes'] else None
    new, middle = [], {}

    def cut_vertex(a, c):
        """Vertex on the cut line over edge a-c (one on each side), the same for both of its faces."""
        key = (min(a, c), max(a, c))
        on = [i for i in (a, c) if R[i, py] == yc]
        if on: return on[0]                                    # already on the line: no repeated vertex nor null triangle
        if key not in middle:
            t = (yc - R[a, py]) / (R[c, py] - R[a, py]); r = R[a] + t * (R[c] - R[a])
            if nc is not None: r[nc:nc + 3] /= np.linalg.norm(r[nc:nc + 3]) + 1e-12
            middle[key] = n + len(new); new.append(r)
        return middle[key]

    above = R[:, py] >= yc; faces = []
    for f in F:
        inside = above[f]
        if inside.all(): faces.append(list(f)); continue
        if not inside.any(): continue
        poly = []                                              # Sutherland–Hodgman against y >= yc
        for j in range(3):
            a, c = f[j], f[(j + 1) % 3]
            if above[a]: poly.append(a)
            if above[a] != above[c]: poly.append(cut_vertex(a, c))
        faces += [[poly[0], poly[j], poly[j + 1]] for j in range(1, len(poly) - 1)]
    R = np.vstack([R] + new) if new else R
    F = np.array(faces)
    used, F = np.unique(F, return_inverse=True); F = F.reshape(-1, 3); R = R[used]
    assert len(R) < 65536 or dt == '<u4'
    for a in p['attributes'].values():
        acc[a]['count'] = len(R)
        o = acc[a].get('byteOffset', 0) // 4; w = {'VEC3': 3, 'VEC2': 2, 'VEC4': 4}[acc[a]['type']]
        acc[a]['min'] = R[:, o:o + w].min(0).tolist(); acc[a]['max'] = R[:, o:o + w].max(0).tolist()
    ia['count'] = F.size; ia['byteOffset'] = 0
    b = replace_view(js, b, pa['bufferView'], R.astype('<f4').tobytes())
    b = replace_view(js, b, ia['bufferView'], F.astype(dt).tobytes())
    write(dst, js, b)
    print(f'{src}: cut at {yc} m, {len(F)} triangles, {len(R)} vertices')


if __name__ == '__main__':
    cut(sys.argv[1], sys.argv[2], float(sys.argv[3]))
