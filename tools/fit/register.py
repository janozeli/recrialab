"""Registers every garment to the mannequin's landmarks, with the same rule for all 38 (landmarks.py).

A fix per garment does not scale: each one moved a waistband, a hem or a cuff by its own numbers. Here the garment's
landmarks are taken to the mannequin's without changing the garment's own proportions (landmarks.proportions: its
length and its sleeve as fractions of the body, and the sleeve over the length). A move is either a slide of the
whole garment, which keeps every proportion, or a stretch of at most MAX_STRETCH, below what the eye catches in a
print; and the sleeve never changes by more than PROPORTION against the body of the top, so a cropped jacket with
long sleeves stays one. What the caps leave undone stays undone: a cropped top stays cropped, a 3/4 sleeve stays 3/4.
- bottom: the waistband keeps its own drawing (landmarks.waistband_shape: front lower than the back, sides higher
  than both) and is not made straight. The whole garment slides until the lowest point of that drawing is
  WAISTBAND_DROP under the WAISTBAND LINE, itself BELOW_WAIST under the waist (the narrowest cut of the torso): legs
  and skirt keep their length, and the drawing rises from the line instead of opening the belly. The slide stops
  WAISTBAND_LIFT above the line, and a deeper drawing is scaled down to fit. Only what is not that drawing, the wrinkles of the generated cloth, is evened out, stretching from the crotch up
  and up to the cap. waistband() gives that drawing on the line to whoever cuts the garment (shell.py);
- top: the hem should not stay above the waistband line minus OVERLAP, so the top covers the waistband: a shorter
  top is scaled in height from the shoulder down, up to the cap. The sleeve is scaled along the arm by the same
  factor as the body of the top. A long sleeve (LONG_SLEEVE of the arm or more) goes instead toward BELOW_WRIST
  under the wrist: one that passes the line is shortened to it (the hand stays in view), and the body of the top
  gives up the stretch that would take it more than PROPORTION away from its sleeve; one that ends above the line
  is lengthened by at most PROPORTION over the body.
Sleeve or torso is decided by which the cloth is closer to, blended over a centimeter.
usage: python3 tools/fit/register.py IN.glb OUT.glb   (file names carry the piece id, NNN)
       python3 tools/fit/register.py --check          (registers the 38 in memory; fails if a garment lost a proportion or its
                                                       length class, passed a cap, or stayed off its line with cap to spare)
       python3 tools/fit/register.py --table          (the 38, published and registered: lengths, classes and what moved)"""
import sys, os, tempfile, numpy as np
from scipy.spatial import cKDTree
from garment import Garment
from metric import body, POSE_C
from paths import GARMENTS, piece_id
import landmarks as L

BELOW_WAIST = .07      # m: waistband line = waist - this
OVERLAP = .05          # m: a top comes down at least this far below the waistband line
LONG_SLEEVE = L.SLEEVE_CLASSES[-1][0]   # fraction of the arm, shoulder to wrist: a sleeve this long or longer is long
BELOW_WRIST = .02      # m: a long sleeve ends this far below the wrist
MAX_STRETCH = 1.06     # largest stretch in one direction: a print distorted beyond this reads as deformed
PROPORTION = 1.03      # largest change of the sleeve against the body of the top
WAISTBAND_DROP = .01   # m: lowest point of a waistband's drawing under the waistband line
WAISTBAND_LIFT = .025  # m: highest the mean height of a waistband goes above the line to keep its drawing
# --check: how far a registered garment may be from its line, and the error of reading a length (the sleeve end is read in 2 cm slices)
WAIST_TOL, HEM_TOL, SLEEVE_TOL, LENGTH_TOL, SHAPE_TOL = .01, .006, .02, .012, .012


def lines(mb):
    w = round(mb['waist'] - BELOW_WAIST, 3)
    return {'waistband': w, 'top_hem_max': round(w - OVERLAP, 3), 'long_sleeve_end': round(mb['wrist'] - BELOW_WRIST, 3)}


def drawing(shape, mb):
    """The waistband's drawing as it goes on the body: its lowest point WAISTBAND_DROP under the waistband line and the
    rest above it, so no drawing opens the belly under a top that a straight waistband would close. For that the
    waistband's mean height goes up to WAISTBAND_LIFT above the line; a drawing deeper than that is scaled down to it.
    Returns the shape, with its mean height where it goes, and the scale."""
    c, a0, tilt, sides = shape; a = np.linspace(-np.pi, np.pi, 73); deep = -(tilt * np.sin(a) + sides * np.cos(2 * a)).min()
    k = min(1., (WAISTBAND_LIFT + WAISTBAND_DROP) / max(deep, 1e-9))
    return (c, float(lines(mb)['waistband'] - WAISTBAND_DROP + k * deep), tilt * k, sides * k), float(k)


def waistband(path, mb=None):
    """The waistband of the registered bottom at `path`, as a function: points -> height of the waistband at their angle."""
    shape, _ = drawing(L.waistband_shape(L.sample(path)), mb or L.recorded())
    return lambda points: L.waistband_height(np.asarray(points), shape)


