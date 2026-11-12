"""Registers every garment to the mannequin's landmarks, with the same rule for all 38 (landmarks.py).

A fix per garment does not scale: each one moved a waistband, a hem or a cuff by its own numbers. Here the garment's
landmarks are taken to the mannequin's, without changing what makes the garment itself: a move is either a slide of
the whole garment, which keeps every proportion, or a stretch of at most MAX_STRETCH, below what the eye catches in
a print. What the cap leaves undone stays undone: a cropped top stays cropped, a 3/4 sleeve stays 3/4.
- bottom: the whole garment slides until its waistband sits on the WAISTBAND LINE, BELOW_WAIST under the waist (the
  narrowest cut of the torso), so legs and skirt keep their length; then the waistband is leveled, stretching only
  from the crotch up and only up to the cap;
- top: the hem should not stay above the waistband line minus OVERLAP, so the top covers the waistband: a shorter
  top is scaled in height from the shoulder down, body and sleeves alike (its proportions hold), up to the cap. A
  long sleeve (ending below LONG_SLEEVE) is scaled along the arm toward BELOW_WRIST under the wrist, up to the cap.
Sleeve or torso is decided by which the cloth is closer to, blended over a centimeter.
usage: python3 tools/fit/register.py IN.glb OUT.glb   (file names carry the piece id, NNN)
       python3 tools/fit/register.py --check          (registers the 38 in memory; fails if a garment neither reaches its line nor
                                                       used the whole cap, or if a waistband is off the line)"""
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
MAX_STRETCH = 1.06     # largest stretch in one direction: a print distorted beyond this reads as deformed
# --check: how far a registered garment may be from its line
WAIST_TOL, HEM_TOL, SLEEVE_TOL = .01, .006, .02


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
        base = before.get('crotch') or before['waistband'] - .18
        rise = np.maximum(top - base, .02); level = np.clip(before['waistband'] - top, -(MAX_STRETCH - 1) * rise, (MAX_STRETCH - 1) * rise)
        Q[:, 1] = y + (ln['waistband'] - before['waistband']) + level * np.clip((y - base) / rise, 0, 1)
        stretch = float(1 + np.abs(level / rise).max())
    else:
        sh, ap = mb['shoulder'], mb['armpit']
        zc = float(np.median(S[np.abs(S[:, 0]) < .10, 2])); f = np.clip((P[:, 2] - zc) / .08, -1, 1) * .5 + .5
        hem = before['hem_front'] * f + before['hem_back'] * (1 - f)
        k = np.clip((sh - ln['top_hem_max']) / (sh - hem), 1, MAX_STRETCH); yt = np.where(y < sh, sh - (sh - y) * k, y)
        V = np.asarray(b.vertices); arm = np.isin(L.limb(V), (1, 2))
        da = cKDTree(V[arm]).query(P)[0]; dt = cKDTree(V[~arm]).query(P)[0]
        w = np.where(y < ap, 1 / (1 + np.exp(-(dt - da) / .01)), 0)
        ka = float(np.mean(k))                               # a short sleeve grows with the body of the top
        if before['sleeve'] is not None and before['sleeve'] < LONG_SLEEVE:
            ka = float(np.clip((sh - ln['long_sleeve_end']) / (sh - before['sleeve']), 1 / MAX_STRETCH, MAX_STRETCH))
        ya = np.where(y < sh, sh - (sh - y) * ka, y)
        for side in (1, -1):
            ys, c, _ = axis[side]; s = P[:, 0] * side > 0
            for j in (0, 2):
                Q[s, j] += w[s] * (np.interp(ya[s], ys, c[:, j]) - np.interp(y[s], ys, c[:, j]))
        Q[:, 1] = (1 - w) * yt + w * ya
        stretch = float(max(k.max(), ka, 1 / ka))
    g.save(dst, Q, before=P)
    return before, L.garment(pid, L.sample(dst), mb, axis), {'moved_cm': round(float(np.abs(Q - P).max()) * 100, 1), 'stretch': round(stretch, 3)}


def misses(pid, before, after, how, ln):
    """What keeps a registered garment from passing: off its line without having used the whole cap."""
    bad = []; capped = how['stretch'] > MAX_STRETCH - .002
    if how['stretch'] > MAX_STRETCH + .002: bad.append(f'stretched {how["stretch"]}, cap {MAX_STRETCH}')
    if int(pid) <= 15:
        if abs(after['waistband'] - ln['waistband']) > WAIST_TOL: bad.append(f'waistband at {after["waistband"]}, line {ln["waistband"]}')
    elif not capped:
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
                before, after, how = register(pid, GARMENTS + f'{pid}.glb', os.path.join(tmp, f'{pid}.glb'), mb, axis, B['C' if pid in POSE_C else 'B'])
                bad = misses(pid, before, after, how, ln); fail += bool(bad)
                short = int(pid) > 15 and max(after['hem_front'], after['hem_back']) > ln['top_hem_max'] + HEM_TOL
                print(pid, how, 'hem', after.get('hem'), 'sleeve', after.get('sleeve'), 'stays short of the line (cap reached)' if short and not bad else '', '; '.join(bad) or 'ok')
        sys.exit(1 if fail else 0)
    src, dst = sys.argv[1:3]; pid = piece_id(src)
    before, after, how = register(pid, src, dst, mb, axis, B['C' if pid in POSE_C else 'B'])
    print(pid, 'before', before, 'after', after, how)
