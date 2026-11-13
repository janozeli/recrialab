"""The loose part of a garment in few polygons: a tube of rings around the vertical axis, welded to the shell.

A shell (shell.py) follows the body, so a skirt would turn into shorts and a long hem would hug the hip. Below
SEAM the shell is cut and a tube takes over: its top ring IS the shell's cut edge (same points), the rings below
keep the same angles and take the garment's radius at that height and angle, never smaller than the body plus
CLEAR and, for a top, never inside the set of all the bottoms plus RISE at that angle (so a long hem passes outside
every bottom). The hem keeps the garment's own height per angle. The texture is baked from the garment (shell.bake).
Sleeves are left whole: sleeve or torso is told by the mesh's connectivity, not by distance to the body (the hand
rests against the hip).
usage: python3 tools/fit/tube.py DENSE_BODY.glb SHELL.glb GARMENT.glb SHELL_CUT_OUT.glb TUBE_OUT.glb RINGS [ENVELOPE.npy]"""
import os, sys, numpy as np, trimesh
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from garment import Garment
import landmarks as L
import shell as S

SEAM = .90             # m: height of the weld between shell and tube
CLEAR, BAND = .006, .02
ARM_GAP = .004         # m: the tube stays this far inside the arm
ARMPIT = 1.28          # m: below this height a sleeve is a part of the shell not connected to the middle of the torso


def sleeves(V, F):
    """Mask of the shell's vertices that belong to a sleeve."""
    _, inv = np.unique(np.round(V, 4), axis=0, return_inverse=True); inv = inv.ravel(); G = inv[F]
    G = G[(V[F][:, :, 1] < ARMPIT).all(1)]; n = inv.max() + 1
    e = np.vstack([G[:, [0, 1]], G[:, [1, 2]], G[:, [2, 0]]])
    _, comp = connected_components(coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(n, n)), directed=False)
    cv = comp[inv]; low = V[:, 1] < ARMPIT; out = np.zeros(len(V), bool)
    for c in np.unique(cv[low]):
        s = low & (cv == c)
        if s.sum() > 2 and np.abs(V[s, 0]).min() > .08: out |= s
    return out


def cut_shell(src, dst):
    """Keeps the shell above SEAM (sleeves whole) and returns the points of the cut edge."""
    m = trimesh.load(src, process=False).to_geometry(); V = np.asarray(m.vertices); F = np.asarray(m.faces)
    s = np.where(sleeves(V, F), 1.0, V[:, 1] - SEAM)
    P, F2, (N, UV) = S.cut(V, F, s, [np.asarray(m.vertex_normals), np.asarray(m.visual.uv)])
    u = np.unique(F2); r = -np.ones(len(P), int); r[u] = np.arange(len(u)); P, N, UV, F2 = P[u], N[u], UV[u], r[F2]
    S.export(dst, P, F2, N / (np.linalg.norm(N, axis=1)[:, None] + 1e-9), UV, m.visual.material.baseColorTexture)
    edge = P[(np.abs(P[:, 1] - SEAM) < 2e-3) & ~sleeves(P, F2)]
    return np.unique(np.round(edge, 4), axis=0)


def radius(P, c, ang, width, q):
    a = np.arctan2(P[:, 2] - c[1], P[:, 0] - c[0]); r = np.hypot(P[:, 0] - c[0], P[:, 2] - c[1]); out = np.full(len(ang), np.nan)
    for i, t in enumerate(ang):
        s = np.abs((a - t + np.pi) % (2 * np.pi) - np.pi) < width
        if s.sum() >= 3: out[i] = np.percentile(r[s], q)
    ok = ~np.isnan(out)
    return np.interp(np.arange(len(ang)), np.flatnonzero(ok), out[ok], period=len(ang)) if ok.any() else np.zeros(len(ang))


