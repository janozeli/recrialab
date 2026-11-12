"""How much of a garment's identity the engine kept: the print, measured on the map from the rebuilt shape back
to the generated garment.

Every texel of a rebuilt shape (shell.bake) knows where it lies on the new shape and where its color came from on
the garment. Between neighboring texels of the same chart:
- a TEAR is a pair that is close on the new shape and far apart on the garment (the print jumps: a letter cut in
  two, a stripe that breaks);
- STRETCH is the length on the new shape over the length on the garment, along the height and around the body;
  their ratio is the print's distortion (a circle that becomes an oval), which the eye catches long before it
  catches a uniform change of size.
Each is reported for the whole garment and for its back (texels facing -z on the torso), where a tear shows most.
The garment side of the map is taken on the garment as published, before register.py moved it, so what the
registration stretched counts too.
usage: from identity import measure; measure(trace, registered, published) with the trace shell.bake fills"""
import numpy as np, trimesh

TEAR_RATIO, TEAR_MIN = 3.0, .005   # a pair this many times further apart on the garment than on the new shape, plus this (m)
BACK_NZ, TORSO_X = -.3, .16        # back: normal pointing back, between the arms


def measure(t, registered=None, published=None, where=None):
    """registered, published: shell.Piece of the garment the bake read and of the same garment before registration.
    where: a dict that receives the points of the tears on the new shape."""
    if published is not None:
        f = registered.f[t['tri']]; b = trimesh.triangles.points_to_barycentric(registered.v[f], t['old'])
        t = dict(t, old=np.einsum('ij,ijk->ik', b, published.v[f]))
    n = t['size']; new = np.full((n, n, 3), np.nan); old = np.full((n, n, 3), np.nan); nz = np.zeros((n, n))
    new[t['y'], t['x']] = t['new']; old[t['y'], t['x']] = t['old']; nz[t['y'], t['x']] = t['normal'][:, 2]
    out = {}; pairs = []
    for a, b in ((np.s_[:, :-1], np.s_[:, 1:]), (np.s_[:-1, :], np.s_[1:, :])):
        dn = new[b] - new[a]; do = old[b] - old[a]; ok = ~np.isnan(dn[..., 0]) & ~np.isnan(do[..., 0])
        ln = np.linalg.norm(dn[ok], axis=1); lo = np.linalg.norm(do[ok], axis=1)
        vertical = np.abs(dn[ok][:, 1]) > .7 * ln
        horizontal = np.abs(dn[ok][:, 1]) < .3 * ln
        back = (nz[a][ok] < BACK_NZ) & (np.abs(new[a][ok][:, 0]) < TORSO_X)
        pairs.append((ln, lo, vertical, horizontal, back, new[a][ok]))
    ln, lo, vertical, horizontal, back, at = (np.concatenate(x) for x in zip(*pairs))
    near = ln < np.percentile(ln, 99)                       # pairs across a chart border lie far apart on the new shape too
    tear = near & (lo > TEAR_RATIO * ln + TEAR_MIN)
    if where is not None: where['tears'] = at[tear]
    out['tear_cm'] = round(100 * float(ln[tear].sum()), 1); out['tear_back_cm'] = round(100 * float(ln[tear & back].sum()), 1)
    out['tear_pct'] = round(100 * float(tear[near].mean()), 2)
    out['tear_back_pct'] = round(100 * float(tear[near & back].mean()), 2) if (near & back).any() else 0.0
    good = near & ~tear & (lo > 1e-5)
    sv = float(np.median(ln[good & vertical] / lo[good & vertical])); sh = float(np.median(ln[good & horizontal] / lo[good & horizontal]))
    out['stretch_height'] = round(sv, 3); out['stretch_around'] = round(sh, 3); out['distortion'] = round(sv / sh, 3)
    return out
