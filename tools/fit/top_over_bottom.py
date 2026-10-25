"""Jacket over the pants: the hem of the top comes out from inside the waist of the bottom garments.

With 036 and 038 at body size (resize.py), the rib hem falls at the hip, where the pants' waistband is, and the pants
poke through the hem (layer_check.py). Like
displacement_field.py, but the collider is the union of the 15 bottom garments (from the hip up) and only the front
and back of the torso below the waist move (|x| < 20 cm, y < 1.08 m): what is closer than SLACK to some pair of pants
moves out along its normal, and the whole field is smoothed by a gaussian kernel of RADIUS, lining and outer cloth
together. Only positions and normals change; UV and texture stay. Refuses edge stretch p99 above MAX_STRETCH.
With --columns (rib hem, like the one on hoodie 037): the per-vertex field pulls the shell away from the inner fold
of the rib, and the fold then counts as lining hanging below the hem (site/fit.test.ts). Here only the front moves,
only in z, column by column (2 x 2 cm of x and height): each column advances what the shell needs to sit COL_SLACK in
front of the frontmost bottom garment from that height up, and shell and fold move together. The push fades out from
COL_HEM[1] down to COL_HEM[0] and towards the sides (|x| from 16 to 22 cm), and the field is smoothed by the kernel of
COL_RADIUS. x and y of every vertex stay as they were (hood.py --check).
usage: python3 tools/fit/top_over_bottom.py [--columns] IN.glb OUT.glb"""
import sys, numpy as np, trimesh
from scipy.ndimage import gaussian_filter
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix, diags
from garment import Garment, kernel
from metric import body
from paths import GARMENTS
from repose_sleeves import weights

SLACK = .005        # from each pair of pants (less leaves the pants poking through the hem)
RADIUS = .06        # smaller stretches the print past MAX_STRETCH
ROUNDS = 60
MAX_STRETCH = .10
HIP = .75           # of the pants, only from here up
COL_HEM = (.93, 1.02)
COL_SLACK = .008
COL_RADIUS = .08    # 6 cm stretches the print past 12%
COL_XMAX, COL_CELL = .22, .02


def columns(src, dst):
    B = body('B').vertices
    T = B[(np.abs(B[:, 0]) < .15) & (np.abs(B[:, 1] - 1.2) < .1)]; zc = (T[:, 2].min() + T[:, 2].max()) / 2
    y0, y1 = COL_HEM; yb = y0 - .23
    NX, NY = int(2 * COL_XMAX / COL_CELL), int((y1 + .05 - yb) / COL_CELL) + 1
    C = np.vstack([B[np.abs(B[:, 0]) < .19]] + [Garment(GARMENTS + f'{i:03d}.glb').vertices() for i in range(1, 16)])
    C = C[(C[:, 1] > yb) & (C[:, 1] < y1 + .05) & (np.abs(C[:, 0]) < COL_XMAX) & (C[:, 2] > zc)]

    def cell(p):
        return (np.clip(((p[:, 0] + COL_XMAX) / COL_CELL).astype(int), 0, NX - 1),
                np.clip(((p[:, 1] - yb) / COL_CELL).astype(int), 0, NY - 1))
    g = Garment(src); P0 = g.vertices()
    _, inv = np.unique(np.round(P0, 5), axis=0, return_inverse=True); inv = inv.ravel()
    X0 = np.zeros((inv.max() + 1, 3)); X0[inv] = P0
    # the sleeves stay where they are
    arm = np.zeros(len(X0)); np.maximum.at(arm, inv, np.maximum(weights(P0, 1, B)[1], weights(P0, -1, B)[1]))
    w = np.clip((y1 - X0[:, 1]) / (y1 - y0), 0, 1)
    w = w * w * (3 - 2 * w) * (1 - arm) * np.clip((COL_XMAX - np.abs(X0[:, 0])) / .06, 0, 1)
    front = np.zeros((NX, NY)); np.maximum.at(front, cell(C), C[:, 2] - zc)
    target = np.maximum.accumulate(front[:, ::-1], axis=1)[:, ::-1] + COL_SLACK   # frontmost from that height up
    k = (X0[:, 2] > zc) & (w > 0); xi, yi = cell(X0[k])
    shell = np.full((NX, NY), -np.inf); np.maximum.at(shell, (xi, yi), X0[k, 2] - zc); has = np.isfinite(shell)
    d = gaussian_filter(np.where(has, np.maximum(target - shell, 0), 0), 1.5, mode='nearest')
    d /= np.maximum(gaussian_filter(has.astype(float), 1.5, mode='nearest'), 1e-3)
    D = np.zeros_like(X0); D[k, 2] = d[xi, yi] * w[k]
    # the kernel carries the push around the hem to the sides and the back (555 vertices behind the torso's middle);
    # holding it to the front brings back the lining of the fold (66.7 cm2) and the threads of 007.037 (12.5)
    D = kernel(X0, COL_RADIUS) @ D; X = X0 + D
    E = trimesh.Trimesh(X0, inv[g.mesh(P0).faces], process=False).edges_unique
    L = np.linalg.norm(X0[E[:, 0]] - X0[E[:, 1]], axis=1)
    e = np.abs(np.linalg.norm(X[E[:, 0]] - X[E[:, 1]], axis=1) / np.maximum(L, 1e-9) - 1)
    moves = (np.linalg.norm(D, axis=1)[E] > 1e-4).any(1)   # the edges that stay would dilute the p99
    ps = np.percentile(e[moves], 99) if moves.any() else 0.
    print(f'{src}: stretch p99 {100 * ps:.1f}%; front moves up to {100 * D[:, 2].max():.1f} cm')
    if ps > MAX_STRETCH: sys.exit(f'{src}: print distorts too much; nothing written')
    g.save(dst, P0 + D[inv], before=P0)   # x and y exactly as they were (hood.py --check)


args = [a for a in sys.argv[1:] if a != '--columns']
if __name__ == '__main__' and len(args) != 2:
    sys.exit(__doc__)
elif __name__ == '__main__' and '--columns' in sys.argv:
    columns(*args)
elif __name__ == '__main__':
    src, dst = args
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
