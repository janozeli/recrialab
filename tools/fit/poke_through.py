"""Poke-throughs and holes of the body under each garment, as the site camera sees it.

With the same cameras and zones as gen_mask.py, counts the rays where:
- poke: the body, with its mask applied, shows in front of the cloth where it should vanish (torso less than 3 cm
  from the cloth; arm inside a sleeve with cloth behind it). On bottoms, the body in front of cloth that lies right
  behind it (less than 3 cm): the hip or the glutes through the waistband or the seat;
- hole: the first body the ray finds is a hidden triangle with no cloth in front nor right behind (less than 5 cm),
  so the mannequin shows hollow. A hidden body with cloth right behind is a poke that vanished, not a hole.
Hiding more of the body removes pokes and opens holes, so the two are measured together. Where the shader clips the
body at the waistband line (waist.py), the clipped body counts as invisible, and clipped with no cloth up to TIGHT
behind it counts as a hole.

Tops share one limit (--max-pokes, --max-holes). Bottoms share --max-bottom-pokes, except the pieces in BOTTOM_AS_IS,
and their holes are per piece (BOTTOM_HOLES): both are baselines that may only go down.
usage: python3 tools/fit/poke_through.py [--max-pokes N] [--max-holes N] [--max-bottom-pokes N] [IDs]   (no IDs: all 38)"""
import sys, os, json, numpy as np
from multiprocessing import Pool
from trimesh.ray.ray_pyembree import RayMeshIntersector
from metric import body, POSE_C
from garment import Garment
from itertools import chain
from gen_mask import cameras, first, zones, ORBIT
from mask_io import hidden_indices
from waist import cut_from, TIGHT
import collar, strap
from sleeve import cut_from as sleeve_cut, below_from as below_sleeve, hem as sleeve_hem, FAR as SLEEVE_FAR
from paths import GARMENTS, MASKS

# Baselines per piece (the recorded counts; they may only go down).
# Shoulder poking through the strap (strap.py): the rest is seen, from another side, with no cloth in front.
SHOULDER = {
    '016': 7,
    '025': 1,
    '031': 807,
}
# Bottom pokes above --max-bottom-pokes: the pose C pants and 002 and 008 are narrower than the mannequin at the
# waist, and pushing their waistband out stretches the print (stretch.py).
BOTTOM_AS_IS = {
    '002': 91,
    '006': 248,
    '008': 139,
    '011': 304,
    '012': 221,
    '013': 363,
    '014': 285,
}
# Bottom holes: hiding the body that pokes through must not let the background show.
BOTTOM_HOLES = {
    '001': 128,
    '002': 439,
    '003': 1051,
    '004': 564,
    '005': 153,
    '006': 6553,
    '007': 415,
    '008': 721,
    '009': 228,
    '010': 603,
    '011': 1313,
    '012': 202,
    '013': 758,
    '014': 7658,
    '015': 655,
}


def measure_top(pid):
    b = body('B'); F = b.faces
    g = Garment(GARMENTS + f'{pid}.glb').mesh(); rg = RayMeshIntersector(g)
    mask = json.load(open(MASKS + f'pose-b/{pid}.json'))
    clips = [(c, far) for c, far in ((collar.cut_from(mask), collar.FAR), (sleeve_cut(mask), SLEEVE_FAR)) if c]
    cut = (lambda P: np.any([c(P) for c, _ in clips], 0)) if clips else None
    below = below_sleeve(mask, sleeve_hem(g, b)) if 'sleeve_line' in mask else None
    hid = np.zeros(len(F), bool); hid[hidden_indices(mask)] = True
    near, sleeve = zones(b, g, rg)
    vis = np.nonzero(~hid)[0]
    rv, rt = RayMeshIntersector(b.submesh([vis], append=True)), RayMeshIntersector(b)
    shoulder = strap.shoulder(b); pokes = holes = on_shoulder = 0
    for o, dd in cameras():
        tg, _ = first(rg, o, dd)
        tb, fb = first(rv, o, dd, front_only=True, cut=cut)
        with np.errstate(invalid='ignore'):
            m = np.isfinite(tb) & np.isfinite(tg) & (tb < tg)
        f = vis[fb[m]]; gap = tg[m] - tb[m]
        out = below(o[m] + dd[m] * tb[m, None]) if below else np.zeros(m.sum(), bool)   # the arm under a clipped sleeve's hem
        pokes += int((((near[f] & (gap < .03)) | (sleeve[f] & (gap < .15))) & ~out).sum())
        on_shoulder += int((shoulder[f] & (gap < .03)).sum())
        tt, ft = first(rt, o, dd, front_only=True)
        with np.errstate(invalid='ignore'):
            hole = np.isfinite(tt) & ~(tg < tt + .05) & hid[np.maximum(ft, 0)] & (ft >= 0)
            # neck and arm clipped by the shader (collar.py, sleeve.py): a gap if there is no cloth up to FAR behind
            for clip, far in clips:
                k = np.isfinite(tt); c = np.zeros(len(tt), bool); c[k] = clip(o[k] + dd[k] * tt[k, None])
                hole = (hole & ~c) | (c & ~(tg < tt + far))
            holes += int(hole.sum())
    return pid, pokes, holes, on_shoulder


