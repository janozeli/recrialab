"""How much of a garment's identity the engine kept: the print, measured on the map from the rebuilt shape back
to the generated garment.

Every texel of a rebuilt shape (shell.bake) knows where it lies on the new shape and where its color came from on
the garment. Between neighboring texels of the same chart:
- a TEAR is a pair that is close on the new shape and far apart on the garment (the print jumps: a letter cut in
  two, a stripe that breaks);
- STRETCH is the length on the new shape over the length on the garment, along the height and around the body;
  their ratio is the print's distortion (a circle that becomes an oval), which the eye catches long before it
  catches a uniform change of size.
Only texels in view count: the low-poly mannequin is built in parts that run into each other (leg into hip, arm into
shoulder), and so is a shell over it; a texel with the shape itself less than HIDDEN in front of it is inside a joint
or faces the other leg, and what the print does there is not seen.
Each is reported for the whole garment and for its back (texels facing -z on the torso), where a tear shows most.
The garment side of the map is taken on the garment as published, before register.py moved it, so what the
registration stretched counts too.

CONTOUR is the other half of the identity: the lines a garment draws. A rule that puts every waistband and every hem
on a level line gives a garment that fits and no longer looks like itself (a waistband that dips in front, a shirt
tail, a V neck). contour() reads each edge of the garment as a profile, the height of the edge around the body and
the half-width of the silhouette along the height, on the published garment and on the rebuilt one, and compares
the two with their means removed: a slide or a uniform change of size costs nothing, a curve made straight does.
engine.py holds waistband, hem and silhouette under a limit and records the rest (a bottom's hem, a top's collar).
The girth at the waist is read on both too: a rebuilt garment much thinner than the published one lost its volume.
usage: from identity import measure; measure(trace, registered, published) with the trace shell.bake fills
       from identity import contour; contour(pid, published_points, rebuilt_points, body)"""
import numpy as np, trimesh
from scipy.spatial import cKDTree, ConvexHull
import landmarks as L

TEAR_RATIO, TEAR_MIN = 3.0, .005   # a pair this many times further apart on the garment than on the new shape, plus this (m)
BACK_NZ, TORSO_X = -.3, .16        # back: normal pointing back, between the arms
HIDDEN = .05                       # m: the shape itself this close in front of a texel hides it
SECTORS = 24                       # sectors around the body in which the height of an edge is read
NECK_R = .13                       # m: the collar is the cloth this close to the neck's axis
WAIST_Y, WAIST_UNDER = 1.06, .03   # m: height of a top's waist; a bottom's is read this far below its waistband


def measure(t, registered=None, published=None, where=None, above=None):
    """registered, published: shell.Piece of the garment the bake read and of the same garment before registration.
    where: a dict that receives the points of the tears on the new shape. above: only the texels above this height
    count (the shell of a garment that ends in a tube is cut there, and the tube carries the print below)."""
    if above is not None:
        keep = t['new'][:, 1] > above; t = {k: (v[keep] if isinstance(v, np.ndarray) and len(v) == len(keep) else v) for k, v in t.items()}
    if published is not None:
        f = registered.f[t['tri']]; b = trimesh.triangles.points_to_barycentric(registered.v[f], t['old'])
        t = dict(t, old=np.einsum('ij,ijk->ik', b, published.v[f]))
    V, F = t['shape']; shape = trimesh.Trimesh(V, F, process=False)
    hit = shape.ray.intersects_first(t['new'] + t['normal'] * .002, t['normal'])
    seen = np.ones(len(hit), bool); h = hit >= 0
    if h.any():
        loc, ir, it = shape.ray.intersects_location(t['new'][h] + t['normal'][h] * .002, t['normal'][h], multiple_hits=False)
        idx = np.flatnonzero(h)[ir]; seen[idx] = np.linalg.norm(loc - t['new'][idx], axis=1) > HIDDEN
        # ... and one that meets the shape from the inside lies within another part (the torso's side inside the shoulder)
        seen[idx] &= np.einsum('ij,ij->i', shape.face_normals[it], t['normal'][idx]) < 0
    t = {k: (v[seen] if isinstance(v, np.ndarray) and len(v) == len(seen) else v) for k, v in t.items()}
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


