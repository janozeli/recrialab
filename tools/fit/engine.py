"""The fit engine: one set of rules that rebuilds all 38 garments on the mannequin, instead of a fix per garment.

register.py takes each garment to the mannequin's landmarks; shell.py rebuilds what wears the body as a skin of
the low-poly mannequin (bottoms first: every top stays outside all of them); tube.py rebuilds skirts and hems
below the hip as welded tubes; loose_hood.py keeps hoods and collars. Then it measures the result:
- per garment: body crossing the garment, triangles, and identity.py on the print (tears and distortion);
- over the 345 looks, from 12 cameras, one ray per cm²: bottom showing in front of the top (the bottom is first
  and the top is less than 3 cm behind) and belly in view between the top's hem and the waistband.
Nothing here writes to site/assets: the output goes to WORK.
usage: python3 tools/fit/engine.py WORK            (builds everything and writes WORK/report.json)
       python3 tools/fit/engine.py WORK 016 004    (only these garments; no look measures)"""
import sys, os, json, glob, numpy as np, trimesh
from multiprocessing import Pool
from garment import Garment
from metric import measure, POSE_C
from paths import GARMENTS
import landmarks as L
import register as R
import mannequin, shell, tube, loose_hood, identity

LONG_HEM = .88         # m: a top whose registered hem is below this gets a tube below the seam
HOODS = (
    '030',
    '033',
    '034',
    '035',
    '036',
    '037',
)
SKIRT_RINGS, HEM_RINGS = 4, 3


def pose(pid): return 'C' if pid in POSE_C else 'B'


def one_shell(a):
    work, kind, pid = a; t = {}
    r = shell.generate(kind, pid, f'{work}/reg/{pid}.glb', f'{work}/dense-{pose(pid)}.glb', f'{work}/low-{pose(pid)}.glb', f'{work}/shell', trace=t)
    r['identity'] = identity.measure(t, shell.Piece(f'{work}/reg/{pid}.glb'), shell.Piece(GARMENTS + f'{pid}.glb'))
    return pid, r


def one_tube(a):
    work, pid, rings, env = a
    return pid, tube.build(f'{work}/dense-B.glb', f'{work}/shell/shell-{pid}.glb', f'{work}/reg/{pid}.glb', f'{work}/final/{pid}-shell.glb',
                           f'{work}/final/{pid}-tube.glb', rings, envelope=np.load(env) if env else None)


def one_hood(a):
    work, pid = a
    return pid, loose_hood.build(f'{work}/dense-B.glb', f'{work}/reg/{pid}.glb', f'{work}/final/{pid}-hood.glb')


def parts(work, pid):
    out = []
    for f in sorted(glob.glob(f'{work}/final/{pid}-*.glb')):
        m = trimesh.load(f, process=False).to_geometry(); out.append(trimesh.Trimesh(m.vertices, m.faces, process=False))
    return trimesh.util.concatenate(out)


def depth(m, X, Y, angles):
    out = []
    for a in angles:
        d = np.array([np.sin(a), 0, np.cos(a)]); r = np.array([np.cos(a), 0, -np.sin(a)])
        o = X[:, None] * r + Y[:, None] * [0, 1, 0] + d * 3
        t = np.full(len(o), np.inf); loc, ir, _ = m.ray.intersects_location(o, np.repeat(-d[None], len(o), 0), multiple_hits=False)
        t[ir] = np.linalg.norm(loc - o[ir], axis=1); out.append(t)
    return np.array(out)


def looks(work, ids):
    """Bottom in front of the top and belly in view, in cm², for every bottom with every top."""
    angles = np.arange(12) * np.pi / 6; X, Y = (a.ravel() for a in np.meshgrid(np.arange(-.45, .45, .01), np.arange(.60, 1.20, .01)))
    D = {p: depth(parts(work, p), X, Y, angles) for p in ids}
    low = trimesh.load(f'{work}/low-B.glb', process=False).to_geometry(); lab = L.limb(np.asarray(low.vertices))
    torso = depth(trimesh.Trimesh(low.vertices, low.faces[(lab[low.faces] == 0).all(1)], process=False), X, Y, angles)
    band = (Y > .90) & (Y < 1.05); out = {}
    for b in [p for p in ids if int(p) <= 15]:
        for t in [p for p in ids if int(p) > 15]:
            with np.errstate(invalid='ignore'):
                poke = int(((D[b] < D[t]) & (D[t] - D[b] < .03)).sum())
            belly = int(((torso < np.minimum(D[b], D[t]) - .002) & np.isfinite(torso))[:, band].sum())
            out[f'{b}.{t}'] = [poke, belly]
    return out