def register(pid, src, dst, mb, axis, b):
    """Writes the registered garment to dst; returns its landmarks before and after."""
    g = Garment(src); P = g.vertices(); S = L.sample(src); before = L.garment(pid, S, mb, axis)
    ln = lines(mb); Q = P.copy(); y = P[:, 1]
    if int(pid) <= 15:
        own = L.waistband_shape(S); shape, drawn = drawing(own, mb); c = shape[0]; ang, top = L.sectors(S, c, 16, 98)
        top = np.convolve(np.r_[top[-1], top, top[0]], [.25, .5, .25], mode='valid')
        top = np.interp(np.arctan2(P[:, 2] - c[1], P[:, 0] - c[0]), np.r_[ang[-1] - 2 * np.pi, ang, ang[0] + 2 * np.pi], np.r_[top[-1], top, top[0]])
        base = before.get('crotch') or own[1] - .18
        rise = np.maximum(top - base, .02); level = np.clip(L.waistband_height(P, shape, own[1]) - top, -(MAX_STRETCH - 1) * rise, (MAX_STRETCH - 1) * rise)
        Q[:, 1] = y + (shape[1] - own[1]) + level * np.clip((y - base) / rise, 0, 1)
        stretch = float(1 + np.abs(level / rise).max()); how = {'slide_cm': round(100 * (shape[1] - own[1]), 1), 'level': round(stretch, 3), 'waistband_drawing': round(drawn, 3), 'waistband_at': round(shape[1], 3)}
    else:
        sh, ap = mb['shoulder'], mb['armpit']
        zc = float(np.median(S[np.abs(S[:, 0]) < .10, 2])); f = np.clip((P[:, 2] - zc) / .08, -1, 1) * .5 + .5
        need = lambda hem: np.clip((sh - ln['top_hem_max']) / (sh - hem), 1, MAX_STRETCH)
        kb = float(need(before['hem_front']) + need(before['hem_back'])) / 2; ka = kb; give = 1.; limit = 'cap' if max(need(before['hem_front']), need(before['hem_back'])) >= MAX_STRETCH else None
        if before['sleeve'] is not None and (sh - before['sleeve']) / (sh - mb['wrist']) >= LONG_SLEEVE:
            ka = float(np.clip((sh - ln['long_sleeve_end']) / (sh - before['sleeve']), 1 / MAX_STRETCH, min(kb * PROPORTION, MAX_STRETCH)))
            if kb > ka * PROPORTION: give = (ka * PROPORTION - 1) / (kb - 1); kb = ka * PROPORTION; limit = 'sleeve'
        k = 1 + give * (need(before['hem_front'] * f + before['hem_back'] * (1 - f)) - 1); yt = np.where(y < sh, sh - (sh - y) * k, y)
        V = np.asarray(b.vertices); arm = np.isin(L.limb(V), (1, 2))
        da = cKDTree(V[arm]).query(P)[0]; dt = cKDTree(V[~arm]).query(P)[0]
        w = np.where(y < ap, 1 / (1 + np.exp(-(dt - da) / .01)), 0)
        ya = np.where(y < sh, sh - (sh - y) * ka, y)
        for side in (1, -1):
            ys, c, _ = axis[side]; s = P[:, 0] * side > 0
            for j in (0, 2):
                Q[s, j] += w[s] * (np.interp(ya[s], ys, c[:, j]) - np.interp(y[s], ys, c[:, j]))
        Q[:, 1] = (1 - w) * yt + w * ya
        stretch = float(max(k.max(), ka, 1 / ka)); how = {'body': round(kb, 3), 'sleeve': round(ka, 3), 'limit': limit}
    g.save(dst, Q, before=P)
    after = L.garment(pid, L.sample(dst), mb, axis)
    return before, after, {'moved_cm': round(float(np.abs(Q - P).max()) * 100, 1), 'stretch': round(stretch, 3), **how,
                           'proportions': [L.proportions(pid, x, mb, ln['waistband']) for x in (before, after)]}


