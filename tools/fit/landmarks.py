"""Deterministic landmarks of the mannequin and of each garment, read from geometry alone (heights in meters).

Every fit rule so far carries its own numbers for where the waist, the wrist or the hem is. This reads them once:
- mannequin, from horizontal cuts of the body every centimeter: crotch (highest cut where the legs are still two
  loops), armpit (highest cut where the arm is still a loop apart from the torso), hip, waist and chest (largest,
  smallest and largest torso perimeter between them), neck, shoulder, wrist (smallest arm perimeter above the hand),
  elbow, ankle and knee;
- bottom: waistband (top of the cloth around the body, and how uneven it is), crotch of the garment (highest cloth
  in the middle of the body, away from front and back) and hem;
- top: collar, hem at the middle of the front and of the back, and sleeve end (walking down the arm from the armpit,
  the last slice with cloth on the outer side of the arm axis; None on a sleeveless top).
The mannequin's landmarks are recorded in landmarks.json with the hash of the body they were read from.
usage: python3 tools/fit/landmarks.py            (prints the landmarks of the body and of the 38 garments)
       python3 tools/fit/landmarks.py --write    (records the mannequin's landmarks)
       python3 tools/fit/landmarks.py --check    (fails if the body changed or its landmarks moved from the recorded ones)"""
import sys, os, json, hashlib, numpy as np, trimesh
from garment import Garment
from metric import body, POSE_C
from paths import GARMENTS, BODY

STEP = .01             # m between body cuts
SKIRTS = (
    '009',
    '010',
)
RECORD = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'landmarks.json')
ARM_X, ARM_TOP, LEG_TOP = .165, 1.30, .80   # m: arm beyond this |x| below this height (hand included); legs below this


def limb(v):
    """Label per point in the rest poses: 1/2 arm (+x/-x), 3/4 leg, 0 torso."""
    r = np.zeros(len(v), int)
    arm = (np.abs(v[:, 0]) > ARM_X) & (v[:, 1] < ARM_TOP)
    r[arm & (v[:, 0] > 0)] = 1; r[arm & (v[:, 0] < 0)] = 2
    leg = (v[:, 1] < LEG_TOP) & ~arm
    r[leg & (v[:, 0] > 0)] = 3; r[leg & (v[:, 0] < 0)] = 4
    return r


def loops(b, y):
    """Closed cuts of the body at height y: list of (center x, perimeter, width in x)."""
    sec = b.section(plane_origin=[0, y, 0], plane_normal=[0, 1, 0])
    out = []
    for d in (sec.discrete if sec is not None else []):
        p = d[:, [0, 2]]; per = float(np.linalg.norm(np.diff(p, axis=0), axis=1).sum())
        if per > .08: out.append((float(p[:, 0].mean()), per, float(np.ptp(p[:, 0]))))
    return out


def mannequin(b):
    v = np.asarray(b.vertices); ys = np.arange(.03, v[:, 1].max(), STEP); L = [loops(b, y) for y in ys]
    m = {}
    def two_legs(l):
        c = [x for x in l if abs(x[0]) < .14]
        return len(c) >= 2 and min(x[0] for x in c) < 0 < max(x[0] for x in c)
    ig = max(i for i, l in enumerate(L) if two_legs(l) and ys[i] < 1.1); m['crotch'] = float(ys[ig] + STEP)
    ia = max(i for i, l in enumerate(L) if len(l) >= 3 and i > ig); m['armpit'] = float(ys[ia] + STEP)
    torso = {i: max(L[i], key=lambda x: x[1]) for i in range(ig + 1, ia + 1)}
    pick = lambda i0, i1, f: f(range(i0, i1), key=lambda i: torso[i][1])
    ih = pick(ig + 1, min(ig + 23, ia), max); m['hip'] = float(ys[ih])
    iw = pick(ih + 1, ia - 8, min); m['waist'] = float(ys[iw])
    m['chest'] = float(ys[pick(iw + 1, ia + 1, max)])
    top = [i for i in range(ia + 1, len(ys)) if L[i]]
    width = {i: max(x[2] for x in L[i]) for i in top}
    ineck = min((i for i in top if ys[i] < m['armpit'] + .22), key=lambda i: width[i]); m['neck'] = float(ys[ineck])
    half = (width[top[0]] + width[ineck]) / 2
    m['shoulder'] = float(ys[max(i for i in top if i <= ineck and width[i] > half)])
    arm = {i: [x for x in L[i] if x[0] > .14 and x[0] - x[2] / 2 > .08] for i in range(ia)}; arm = {i: x[0] for i, x in arm.items() if x}
    i0 = min(arm); m['hand'] = float(ys[i0])
    m['wrist'] = float(ys[min((i for i in arm if ys[i0] + .08 < ys[i] < ys[i0] + .30), key=lambda i: arm[i][1])])
    m['elbow'] = (m['wrist'] + m['shoulder']) / 2
    leg = {i: [x for x in L[i] if 0 < x[0] < .14] for i in range(ig)}
    m['ankle'] = float(ys[min((i for i in leg if leg[i] and .05 < ys[i] < .30), key=lambda i: leg[i][0][1])])
    m['knee'] = (m['crotch'] + m['ankle']) / 2
    return {k: round(x, 3) for k, x in m.items()}


