"""Junction of the top and the bottom garment, as the site camera sees it (same cameras as gen_mask.py).

For each bottom × top pair, with the published layer table, counts the rays where:
- hole: the first cloth the ray finds is a bottom triangle hidden by the table, above the top's hem (below it the
  site draws the triangle back, clipped: top_hem.py, raised where every layer of the top stands off the bottom), with
  no top in front nor right behind (< 5 cm): there the pants vanish in a jagged line below the hem;
- poke: the bottom garment, visible, shows in front of the top with the top right behind (< POKE), found from the
  outside: the waist poking through the blouse. With the top farther behind the pants are only in front of it (the
  arm hanging beside the hip, the hem seen from the side), not poking through. A waist poking deep through (the top more than 3 cm behind) does not count here; on the site
  orbit the junction measure of tools/visual-qa/measure.py catches it. Found from the inside, the camera is inside
  the top (from below, through the hem) and the bottom there is in view, not poking through.
Where the bottom's material is single-sided the site does not draw its back faces, and neither does the measure
(Garment.single_sided, as in gen_layers.py): a ray that meets such a bottom from the inside sees through it.
The cameras differ from the generator's (gen_layers.WINDOW): angles shifted 10°, from below up to above, from the
lowest hem to the chest; so the measure does not check the generator with its own rays.
Per garment, its pokes and holes summed over all its pairs (a bottom with the 23 tops, a top over the 15 bottoms) may
not rise above BASELINE: the hip of trousers 014 standing outside the tops' hems went from 2,086 pokes over its 23 pairs
to 8,859 and no pair crossed the per-pair limit (calibration case hip-014). The sum is checked only for garments whose
pairs are all in the run, with SLACK on top: the same code and packages count up to 3.3% more pokes on the CI runner
than on a cloud session (030 over its 15 pairs: 2,154 against 2,083; holes match), so the baseline is the larger of the
two and SLACK absorbs the rest. --update lowers it where a garment improved and never raises it.
usage: python3 tools/fit/layer_check.py [--max-pokes N] [--max-holes N] [--max-total-pokes N] [--max-total-holes N] [--no-cache] [--update] [BOTTOM.TOP ...]
       (no pairs: 15 × 23; the total catches holes traded for pokes spread over many pairs)"""
import sys, os, json, numpy as np
from multiprocessing import Pool
from trimesh.ray.ray_pyembree import RayMeshIntersector
from garment import Garment
from gen_mask import cameras, first, ORBIT
import top_hem
from paths import GARMENTS, LAYERS

POKE = .03   # m, the same as poke_through.py
# poke caps with POKE, per pair and over the 345 pairs: they hold even when the command line passes a looser limit
CEILING = {'pokes': 1500, 'total-pokes': 90000}
BASELINE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'layer_baseline.json')
SLACK = .05   # fraction over the baseline, ray casting differing between machines (see above)
BOTTOMS, TOPS = [f'{i:03d}' for i in range(1, 16)], [f'{i:03d}' for i in range(16, 39)]


def hidden(bid, tid):
    return np.concatenate([np.arange(a, b + 1) for a, b in ranges(bid, tid)] or [np.zeros(0, int)])


def ranges(bid, tid):
    t = json.load(open(LAYERS + f'{bid}.json')); off = 0; out = []
    for m, r in zip(t['meshes'], t['pairs'].get(tid, [])):
        out += [(a + off, b + off) for a, b in r]; off += m['triangles']
    return out


CAMERAS = ORBIT


def measure(pair, hid=None):
    bid, tid = pair.split('.')
    bg = Garment(GARMENTS + f'{bid}.glb'); bm = bg.mesh(); single = bg.single_sided(); tm = Garment(GARMENTS + f'{tid}.glb').mesh()
    h = np.zeros(len(bm.faces), bool); h[hidden(bid, tid) if hid is None else hid] = True
    hem = top_hem.line(tm.vertices); rad = top_hem.radius(tm.vertices, hem)
    rt, rb = RayMeshIntersector(tm), RayMeshIntersector(bm)
    vis = np.nonzero(~h)[0]; rv = RayMeshIntersector(bm.submesh([vis], append=True)) if len(vis) else None
    pokes = holes = 0
    for o, d in cameras(**CAMERAS):
        tg, fg = first(rt, o, d)
        tb, fb = first(rb, o, d, front_only=single)
        outside = np.zeros(len(o), bool); ok = fg >= 0
        outside[ok] = np.einsum('ij,ij->i', tm.face_normals[fg[ok]], d[ok]) < 0
        with np.errstate(invalid='ignore'):
            hid_hit = np.isfinite(tb) & h[np.maximum(fb, 0)]
            # hidden below the top's hem: the site draws it (garment-hem.ts)
            p = o[hid_hit] + d[hid_hit] * tb[hid_hit, None]; back = np.zeros(len(o), bool); back[hid_hit] = p[:, 1] < top_hem.height(hem, p, rad)
            holes += int((hid_hit & ~back & ~(tg < tb + .05)).sum())
            poke = lambda t: np.isfinite(t) & (t < tg) & (tg - t < POKE) & outside
            if rv is not None:
                tv, _ = first(rv, o, d, front_only=single[vis])
                pokes += int((poke(tv) | (back & poke(tb))).sum())
            else:
                pokes += int((back & poke(tb)).sum())
    return pair, pokes, holes