def build(dense_path, shell_path, garment_path, shell_out, tube_out, n, envelope=None):
    n = int(n); b = S.load_body(dense_path); BV = np.asarray(b.vertices)
    low = dense_path.replace('dense-', 'low-')            # the body that is drawn: where it stands outside the dense one (the bridge between the thighs), the cloth covers it too
    if low != dense_path and os.path.exists(low): BV = np.vstack([BV, trimesh.sample.sample_surface(S.load_body(low), 30000, seed=1)[0]])
    lab = L.limb(BV)
    arms = BV[(lab == 1) | (lab == 2)]; BV = BV[(lab != 1) & (lab != 2)]
    P = Garment(garment_path).vertices(); P = P[np.abs(P[:, 0]) < .21]
    edge = cut_shell(shell_path, shell_out)
    cen = edge[:, [0, 2]].mean(0); ang = np.arctan2(edge[:, 2] - cen[1], edge[:, 0] - cen[0]); o = np.argsort(ang); edge, ang = edge[o], ang[o]
    k = len(ang); width = np.pi / 12
    r0 = np.hypot(edge[:, 0] - cen[0], edge[:, 2] - cen[1])
    # hem per angle: the lowest of the garment at that angle
    a = np.arctan2(P[:, 2] - cen[1], P[:, 0] - cen[0]); hem = np.full(k, np.nan)
    for i, t in enumerate(ang):
        s = np.abs((a - t + np.pi) % (2 * np.pi) - np.pi) < width
        if s.sum() >= 5: hem[i] = np.percentile(P[s, 1], 3)
    hem = np.where(np.isnan(hem), np.nanmedian(hem), hem)
    rings = [edge]
    rp_seam = radius(P[np.abs(P[:, 1] - SEAM) < BAND], cen, ang, width, 90)
    if envelope is not None:
        ea = np.arctan2(envelope[:, 2] - cen[1], envelope[:, 0] - cen[0]); er = np.hypot(envelope[:, 0] - cen[0], envelope[:, 2] - cen[1])
    for j in range(1, n + 1):
        y = SEAM + (hem - SEAM) * j / n; ym = float(np.median(y))
        step = abs(float(np.median(hem)) - SEAM) / n / 2 + .01
        # what the garment widens (or narrows) from the seam down to here, added to the shell's radius at the seam: no step at the top
        r = r0 + (radius(P[np.abs(P[:, 1] - ym) < BAND], cen, ang, width, 90) - rp_seam)
        br = arms[np.abs(arms[:, 1] - ym) < step]
        if len(br):   # the hem passes between the hip and the arm
            ab = np.arctan2(br[:, 2] - cen[1], br[:, 0] - cen[0]); rb = np.hypot(br[:, 0] - cen[0], br[:, 2] - cen[1])
            for i, t in enumerate(ang):
                sb = np.abs((ab - t + np.pi) % (2 * np.pi) - np.pi) < width
                if sb.sum() >= 3: r[i] = min(r[i], rb[sb].min() - ARM_GAP)
        r = np.maximum(r, radius(BV[np.abs(BV[:, 1] - ym) < step], cen, ang, width, 100) + CLEAR)
        if envelope is not None:
            for i, t in enumerate(ang):   # at this angle's own height, and up to the ring above (the face between them does not cut the bottom)
                se = (np.abs((ea - t + np.pi) % (2 * np.pi) - np.pi) < width) & (envelope[:, 1] > y[i] - .01) & (envelope[:, 1] < y[i] + (SEAM - hem[i]) / n + .01)
                if se.sum() >= 3: r[i] = max(r[i], er[se].max() + S.RISE)
        rings.append(np.c_[cen[0] + r * np.cos(ang), y, cen[1] + r * np.sin(ang)])
    V = np.vstack(rings); F = []
    for i in range(n):
        for j in range(k):
            p, q = i * k + j, i * k + (j + 1) % k; F += [(p, q, p + k), (q, q + k, p + k)]
    F = np.array(F)
    if trimesh.Trimesh(V, F, process=False).volume < 0: F = F[:, ::-1]
    N = np.asarray(trimesh.Trimesh(V, F, process=False).vertex_normals)
    base = V - N * .03                                   # the texture rays leave 3 cm inside the tube
    dense, _ = trimesh.sample.sample_surface(trimesh.Trimesh(base, F, process=False), 40000, seed=1)
    V2, N2, UV, F2, img, missing = S.bake(S.Piece(garment_path), cKDTree(dense), dense, V, base, N, F, .10, limbs=False)
    S.export(tube_out, V2, F2, N2, UV, img)
    return {'triangles': int(len(F2)), 'sides': k, 'hem': [round(float(hem.min()), 2), round(float(hem.max()), 2)], 'texture_without_source_pct': round(100 * missing, 1)}


if __name__ == '__main__':
    a = sys.argv[1:]
    print(build(*a[:6], envelope=np.load(a[6]) if len(a) > 6 else None))
