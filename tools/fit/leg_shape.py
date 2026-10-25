"""Reshapes each leg of the pants into the shape of the neutral body's leg, with the same amount of cloth.

The pants came from Tripo with the leg deeper than wide (a 0.20 by 0.14 m section at the thigh of 006) and shifted
inward, on a mannequin with a narrower thigh. The neutral body has a thigh wider than deep: the pant leg has cloth to
spare (perimeter 1.2 to 1.8 times the leg's), but thigh and shin poke through at the side. On the pants where
pushing out only what pokes through stretches too much, here the whole section of each leg changes shape, height by
height:
  1. the smooth curve of the pant leg (median radius per angle, around its center) and that of the body's leg
     (around the body's center) are measured in slices of DY;
  2. the body curve grows uniformly until it has the same perimeter as the pant curve (even slack all around);
  3. each point of the pants goes to the new curve by arc length from the front (the cloth does not stretch around),
     and its relief over the smooth curve (folds, pockets, seams) goes along, along the curve normal.
  4. the cloth settles (repose_sleeves.arap, soft target with weight K): the map alone stretches the print 50 to 75%
     at p99, because the new curve of each slice does not follow the neighboring one; ARAP restores the edge lengths.
     Cloth that was outside the body and that settling would carry inside becomes a firm anchor at its former distance.
From the crotch up nothing changes (the transition goes from TOP - BAND to TOP; on 014, TOP_PIECES takes the leg up
to near the crotch). Only positions and normals change; UV and texture stay. Where the pant leg has no cloth for
MIN_SLACK all around, the slice stays as it is. Refuses (writes nothing) if the cloth stretches past the limit, region
by region (pant_leg_cloth.MAX).
usage: python3 tools/fit/leg_shape.py IN.glb OUT.glb [NNN] [--again]   (then install.py --bottom NNN, with the new mask joined
       to the previous one: the regenerated one hides less body at the side of the thigh and it shows through the
       cloth in the showcase)"""
import sys, numpy as np, trimesh
from scipy.spatial import cKDTree
from scipy.ndimage import gaussian_filter1d
from garment import Garment
from repose_sleeves import arap
from separate_legs import leg_side
from metric import body, POSE_C

DY = .01             # slice (m)
NA = 72              # angles per turn
TOP = .80            # above this nothing changes (the neutral body's crotch is at 0.83 m; each leg only moves below)
BAND = .25           # transition up to TOP
HIP = (.86, .92)     # the hip becomes a single section above the crotch, with a transition
SHOE = (.20, .40)    # below 0.15 m the body is the sneaker: the hem stays (with a 5 cm margin, else the slack over the sneaker grows), transition up to 0.40
SMOOTH_Y, SMOOTH_A = 3, 3   # smoothing of the smooth curve (slices, angles)
MIN_SLACK = .004     # minimum even slack around the leg (m)
MAX_STRETCH = .10    # p99 of the length change of the edges that move
K = (.1, .05, .025)  # target weight when settling, from firmest to loosest (smaller: stretches less, reshapes less)
ROUNDS = 20
HOLD = 4             # anchor rounds for cloth that would go into the body
ARM_X = .17
# pieces whose hip becomes a single section: there it lowers the poke-through at the waistband; on the other pants
# it raises the pokes or the slack
HIP_PIECES = {
    '012',
    '013',
}
HIP_STRETCH = .08    # how much the hip circumference may stretch to fit the body
# pieces whose leg changes up to near the crotch (top, band): their thigh pokes through at the side from 0.62 to
# 0.80 m, where the default transition barely moves it
TOP_PIECES = {
    '014': (.86, .20),
    '006': (.86, .20),
}
SHOE_PIECES = {'013': (.10, .25)}   # 013: the elastic cuff sits at the ankle, above the sneaker; the leg changes down to it


