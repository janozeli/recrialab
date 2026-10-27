"""Gap and penetration of the bottoms per body band, held to the baseline (it can only improve).

From each body vertex metric.measure casts a ray along the normal: the gap is the first garment outward, and
penetrates is garment inside the body (more than 3 mm). Below the crotch, a ray that crosses the gap and hits the
trousers' other leg does not count (the version of the measure is stored in penetration.json, with the bands a new version redefines in `redefined`: only those may start above the old baseline). The arm, which hangs beside the thigh, is left out. Per band (waist to ankle) and in total,
the piece cannot penetrate more than in penetration.json (nor in what the mask leaves visible), nor gain gap above
4 cm. Trousers 002 and 006 were dressed by the generator on a mannequin with thinner legs, and 15 to 31%
of their thigh, knee and shin sits inside the neutral body (the mask hides it). Their `goal` is what dressing them
again with the neutral body as collider has to reach; until then the value must stay at or below the baseline.
usage: python3 tools/fit/penetration.py            (checks against penetration.json)
       python3 tools/fit/penetration.py --update   (lowers the baseline where the piece improved; never raises it)"""
import sys, os, json, numpy as np
from multiprocessing import Pool
from metric import body, POSE_C, measure, masked_vertices
from garment import Garment
from gen_mask import ARM_Y
from paths import GARMENTS

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'penetration.json')
PIECES = [f'{i:03d}' for i in range(1, 16)]
BANDS = {'waist': (.98, 1.10), 'hip': (.86, .98), 'thigh': (.62, .86), 'knee': (.45, .62),
         'shin': (.15, .45), 'ankle': (.12, .15)}
INSTEP = .12      # below it is the sneaker, left out of every band: cloth lying on it is shoe.py's, and counted here it
                  # lowered the gap of a hem wrapping the shoe
SLACK = .3    # percentage points of slack for rounding (the measure is deterministic)
MIN_BAND = 5e-3   # a band with less than this covered (50 cm²) does not count
ARM_X = .17       # arm below the elbow, the same cut as gen_mask.zones: the hand reaches down to 0.69 m, beside the thigh


def measure_piece(pid):
    b = body('C' if pid in POSE_C else 'B')
    hid = masked_vertices(pid, b)
    _, s, cov = measure(Garment(GARMENTS + f'{pid}.glb').mesh(), b, hid, legs=True)
    area = np.zeros(len(b.vertices)); np.add.at(area, b.faces.ravel(), np.repeat(b.area_faces / 3, 3))
    V = b.vertices; cov = cov & ~((np.abs(V[:, 0]) > ARM_X) & (V[:, 1] > ARM_Y))   # the arm is not the bottom
    cov &= V[:, 1] >= INSTEP
    y = V[:, 1]; pct = lambda k, a: round(100 * float(area[k].sum() / a), 1)
    def summary(k):
        a = area[k].sum(); pen = k & (s < -.003)
        return {'penetrates': pct(pen, a), 'penetrates_visible': pct(pen & ~hid, a), 'gap_over_4cm': pct(k & (s > .04), a)}
    r = {'total': summary(cov)}
    for name, (lo, hi) in BANDS.items():
        k = cov & (y >= lo) & (y < hi)
        if area[k].sum() >= MIN_BAND: r[name] = summary(k)
    return pid, r


def worse(now, base):
    bad = []
    for pid, bands in now.items():
        for band, m in bands.items():
            for key, v in m.items():
                b = base[pid]['bands'].get(band, {}).get(key, 0)
                if v > b + SLACK: bad.append(f'{pid} {band} {key} {b} → {v}%')
    return bad


if __name__ == '__main__':
    with Pool(os.cpu_count()) as pool: now = dict(pool.map(measure_piece, PIECES))
    base = json.load(open(BASE))
    for pid in PIECES:
        t = now[pid]['total']; d = base['pieces'][pid].get('goal')
        print(pid, 'penetrates', t['penetrates'], '% (visible', t['penetrates_visible'], '%), gap > 4 cm', t['gap_over_4cm'], '%',
              f'| goal: {d["target_penetrates"]}%' if d else '')
    if sys.argv[1:] == ['--update']:
        for pid in PIECES:
            fx = base['pieces'][pid]['bands']
            for band, m in now[pid].items():
                for key, v in m.items(): fx.setdefault(band, {})[key] = min(v, fx.get(band, {}).get(key, v))
        json.dump(base, open(BASE, 'w'), indent=1, ensure_ascii=False); open(BASE, 'a').write('\n')
        sys.exit()
    bad = worse(now, base['pieces'])
    if bad: sys.exit('a bottom got worse against tools/fit/penetration.json: ' + '; '.join(bad))
    print('no bottom got worse')