def profiles(pid, P, body):
    """The edges of a garment as profiles, from points P sampled on it: {edge: heights or half-widths, in m}."""
    v = np.asarray(body.vertices); lab = L.limb(v); near = lab[cKDTree(v).query(P)[1]]
    out = {}
    def around(Q, q, k=SECTORS):
        if len(Q) < 40 * k: return None
        return L.sectors(Q, Q[:, [0, 2]].mean(0), k, q)[1]
    def side(Q):
        lo, hi = np.percentile(Q[:, 1], [4, 96]); ys = np.arange(lo, hi, .02)
        return np.array([np.percentile(np.abs(Q[np.abs(Q[:, 1] - y) < .01, 0]), 98) if (np.abs(Q[:, 1] - y) < .01).sum() > 40 else np.nan for y in ys])
    if int(pid) <= 15:
        top = P[P[:, 1] > np.percentile(P[:, 1], 80)]
        out['waistband'] = L.sectors(P, top[:, [0, 2]].mean(0), SECTORS, 98)[1]
        if pid in L.SKIRTS: out['hem'] = around(P, 2)
        else:
            legs = [around(P[(P[:, 0] * s > .02) & (P[:, 1] < np.percentile(P[:, 1], 40))], 2, SECTORS // 2) for s in (1, -1)]
            out['hem'] = None if any(x is None for x in legs) else np.concatenate(legs)
        out['side'] = side(P)
    else:
        torso = P[~np.isin(near, (1, 2))]
        out['hem'] = around(torso[torso[:, 1] < np.percentile(torso[:, 1], 60)], 2)
        if out['hem'] is not None:                        # under the arms the sleeve hides the hem: front and back only
            ang = -np.pi + (np.arange(SECTORS) + .5) * 2 * np.pi / SECTORS; out['hem'] = out['hem'][np.abs(np.sin(ang)) > .5]
        neck = v[(v[:, 1] > 1.50) & (v[:, 1] < 1.56)][:, [0, 2]].mean(0)
        collar = P[(np.hypot(P[:, 0] - neck[0], P[:, 2] - neck[1]) < NECK_R) & (P[:, 1] > 1.35)]
        out['collar'] = L.sectors(collar, neck, SECTORS, 98)[1] if len(collar) > 40 * SECTORS else None
        out['side'] = side(torso[torso[:, 1] < 1.30])
        # the line of the back, seen in profile: a loose top hangs from the shoulder blades; one that follows the lumbar
        # and the glute reads as painted on the body
        mid = torso[(np.abs(torso[:, 0]) < .05) & (torso[:, 1] < 1.40)]; mid = mid[mid[:, 2] < np.median(torso[:, 2])]   # the back half only: below a back hem that ends higher, the front is not the back
        lo, hi = np.percentile(mid[:, 1], [4, 96]) if len(mid) > 400 else (0, 0)
        out['back'] = np.array([np.percentile(mid[np.abs(mid[:, 1] - y) < .01, 2], 2) if (np.abs(mid[:, 1] - y) < .01).sum() > 20 else np.nan for y in np.arange(lo, hi, .02)]) if hi > lo else None
    return out


def girth(pid, P, body):
    """Perimeter of the garment at the waist, in m (convex hull of its cut): a bottom WAIST_UNDER below its waistband, a
    top at WAIST_Y, sleeves left out. None where the garment does not reach."""
    if int(pid) <= 15: y = float(np.median(L.sectors(P, L.waist_center(P), SECTORS, 98)[1])) - WAIST_UNDER
    else:
        v = np.asarray(body.vertices); P = P[~np.isin(L.limb(v)[cKDTree(v).query(P)[1]], (1, 2))]; y = WAIST_Y
    cut = P[np.abs(P[:, 1] - y) < .01][:, [0, 2]]
    return float(ConvexHull(cut).area) if len(cut) > 200 else None


def contour(pid, published, rebuilt, body):
    """Per edge, in cm: relief of the published garment's edge (5th to 95th percentile), relief of the rebuilt one,
    and lost, the RMS difference between the two profiles with their means removed."""
    a, b = profiles(pid, published, body), profiles(pid, rebuilt, body); out = {}
    ga, gb = girth(pid, published, body), girth(pid, rebuilt, body)
    if ga and gb: out['waist'] = {'girth_cm': round(100 * ga, 1), 'girth_rebuilt_cm': round(100 * gb, 1)}
    for k in a:
        if a[k] is None or b.get(k) is None: continue
        f, g = a[k], b[k]
        if k in ('side', 'back'):                                   # the two run over different heights: compared along the garment
            f, g = f[~np.isnan(f)], g[~np.isnan(g)]
            if min(len(f), len(g)) < 4: continue
            x = np.linspace(0, 1, 24); f = np.interp(x, np.linspace(0, 1, len(f)), f); g = np.interp(x, np.linspace(0, 1, len(g)), g)
        if k == 'back':                                   # a back that leans is the same back: the lean is taken out too
            f, g = (p - np.polyval(np.polyfit(x, p, 1), x) for p in (f, g))
        relief = lambda p: float(np.percentile(p, 95) - np.percentile(p, 5))
        out[k] = {'relief_cm': round(100 * relief(f), 1), 'relief_rebuilt_cm': round(100 * relief(g), 1),
                  'lost_cm': round(100 * float(np.sqrt(np.mean(((f - f.mean()) - (g - g.mean())) ** 2))), 1)}
    return out