def run(work, ids):
    for d in ('reg', 'shell/env', 'final'): os.makedirs(f'{work}/{d}', exist_ok=True)
    for p in 'BC': mannequin.build(p, f'{work}/dense-{p}.glb', f'{work}/low-{p}.glb')
    B = {p: shell.load_body(f'{work}/dense-{p}.glb') for p in 'BC'}; mb = L.recorded(); axis = L.arm_axis(B['B'])
    rep = {'lines': R.lines(mb), 'garments': {}}
    for pid in ids:
        before, after, how = R.register(pid, GARMENTS + f'{pid}.glb', f'{work}/reg/{pid}.glb', mb, axis, B[pose(pid)])
        rep['garments'][pid] = {'before': before, 'registered': after, **how}
    bottoms = [p for p in ids if int(p) <= 15]; tops = [p for p in ids if int(p) > 15]
    with Pool(min(6, os.cpu_count())) as pool:
        for group, kind in ((bottoms, 'bottom'), (tops, 'top')):
            for pid, r in pool.map(one_shell, [(work, kind, p) for p in group]): rep['garments'][pid]['shell'] = r
        skirts = [p for p in bottoms if p in L.SKIRTS]
        for pid, r in pool.map(one_tube, [(work, p, SKIRT_RINGS, None) for p in skirts]): rep['garments'][pid]['tube'] = r
        for p in ids:
            if p not in skirts and not (int(p) > 15 and rep['garments'][p]['registered']['hem'] < LONG_HEM):
                os.replace(f'{work}/shell/shell-{p}.glb', f'{work}/final/{p}-shell.glb')
        # the set of the bottoms as built: long hems pass outside it
        env = np.vstack([np.asarray(trimesh.sample.sample_surface(trimesh.load(f, process=False).to_geometry(), 30000, seed=1)[0])
                         for p in bottoms for f in sorted(glob.glob(f'{work}/final/{p}-*.glb'))] or [np.zeros((0, 3))])
        np.save(f'{work}/envelope.npy', env[(env[:, 1] > .55) & (env[:, 1] < 1.05)])
        long_tops = [p for p in tops if rep['garments'][p]['registered']['hem'] < LONG_HEM]
        for pid, r in pool.map(one_tube, [(work, p, HEM_RINGS, f'{work}/envelope.npy' if bottoms else None) for p in long_tops]): rep['garments'][pid]['tube'] = r
        for pid, r in pool.map(one_hood, [(work, p) for p in tops if p in HOODS]): rep['garments'][pid]['hood'] = r
    low = {p: trimesh.load(f'{work}/low-{p}.glb', process=False).to_geometry() for p in 'BC'}
    for pid in ids:
        m = parts(work, pid); b = low[pose(pid)]
        r, _, _ = measure(m, trimesh.Trimesh(b.vertices, b.faces, process=False), legs=int(pid) <= 15)
        rep['garments'][pid].update(body_crossing_pct=r['penetrates_pct'], triangles=int(len(m.faces)))
    if len(ids) == 38:
        rep['looks'] = looks(work, ids); v = np.array(list(rep['looks'].values()))
        rep['summary'] = {'poke_total_cm2': int(v[:, 0].sum()), 'poke_worst_look_cm2': int(v[:, 0].max()), 'belly_total_cm2': int(v[:, 1].sum()), 'belly_worst_look_cm2': int(v[:, 1].max()),
                          'body_crossing_mean_pct': round(float(np.mean([g['body_crossing_pct'] for g in rep['garments'].values()])), 2),
                          'triangles_max': max(g['triangles'] for g in rep['garments'].values())}
    json.dump(rep, open(f'{work}/report.json', 'w'), indent=1)
    return rep


if __name__ == '__main__':
    work = sys.argv[1]; ids = sys.argv[2:] or [f'{n:03d}' for n in range(1, 39)]
    rep = run(work, ids)
    for pid, g in rep['garments'].items():
        print(pid, f"crossing {g['body_crossing_pct']}%  triangles {g['triangles']}  identity {g['shell']['identity']}")
    if 'summary' in rep: print(json.dumps(rep['summary']))