def misses(pid, before, after, how, ln):
    """What keeps a registered garment from passing: a proportion or a length class lost, a cap passed, or the garment
    off its line with cap to spare."""
    bad = []; p0, p1 = how['proportions']
    if how['stretch'] > MAX_STRETCH + .002: bad.append(f'stretched {how["stretch"]}, cap {MAX_STRETCH}')
    mb = L.recorded()
    for k, sleeve in (('length', False), ('sleeve', True)):   # a class is lost when no change within the cap explains it
        if k in p0 and k in p1 and p0[k + '_class'] not in {L.length_class(pid, p1[k] * x, mb, ln['waistband'], sleeve) for x in (1 / MAX_STRETCH, 1, MAX_STRETCH)}:
            bad.append(f'{k} was {p0[k + "_class"]}, is {p1[k + "_class"]}')
    if int(pid) <= 15:
        low = after['waistband_mean'] - abs(after['waistband_front_drop']) / 2 - abs(after['waistband_side_rise']) / 2
        if abs(after['waistband_mean'] - how['waistband_at']) > WAIST_TOL: bad.append(f'waistband at {after["waistband_mean"]} on average, should be at {how["waistband_at"]}')
        if low < ln['waistband'] - WAISTBAND_DROP - WAIST_TOL: bad.append(f'waistband goes down to {round(low, 3)}, at most {WAISTBAND_DROP} m under the line {ln["waistband"]}')
        if abs(p1['length_m'] - p0['length_m']) > LENGTH_TOL: bad.append(f'length was {p0["length_m"]} m, is {p1["length_m"]}: a bottom slides whole')
        for k in ('waistband_front_drop', 'waistband_side_rise'):   # between the drawing as published and as it goes on the line
            lo, hi = sorted((before[k], before[k] * how['waistband_drawing']))
            if not lo - SHAPE_TOL <= after[k] <= hi + SHAPE_TOL: bad.append(f'{k} was {before[k]}, is {after[k]}: the waistband keeps its drawing')
        return bad
    if p1['length_m'] > p0['length_m'] * MAX_STRETCH + LENGTH_TOL or p1['length_m'] < p0['length_m'] - LENGTH_TOL:
        bad.append(f'length was {p0["length_m"]} m, is {p1["length_m"]}, cap {MAX_STRETCH}')
    if p0.get('sleeve_m'):
        r = how['sleeve'] / how['body']; slack = SLEEVE_TOL / p0['sleeve_m']
        if not 1 / PROPORTION - .002 < r < PROPORTION + .002: bad.append(f'sleeve changed {round(r, 3)} against the body of the top, at most {PROPORTION}')
        if abs(p1['sleeve_m'] / p0['sleeve_m'] / how['sleeve'] - 1) > slack: bad.append(f'sleeve was {p0["sleeve_m"]} m, is {p1["sleeve_m"]}, scaled {how["sleeve"]}')
        if p0['sleeve_class'] == 'long' and after['sleeve'] < ln['long_sleeve_end'] - SLEEVE_TOL:
            bad.append(f'long sleeve ends at {after["sleeve"]}, past the wrist line {ln["long_sleeve_end"]}')
    if how['limit'] is None:
        for k in ('hem_front', 'hem_back'):
            if after[k] > ln['top_hem_max'] + HEM_TOL: bad.append(f'{k} at {after[k]}, at most {ln["top_hem_max"]}')
    return bad


def check(report):
    """Called by engine.py --check on its report: the same misses, on the garments as the engine registered them."""
    ln = lines(L.recorded())
    return [f'{pid}: {x}' for pid, g in report['garments'].items() for x in misses(pid, g['before'], g['registered'], g, ln)]


def row(pid, before, after, how):
    p0, p1 = how['proportions']; cm = lambda k: f'{100 * p0[k]:5.1f} > {100 * p1[k]:5.1f}' if p0.get(k) else '     -       '
    kind = p0['length_class'] + ('' if int(pid) <= 15 else ' / ' + p0['sleeve_class'])
    what = (f"slide {how['slide_cm']:+.1f} cm, level {how['level']}, drawing x{how['waistband_drawing']}, waistband front drop {100 * before['waistband_front_drop']:+.1f} > {100 * after['waistband_front_drop']:+.1f} cm,"
            f" side rise {100 * before['waistband_side_rise']:+.1f} > {100 * after['waistband_side_rise']:+.1f}, uneven {100 * before['waistband_uneven']:.1f} > {100 * after['waistband_uneven']:.1f}") if int(pid) <= 15 else f"body {how['body']}, sleeve {how['sleeve']}" + (f" ({how['limit']})" if how['limit'] else '')
    return f"{pid}  {kind:24s} length {cm('length_m')}  sleeve {cm('sleeve_m')}  hem {before['hem']:.3f} > {after['hem']:.3f}  {what}"


if __name__ == '__main__':
    B = {p: body(p) for p in 'BC'}; mb = L.recorded(); axis = L.arm_axis(B['B'])
    if '--check' in sys.argv or '--table' in sys.argv:
        fail = 0; ln = lines(mb); print('lines:', ln, ' lengths in cm, published > registered')
        with tempfile.TemporaryDirectory() as tmp:
            for n in range(1, 39):
                pid = f'{n:03d}'
                before, after, how = register(pid, GARMENTS + f'{pid}.glb', os.path.join(tmp, f'{pid}.glb'), mb, axis, B['C' if pid in POSE_C else 'B'])
                bad = misses(pid, before, after, how, ln); fail += bool(bad)
                print(row(pid, before, after, how), ' ', '; '.join(bad) or 'ok')
        sys.exit(1 if fail and '--check' in sys.argv else 0)
    src, dst = sys.argv[1:3]; pid = piece_id(src)
    before, after, how = register(pid, src, dst, mb, axis, B['C' if pid in POSE_C else 'B'])
    print(pid, 'before', before, 'after', after, how)
