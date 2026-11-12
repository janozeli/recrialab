"""Registers every garment to the mannequin's landmarks, with the same rule for all 38 (landmarks.py).

A fix per garment does not scale: each one moved a waistband, a hem or a cuff by its own numbers. Here the garment's
landmarks are taken to the mannequin's:
- bottom: the waistband goes level to the WAISTBAND LINE, BELOW_WAIST under the waist (the narrowest cut of the
  torso). Pants and shorts stretch only from their crotch up; a skirt moves whole and keeps its length;
- top: the hem never stays above the waistband line minus OVERLAP, so every top covers every waistband (no belly
  between the pieces, in any of the 345 looks): a shorter top stretches from the armpit down, front and back each
  by what it lacks. A long sleeve (ending below LONG_SLEEVE) ends BELOW_WRIST under the wrist, sliding along the arm
  axis, so the hand stays in view.
Sleeve or torso is decided by which the cloth is closer to, blended over a centimeter.
usage: python3 tools/fit/register.py IN.glb OUT.glb   (file names carry the piece id, NNN)
       python3 tools/fit/register.py --check          (registers the 38 in memory; fails if a registered garment misses the lines)"""
import sys, os, tempfile, numpy as np
from scipy.spatial import cKDTree
from garment import Garment
from metric import body, POSE_C
from paths import GARMENTS, piece_id
import landmarks as L

BELOW_WAIST = .07      # m: waistband line = waist - this
OVERLAP = .05          # m: a top comes down at least this far below the waistband line
LONG_SLEEVE = .95      # m: a sleeve that ends below this height is long
BELOW_WRIST = .02      # m: a long sleeve ends this far below the wrist
# --check: how far a registered garment may be from its line
WAIST_TOL, UNEVEN_MAX, HEM_TOL, SLEEVE_TOL = .01, .035, .006, .02


def lines(mb):
    w = round(mb['waist'] - BELOW_WAIST, 3)
    return {'waistband': w, 'top_hem_max': round(w - OVERLAP, 3), 'long_sleeve_end': round(mb['wrist'] - BELOW_WRIST, 3)}


def register(pid, src, dst, mb, axis, b):
    """Writes the registered garment to dst; returns its landmarks before and after."""
    g = Garment(src); P = g.vertices(); S = L.sample(src); before = L.garment(pid, S, mb, axis)
    ln = lines(mb); Q = P.copy(); y = P[:, 1]
    if int(pid) <= 15:
        c = L.waist_center(S); ang, top = L.sectors(S, c, 16, 98)
        top = np.convolve(np.r_[top[-1], top, top[0]], [.25, .5, .25], mode='valid')
        top = np.interp(np.arctan2(P[:, 2] - c[1], P[:, 0] - c[0]), np.r_[ang[-1] - 2 * np.pi, ang, ang[0] + 2 * np.pi], np.r_[top[-1], top, top[0]])
        if pid in L.SKIRTS:
            w = np.clip(1 - (before['waistband'] - y) / .15, 0, 1)
            Q[:, 1] = y + (ln['waistband'] - before['waistband']) + (before['waistband'] - top) * w
        else:
            base = before.get('crotch') or before['waistband'] - .18
            w = np.clip((y - base) / np.maximum(top - base, .02), 0, 1)
            Q[:, 1] = y + (ln['waistband'] - top) * w
    else:
        ap = mb['armpit']
        zc = float(np.median(S[np.abs(S[:, 0]) < .10, 2])); f = np.clip((P[:, 2] - zc) / .08, -1, 1) * .5 + .5
        hem = before['hem_front'] * f + before['hem_back'] * (1 - f)
        k = np.maximum(1, (ap - ln['top_hem_max']) / (ap - hem)); yt = np.where(y < ap, ap - (ap - y) * k, y)
        V = np.asarray(b.vertices); arm = np.isin(L.limb(V), (1, 2))
        da = cKDTree(V[arm]).query(P)[0]; dt = cKDTree(V[~arm]).query(P)[0]
        w = np.where(y < ap, 1 / (1 + np.exp(-(dt - da) / .01)), 0)
        ya = yt
        if before['sleeve'] is not None and before['sleeve'] < LONG_SLEEVE:
            ka = (ap - ln['long_sleeve_end']) / (ap - before['sleeve']); ya = np.where(y < ap, ap - (ap - y) * ka, y)
            for side in (1, -1):
                ys, c, _ = axis[side]; s = P[:, 0] * side > 0
                for j in (0, 2):
                    Q[s, j] += w[s] * (np.interp(ya[s], ys, c[:, j]) - np.interp(y[s], ys, c[:, j]))
        Q[:, 1] = (1 - w) * yt + w * ya
    g.save(dst, Q, before=P)
    return before, L.garment(pid, L.sample(dst), mb, axis), float(np.abs(Q - P).max())


def misses(pid, before, after, ln):
    bad = []
    if int(pid) <= 15:
        if abs(after['waistband'] - ln['waistband']) > WAIST_TOL: bad.append(f'waistband at {after["waistband"]}, line {ln["waistband"]}')
        if after['waistband_uneven'] > UNEVEN_MAX: bad.append(f'waistband uneven by {after["waistband_uneven"]}, max {UNEVEN_MAX}')
    else:
        for k in ('hem_front', 'hem_back'):
            if after[k] > ln['top_hem_max'] + HEM_TOL: bad.append(f'{k} at {after[k]}, at most {ln["top_hem_max"]}')
        if before['sleeve'] is not None and before['sleeve'] < LONG_SLEEVE and abs(after['sleeve'] - ln['long_sleeve_end']) > SLEEVE_TOL:
            bad.append(f'long sleeve ends at {after["sleeve"]}, line {ln["long_sleeve_end"]}')
    return bad


if __name__ == '__main__':
    B = {p: body(p) for p in 'BC'}; mb = L.recorded(); axis = L.arm_axis(B['B'])
    if '--check' in sys.argv:
        fail = 0; ln = lines(mb); print('lines:', ln)
        with tempfile.TemporaryDirectory() as tmp:
            for n in range(1, 39):
                pid = f'{n:03d}'
                before, after, moved = register(pid, GARMENTS + f'{pid}.glb', os.path.join(tmp, f'{pid}.glb'), mb, axis, B['C' if pid in POSE_C else 'B'])
                bad = misses(pid, before, after, ln); fail += bool(bad)
                print(pid, f'moved up to {moved * 100:.1f} cm', '; '.join(bad) or 'ok')
        sys.exit(1 if fail else 0)
    src, dst = sys.argv[1:3]; pid = piece_id(src)
    before, after, moved = register(pid, src, dst, mb, axis, B['C' if pid in POSE_C else 'B'])
    print(pid, 'before', before, 'after', after, f'moved up to {moved * 100:.1f} cm')
