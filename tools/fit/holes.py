"""Holes in the front of the bottoms: small boundary loops (perimeter < 15 cm) on the front, from the crotch up.
The generated mesh can leave tears at the fly (006 had one just below the button, with the mannequin showing
through it); closed, the loop becomes a zero-width seam. The leg hems and the waist are large loops and do not count.
usage: python3 tools/fit/holes.py [--close INPUT.glb OUTPUT.glb] [IDs]   (without IDs: the 15 bottoms; exits with an error on a hole)"""
import sys, numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from garment import Garment
from paths import GARMENTS


PERIMETER = .15
OPENING = .002  # a flattened loop (a seam) has zero opening


def holes(g):
    """Small loops on the front: a list of indices (of the welded vertices) and the vertex -> welded map."""
    m = g.mesh()
    _, inv = np.unique(np.round(m.vertices, 5), axis=0, return_inverse=True); inv = inv.ravel()
    F = inv[m.faces]; X = np.zeros((inv.max() + 1, 3)); X[inv] = m.vertices
    E = np.sort(np.vstack([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]), axis=1)
    u, c = np.unique(E, axis=0, return_counts=True); b = u[c == 1]
    if not len(b): return [], inv, X
    _, lab = connected_components(coo_matrix((np.ones(len(b)), (b[:, 0], b[:, 1])), shape=(len(X), len(X))), directed=False)
    out = []
    for L in np.unique(lab[b[:, 0]]):
        ed = b[lab[b[:, 0]] == L]; idx = np.unique(ed)
        per = np.linalg.norm(X[ed[:, 0]] - X[ed[:, 1]], axis=1).sum(); c0 = X[idx].mean(0)
        opening = np.ptp((X[idx] - c0) @ np.linalg.svd(X[idx] - c0)[2][1]) if len(idx) > 2 else 0
        if per < PERIMETER and opening > OPENING and c0[1] > .85 and c0[2] > 0 and abs(c0[0]) < .1: out.append(idx)
    return out, inv, X


def close(src, dst):
    """Closes each hole by flattening the loop onto the line that crosses it most (the tear becomes a seam)."""
    g = Garment(src); P0 = g.vertices(); loops, inv, X = holes(g); Y = X.copy()
    for idx in loops:
        c0 = X[idx].mean(0); _, _, vt = np.linalg.svd(X[idx] - c0); axis = vt[0]
        Y[idx] = c0 + np.outer((X[idx] - c0) @ axis, axis)
    g.save(dst, Y[inv], before=P0)
    print(f'{src}: {len(loops)} hole(s) closed, largest displacement {100 * np.linalg.norm(Y - X, axis=1).max():.1f} cm')


if __name__ == '__main__':
    a = sys.argv[1:]
    if a[:1] == ['--close']: close(a[1], a[2]); sys.exit()
    bad = []
    for pid in a or [f'{i:03d}' for i in range(1, 16)]:
        loops, _, X = holes(Garment(GARMENTS + f'{pid}.glb'))
        for idx in loops: bad.append(f'{pid} hole at y={X[idx, 1].mean():.3f} x={X[idx, 0].mean():.3f}')
    print('\n'.join(bad) or 'no holes')
    if bad: sys.exit('holes on the front: ' + str(len(bad)))