# Each pair's result is kept by the hash of everything it reads (both GLBs, the pair's line in the table and all the
# code in tools/fit with requirements.txt): a change to one garment only redoes its pairs (about 20 s instead of 5 min
# for all 345). The cache is content-addressed, so it can be shared between runs without stale values.
HERE = os.path.dirname(os.path.abspath(__file__))
CODE = sorted(f for f in os.listdir(HERE) if f.endswith('.py') or f == 'requirements.txt')
CACHE = os.environ.get('LAYER_CHECK_CACHE') or os.path.expanduser('~/.cache/recrialab/layer-check')


def key(pair):
    import hashlib
    bid, tid = pair.split('.'); h = hashlib.sha256()
    for f in [GARMENTS + f'{bid}.glb', GARMENTS + f'{tid}.glb'] + [os.path.join(HERE, c) for c in CODE]:
        h.update(open(f, 'rb').read())
    h.update(json.dumps(ranges(bid, tid)).encode())
    return h.hexdigest()


def measure_cached(pair):
    k = key(pair); f = os.path.join(CACHE, k + '.json')
    try: return tuple(json.load(open(f)))
    except (OSError, ValueError): pass
    r = measure(pair)
    try:
        os.makedirs(CACHE, exist_ok=True); tmp = f'{f}.{os.getpid()}'
        json.dump(list(r), open(tmp, 'w')); os.replace(tmp, f)
    except OSError: pass
    return r


if __name__ == '__main__':
    args = sys.argv[1:]; lim = {}
    while args[:1] and args[0].startswith('--max-'):
        lim[args[0][6:]] = int(args[1]); args = args[2:]
    for k, v in CEILING.items(): lim[k] = min(lim.get(k, v), v)
    args = [a for a in args if a not in ('--no-cache', '--update')]
    pairs = args or [f'{b}.{t}' for b in BOTTOMS for t in TOPS]
    with Pool(os.cpu_count()) as pool:
        res = pool.map(measure if '--no-cache' in sys.argv else measure_cached, pairs)
    for pair, p, h in res: print(pair, 'pokes', p, 'holes', h)
    print('total pokes', sum(r[1] for r in res), 'holes', sum(r[2] for r in res))
    bad = [f'{pair} pokes {p}' for pair, p, _ in res if p > lim.get('pokes', 1e9)] + \
          [f'{pair} holes {h}' for pair, _, h in res if h > lim.get('holes', 1e9)]
    tp, tb = sum(r[1] for r in res), sum(r[2] for r in res)
    bad += [f'total pokes {tp}'] * (tp > lim.get('total-pokes', 1e12)) + [f'total holes {tb}'] * (tb > lim.get('total-holes', 1e12))
    run = {pair: (p, h) for pair, p, h in res}
    own = {g: [f'{g}.{t}' for t in TOPS] for g in BOTTOMS} | {g: [f'{b}.{g}' for b in BOTTOMS] for g in TOPS}
    base = json.load(open(BASELINE))
    for g, ps in own.items():
        if not all(q in run for q in ps): continue
        now = {'pokes': sum(run[q][0] for q in ps), 'holes': sum(run[q][1] for q in ps)}
        if '--update' in sys.argv: base[g] = {k: min(v, base[g][k]) for k, v in now.items()}
        bad += [f'{g} {k} over its pairs {now[k]} > {base[g][k]} + {SLACK:.0%}' for k in now if now[k] > base[g][k] * (1 + SLACK)]
    if '--update' in sys.argv: open(BASELINE, 'w').write(json.dumps(base, indent=1) + '\n')
    if bad: sys.exit('above the limit: ' + ', '.join(bad))
