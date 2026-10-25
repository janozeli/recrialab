"""Jacket over the pants: the hem of the top comes out from inside the waist of the bottom garments.

With 036 and 038 at body size (resize.py), the rib hem falls at the hip, where the pants' waistband is, and the pants
poke through the hem (layer_check.py). Like
displacement_field.py, but the collider is the union of the 15 bottom garments (from the hip up) and only the front
and back of the torso below the waist move (|x| < 20 cm, y < 1.08 m): what is closer than SLACK to some pair of pants
moves out along its normal, and the whole field is smoothed by a gaussian kernel of RADIUS, lining and outer cloth
together. Only positions and normals change; UV and texture stay. Refuses edge stretch p99 above MAX_STRETCH.
usage: python3 tools/fit/top_over_bottom.py IN.glb OUT.glb"""
import sys, numpy as np, trimesh
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix, diags
from garment import Garment
from paths import GARMENTS

SLACK = .005        # from each pair of pants (less leaves the pants poking through the hem)
RADIUS = .06        # smaller stretches the print past MAX_STRETCH
ROUNDS = 60
MAX_STRETCH = .10
HIP = .75           # of the pants, only from here up

if __name__ == '__main__':
    src, dst = sys.argv[1:3]
    Ss, Ns = [], []
    for i in range(1, 16):
        m = Garment(GARMENTS + f'{i:03d}.glb').mesh()
        s, fi = trimesh.sample.sample_surface_even(m, 60000, seed=1); k = s[:, 1] > HIP
        Ss.append(s[k]); Ns.append(m.face_normals[fi][k])
    S, SN = np.vstack(Ss), np.vstack(Ns)
    # normal pointing away from the body axis: lining and outer cloth of the pants have opposite normals
    r = S * [1, 0, 1]; SN *= np.sign(np.einsum('ij,ij->i', SN, r))[:, None]
    ST = cKDTree(S)
    g = Garment(src); P0 = g.vertices(); m = g.mesh(P0)
    # weld the vertices duplicated along UV seams: the cloth is one piece
    _, inv = np.unique(np.round(P0, 5), axis=0, return_inverse=True); inv = inv.ravel()
    X0 = np.zeros((inv.max() + 1, 3)); X0[inv] = P0; F = inv[m.faces]
    E = trimesh.Trimesh(X0, F, process=False).edges_unique
    L = np.linalg.norm(X0[E[:, 0]] - X0[E[:, 1]], axis=1)
    pairs = cKDTree(X0).query_pairs(2 * RADIUS, output_type='ndarray')
    i = np.r_[pairs[:, 0], pairs[:, 1], np.arange(len(X0))]; j = np.r_[pairs[:, 1], pairs[:, 0], np.arange(len(X0))]
    K = coo_matrix((np.exp(-(np.linalg.norm(X0[i] - X0[j], axis=1) / RADIUS) ** 2), (i, j)), shape=(len(X0),) * 2).tocsr()
    K = diags(1 / np.asarray(K.sum(1)).ravel()) @ K
    zone = ((X0[:, 1] < 1.08) & (np.abs(X0[:, 0]) < .2)).astype(float)[:, None]
    D = np.zeros_like(X0)
    for _ in range(ROUNDS):
        X = X0 + D; d, jj = ST.query(X); sd = np.einsum('ij,ij->i', X - S[jj], SN[jj])
        near = (d < .04) & (sd < SLACK)
        D[near] += (SLACK - sd[near])[:, None] * SN[jj[near]]
        D = zone * (K @ D)
    X = X0 + D
    e = np.abs(np.linalg.norm(X[E[:, 0]] - X[E[:, 1]], axis=1) / np.maximum(L, 1e-9) - 1)
    ps = np.percentile(e, 99); n = np.linalg.norm(D, axis=1)[zone[:, 0] > 0]
    print(f'{src}: stretch p99 {100 * ps:.1f}%; displacement median {100 * np.median(n):.1f}, max {100 * n.max():.1f} cm')
    if ps > MAX_STRETCH: sys.exit(f'{src}: print distorts too much; nothing written')
    g.save(dst, X[inv], before=P0)