def measure_bottom(pid):
    pose = 'C' if pid in POSE_C else 'B'
    b = body(pose); F = b.faces
    g = Garment(GARMENTS + f'{pid}.glb').mesh(); rg = RayMeshIntersector(g)
    mask = json.load(open(MASKS + ('pose-c/' if pose == 'C' else 'pose-b/') + f'{pid}.json')); cut = cut_from(mask)
    hid = np.zeros(len(F), bool); hid[hidden_indices(mask)] = True
    vis = np.nonzero(~hid)[0]; rv, rt = RayMeshIntersector(b.submesh([vis], append=True)), RayMeshIntersector(b)
    pokes = holes = 0
    # pokes from the hip up (lower, the leg shows through the skirt hem); holes also on the site orbit
    for above, (o, dd) in chain(((True, c) for c in cameras(.008)), ((False, c) for c in cameras(**ORBIT))):
        tg, _ = first(rg, o, dd); tb, _ = first(rv, o, dd, front_only=True, cut=cut)
        tt, ft = first(rt, o, dd, front_only=True)
        with np.errstate(invalid='ignore'):
            if above:
                pokes += int((np.isfinite(tb) & (tb < tg) & (tg - tb < .03)).sum())
            hole = np.isfinite(tt) & ~(tg < tt + .05) & hid[np.maximum(ft, 0)] & (ft >= 0)
            if cut is not None:   # clipped by the shader: the cloth right behind (up to TIGHT, like the waistband line) covers it
                k = np.isfinite(tt); c = np.zeros(len(tt), bool); c[k] = cut(o[k] + dd[k] * tt[k, None])
                hole = (hole & ~c) | (c & ~(tg < tt + TIGHT))
            holes += int(hole.sum())
    return pid, pokes, holes


if __name__ == '__main__':
    args = sys.argv[1:]; lim = {}
    while args[:1] and args[0].startswith('--max-'):
        lim[args[0][6:]] = int(args[1]); args = args[2:]
    ids = args or [f'{i:03d}' for i in range(1, 39)]
    bottoms = [i for i in ids if int(i) < 16]; tops = [i for i in ids if int(i) >= 16]
    with Pool(os.cpu_count()) as pool:
        res = pool.map(measure_top, tops); rb = pool.map(measure_bottom, bottoms)
    for pid, p, h, o in res: print(pid, 'pokes', p, 'holes', h, 'shoulder through the strap', o)
    print('total pokes', sum(r[1] for r in res), 'holes', sum(r[2] for r in res))
    bad = [f'{pid} pokes {p}' for pid, p, _, _ in res if p > lim.get('pokes', 1e9)] + \
          [f'{pid} holes {h}' for pid, _, h, _ in res if h > lim.get('holes', 1e9)] + \
          [f'{pid} shoulder {o}' for pid, _, _, o in res if o > SHOULDER.get(pid, 0)]
    for pid, p, h in rb: print(pid, 'pokes (body through the bottom garment)', p, 'holes', h)
    bad += [f'{pid} pokes {p}' for pid, p, _ in rb if p > BOTTOM_AS_IS.get(pid, lim.get('bottom-pokes', 1e9))] + \
           [f'{pid} holes {h}' for pid, _, h in rb if h > BOTTOM_HOLES.get(pid, 0)]
    if bad: sys.exit('above the limit: ' + ', '.join(bad))