def curve(P, c, ys):
    """Median radius per (slice, angle) of the points P (one side only) around the centers c[slice]; NaN where empty."""
    i = np.clip(np.round((P[:, 1] - ys[0]) / DY).astype(int), 0, len(ys) - 1)
    d = P[:, [0, 2]] - c[i]
    a = (np.arctan2(d[:, 0], d[:, 1]) % (2 * np.pi)) / (2 * np.pi) * NA   # angle 0 = front (+z)
    j = np.floor(a).astype(int) % NA; r = np.hypot(d[:, 0], d[:, 1])
    R = np.full((len(ys), NA), np.nan)
    for k in np.unique(i * NA + j):
        sel = (i * NA + j) == k
        R[k // NA, k % NA] = np.median(r[sel])
    return R


def fill(R):
    """NaN by circular interpolation in each slice, then smoothing (circular in angle)."""
    R = R.copy()
    for f in range(len(R)):
        ok = np.isfinite(R[f])
        if ok.sum() < 4: R[f] = np.nan; continue
        x = np.nonzero(ok)[0]
        R[f] = np.interp(np.arange(NA), np.r_[x - NA, x, x + NA], np.tile(R[f, ok], 3))
    ok = np.isfinite(R).all(1)
    R[ok] = gaussian_filter1d(R[ok], SMOOTH_A, axis=1, mode='wrap')
    return R


def perimeter(R):
    t = np.linspace(0, 2 * np.pi, NA, endpoint=False)
    X, Z = R * np.sin(t), R * np.cos(t)
    return np.hypot(np.roll(X, -1, -1) - X, np.roll(Z, -1, -1) - Z).sum(-1)


def arc(R):
    """Cumulative (normalized) arc length per angle, from the front."""
    t = np.linspace(0, 2 * np.pi, NA + 1)
    Rr = np.c_[R, R[:, :1]]
    X, Z = Rr * np.sin(t), Rr * np.cos(t)
    s = np.c_[np.zeros(len(R)), np.cumsum(np.hypot(np.diff(X), np.diff(Z)), 1)]
    return s / s[:, -1:]


def centers(P, ys):
    c = np.full((len(ys), 2), np.nan)
    i = np.round((P[:, 1] - ys[0]) / DY).astype(int)
    for f in range(len(ys)):
        q = P[i == f][:, [0, 2]]
        if len(q) > 8: c[f] = (q.min(0) + q.max(0)) / 2
    ok = np.isfinite(c[:, 0])
    for k in range(2): c[:, k] = np.interp(np.arange(len(ys)), np.nonzero(ok)[0], c[ok, k])
    return gaussian_filter1d(c, SMOOTH_Y, axis=0, mode='nearest')


def leg_ramp(y, top=TOP, band=BAND, shoe=SHOE):
    """How much the leg changes at each height: nothing from the crotch up nor at the hem over the sneaker."""
    return np.clip((top - y) / band, 0, 1) * np.clip((y - shoe[0]) / (shoe[1] - shoe[0]), 0, 1)


def hip_ramp(y):
    """How much the hip changes: nothing at the crotch (the two legs are not one section yet), fully from HIP[1] up."""
    return np.clip((y - HIP[0]) / (HIP[1] - HIP[0]), 0, 1)


def reshape(P, B, ramp=leg_ramp, top=TOP, stretch=0):
    """New positions of the points P of a section (one leg, or the hip up to the waistband) up to height top."""
    ys = np.arange(min(P[:, 1].min(), B[:, 1].min()) - DY, top + DY, DY)
    cg, cb = centers(P, ys), centers(B, ys)
    Rg, Rb = fill(curve(P, cg, ys)), fill(curve(B, cb, ys))
    ok = np.isfinite(Rg).all(1) & np.isfinite(Rb).all(1)
    near = np.nonzero(ok)[0][np.abs(np.arange(len(ys))[:, None] - np.nonzero(ok)[0]).argmin(1)]
    Rg, Rb = Rg[near], Rb[near]   # slice without pants or without body: the nearest one that has both
    Rg = gaussian_filter1d(Rg, SMOOTH_Y, axis=0, mode='nearest'); Rb = gaussian_filter1d(Rb, SMOOTH_Y, axis=0, mode='nearest')
    slack = (perimeter(Rg) - perimeter(Rb)) / (2 * np.pi)
    # where the pants have no cloth for the minimum slack all around (the tight hem at the ankle), the slice stays;
    # at the hip the circumference may stretch up to `stretch` to get the minimum slack
    short = (perimeter(Rb) + 2 * np.pi * MIN_SLACK) / perimeter(Rg) - 1
    fits = np.clip((slack - MIN_SLACK) / .005, 0, 1) if not stretch else np.clip((stretch - short) / .01, 0, 1)
    w_f = gaussian_filter1d(fits * ok, SMOOTH_Y, mode='nearest')
    held = fits < 1
    slack = np.maximum(slack, MIN_SLACK)
    Rt = Rb + slack[:, None]
    Sg, St = arc(Rg)[:, :NA], arc(Rt)[:, :NA]
    # each point: slice, angle and relief over the smooth curve of the pants
    f = np.clip((P[:, 1] - ys[0]) / DY, 0, len(ys) - 1.001); f0 = f.astype(int); w = f - f0
    lerp = lambda A: A[f0] * (1 - w)[:, None] + A[f0 + 1] * w[:, None] if A.ndim == 2 else A[f0] * (1 - w) + A[f0 + 1] * w
    c_g, c_b = lerp(cg), lerp(cb)
    d = P[:, [0, 2]] - c_g; r = np.hypot(d[:, 0], d[:, 1])
    a = (np.arctan2(d[:, 0], d[:, 1]) % (2 * np.pi)) / (2 * np.pi) * NA
    def at(A, a):   # value of curve A (at the point's slice) at angle a (fractional, circular)
        L = lerp(A); j0 = np.floor(a).astype(int) % NA; j1 = (j0 + 1) % NA; u = a - np.floor(a)
        return L[np.arange(len(a)), j0] * (1 - u) + L[np.arange(len(a)), j1] * u
    relief = r - at(Rg, a)
    Lg = lerp(np.c_[Sg, np.ones(len(ys))]); j0 = np.clip(np.floor(a).astype(int), 0, NA - 1); u = a - j0
    s = Lg[np.arange(len(a)), j0] * (1 - u) + Lg[np.arange(len(a)), j0 + 1] * u   # arc of the pants at the point's angle
    # angle on the new curve with the same arc: inverts St per slice
    Lt = lerp(np.c_[St, np.ones(len(ys))])
    a2 = np.array([np.interp(s[k], Lt[k], np.arange(NA + 1)) for k in range(len(P))])
    r2 = at(Rt, a2) + relief
    t2 = a2 / NA * 2 * np.pi
    new = P.copy(); new[:, 0] = c_b[:, 0] + r2 * np.sin(t2); new[:, 2] = c_b[:, 1] + r2 * np.cos(t2)
    weight = ramp(P[:, 1]); weight = weight ** 2 * (3 - 2 * weight) * lerp(w_f)
    valid = np.isfinite(new).all(1)
    out = P.copy(); out[valid] = P[valid] + (new[valid] - P[valid]) * weight[valid, None]
    full = ok & (ramp(ys) >= 1)
    return out, held[full], ys[full]


def distance(X, kd, b):
    """Signed distance to the body (positive outside), along the normal of the nearest body vertex; and that normal."""
    i = kd.query(X)[1]; n = b.vertex_normals[i]
    return np.einsum('ij,ij->i', X - b.vertices[i], n), n


def stretch(X0, X, FF):
    """p99 of the length change of the edges that move per region (pant_leg_cloth.regions: the middle between the legs,
    the cuff and the rest), on the MAX_STRETCH scale: each region against its own limit in pant_leg_cloth.MAX (the
    elastic cuff stretches around the ankle; the rest, MAX_STRETCH). Measured per region because in the p99 of the
    whole piece a small region, like the bridge between the legs, does not show."""
    from pant_leg_cloth import measures, MAX
    m = measures(X0, X, FF, moved=np.linalg.norm(X - X0, axis=1) > 1e-4)[0]
    return max(m[k][0] / MAX[k][0] for k in m) * MAX_STRETCH, ', '.join(f'{k} {100 * e:.1f}%' for k, (e, _) in m.items())


def dress(src, dst, pid, again=False):
    """again: the input already went through here (the published GLB, after separate_legs.py): the hip and the leg
    up to the crotch (HIP_PIECES, TOP_PIECES) already sit on the body, and redoing them would stretch them again."""
    g = Garment(src); P0 = g.vertices(); faces = g.mesh(P0).faces
    b = body('C' if pid in POSE_C else 'B'); V = b.vertices
    V = V[~((np.abs(V[:, 0]) > ARM_X) & (V[:, 1] > .6))]
    P = P0.copy(); top, band = (TOP, BAND) if again else TOP_PIECES.get(pid, (TOP, BAND)); shoe = SHOE_PIECES.get(pid, SHOE)
    sides = leg_side(P0, faces)
    for side in (1, -1):
        sel = (sides == side) & (P0[:, 1] < top)
        Bl = V[(np.sign(V[:, 0]) == side) & (V[:, 1] < top + DY)]
        P[sel], fo, yf = reshape(P0[sel], Bl, lambda y: leg_ramp(y, top, band, shoe), top)
        held = yf[fo]
        if len(held): print(f'  {"left" if side > 0 else "right"} leg: stays where cloth is short, y {held.min():.2f} to {held.max():.2f} m')
    # the hip up to the waistband: a single section around both legs, where there is cloth for it
    if pid in HIP_PIECES and not again:
        ytop = P0[:, 1].max(); sel = P0[:, 1] > HIP[0] - DY
        P[sel], fo, yf = reshape(P[sel], V[(V[:, 1] > HIP[0] - 2 * DY) & (V[:, 1] < ytop + DY)], hip_ramp, ytop, HIP_STRETCH)
        held = yf[fo]
        if len(held): print(f'  hip: stays where cloth is short, y {held.min():.2f} to {held.max():.2f} m')
    # a UV seam becomes a single vertex, so both sides move together
    _, inv = np.unique(np.round(P0, 5), axis=0, return_inverse=True); inv = inv.ravel()
    X0 = np.zeros((inv.max() + 1, 3)); X0[inv] = P0; T = np.zeros_like(X0); T[inv] = P
    # pants with the legs joined by a bridge of cloth down to the ankle (the section is a figure eight): separate_legs.py
    # first, otherwise the bridge stretches and the piece is refused
    FF = inv[faces]
    E = trimesh.Trimesh(X0, FF, process=False).edges_unique
    # what the map does not move (hem on the sneaker, from the crotch up) stays pinned: settling does not drag it
    still = np.linalg.norm(T - X0, axis=1) < 1e-5
    # cloth that was outside the body does not go into it: where settling carried it inside (or closer than
    # MIN_SLACK, if it was farther), it becomes a firm anchor at its former distance, and the cloth settles again
    kd = cKDTree(b.vertices); s0 = distance(X0, kd, b)[0]; floor = np.minimum(s0, MIN_SLACK)
    for k in K:
        Tk, pinned = T.copy(), 1 + 1e4 * still
        for _ in range(HOLD):
            X = arap(X0, Tk, E, pinned, rounds=ROUNDS, K=k)
            s1, n = distance(X, kd, b); enters = (s0 > 0) & (s1 < floor - 1e-3) & ~still
            if not enters.any(): break
            Tk[enters] = X[enters] + n[enters] * (floor[enters] - s1[enters])[:, None]; pinned[enters] = 1e3 / k
        P = X[inv]
        moved = np.linalg.norm(P - P0, axis=1) > 1e-4
        est, regions = stretch(X0, X, FF)
        if est <= MAX_STRETCH: break
    print(f'  cloth that would go into the body: {enters.sum()} vertices')
    d = np.linalg.norm(P - P0, axis=1)
    print(f'{src}: settled with K {k}, stretch p99 {regions}, '
          f'largest displacement {100 * d.max():.1f} cm, {moved.sum()} vertices')
    if est > MAX_STRETCH: sys.exit(f'refused: stretches too much ({regions}; limits in pant_leg_cloth.MAX)')
    g.save(dst, P, before=P0)


if __name__ == '__main__':
    a = [x for x in sys.argv[1:] if x != '--again']; src, dst = a[:2]
    pid = a[2] if len(a) > 2 else __import__('re').search(r'(\d{3})', src).group(1)
    dress(src, dst, pid, '--again' in sys.argv)