def arm_axis(b):
    """Per side (+1/-1): heights, centers and mean radius of the arm in 2 cm slices."""
    v = np.asarray(b.vertices); lab = limb(v); out = {}
    for side, m in ((1, 1), (-1, 2)):
        s = lab == m; k = np.floor(v[s, 1] / .02).astype(int); ks = np.unique(k)
        c = np.array([v[s][k == j].mean(0) for j in ks])
        r = np.array([np.hypot(v[s][k == j][:, 0] - cc[0], v[s][k == j][:, 2] - cc[2]).mean() for j, cc in zip(ks, c)])
        out[side] = (ks * .02 + .01, c, r)
    return out


def sample(path, n=150000):
    return np.asarray(trimesh.sample.sample_surface(Garment(path).mesh(), n, seed=1)[0])


def sectors(P, center, k, q):
    """Percentile q of the height of P in each of k sectors around the vertical axis through center."""
    a = np.arctan2(P[:, 2] - center[1], P[:, 0] - center[0]); ang = -np.pi + (np.arange(k) + .5) * 2 * np.pi / k
    out = np.full(k, np.nan)
    for i, t in enumerate(ang):
        s = np.abs((a - t + np.pi) % (2 * np.pi) - np.pi) < np.pi / k
        if s.sum() > 20: out[i] = np.percentile(P[s, 1], q)
    ok = ~np.isnan(out)
    return ang, np.interp(np.arange(k), np.flatnonzero(ok), out[ok], period=k)


def waist_center(P):
    return P[P[:, 1] > np.percentile(P[:, 1], 80)][:, [0, 2]].mean(0)


def garment(pid, P, mb, axis):
    """Landmarks of a dressed garment from points P sampled on its surface."""
    r = {}
    if int(pid) <= 15:
        _, top = sectors(P, waist_center(P), 16, 98)
        r['waistband'] = float(np.median(top)); r['waistband_uneven'] = float(np.ptp(top))
        r['hem'] = float(np.mean([np.percentile(P[P[:, 0] * side > .02, 1], 2) for side in (1, -1)]))
        if pid not in SKIRTS:
            r['crotch'] = None
            for y in np.arange(r['waistband'] - .03, r['hem'], -STEP):
                f = P[np.abs(P[:, 1] - y) < STEP]; c = f[np.abs(f[:, 0]) < .012]
                if len(f) < 20: continue
                z0, z1 = np.percentile(f[:, 2], [2, 98])
                if ((c[:, 2] > z0 + .35 * (z1 - z0)) & (c[:, 2] < z1 - .35 * (z1 - z0))).sum() >= 6: r['crotch'] = float(y); break
    else:
        r['collar'] = float(np.percentile(P[:, 1], 99.5))
        mid = P[np.abs(P[:, 0]) < .10]
        r['hem_front'] = float(np.percentile(mid[mid[:, 2] > 0, 1], 2)); r['hem_back'] = float(np.percentile(mid[mid[:, 2] <= 0, 1], 2))
        r['hem'] = (r['hem_front'] + r['hem_back']) / 2
        ends = []
        for side in (1, -1):
            ys, c, rad = axis[side]; end = None
            for y, cc, ra in sorted(zip(ys, c, rad), key=lambda t: -t[0]):
                if y > mb['armpit'] - .02: continue
                s = (np.abs(P[:, 1] - y) < .011) & (P[:, 0] * side > cc[0] * side + .3 * ra) & (np.hypot(P[:, 0] - cc[0], P[:, 2] - cc[2]) < ra + .10)
                if s.sum() < 40: break
                end = y
            ends.append(end)
        r['sleeve'] = float(np.mean(ends)) if None not in ends else None
    return {k: (round(x, 3) if isinstance(x, float) else x) for k, x in r.items()}


def body_hash():
    return hashlib.sha256(open(BODY + 'pose-b.glb', 'rb').read()).hexdigest()


def recorded():
    return json.load(open(RECORD))['mannequin']


if __name__ == '__main__':
    mb = mannequin(body('B'))
    if '--write' in sys.argv:
        json.dump({'body': body_hash(), 'mannequin': mb}, open(RECORD, 'w'), indent=1); open(RECORD, 'a').write('\n'); sys.exit()
    if '--check' in sys.argv:
        rec = json.load(open(RECORD)); bad = []
        if rec['body'] != body_hash(): bad.append('pose-b.glb changed: read the landmarks again (--write) and run register.py --check')
        bad += [f'{k}: recorded {rec["mannequin"].get(k)}, read {x}' for k, x in mb.items() if rec['mannequin'].get(k) != x]
        mc = mannequin(body('C'))
        bad += [f'{k}: pose C reads {mc[k]}, pose B {mb[k]}' for k in ('waist', 'armpit', 'wrist') if abs(mc[k] - mb[k]) > .011]
        print('mannequin landmarks:', mb); print('\n'.join(bad) or 'ok'); sys.exit(1 if bad else 0)
    print('mannequin', mb); axis = arm_axis(body('B'))
    for n in range(1, 39):
        pid = f'{n:03d}'; print(pid, garment(pid, sample(GARMENTS + f'{pid}.glb'), mb, axis))
