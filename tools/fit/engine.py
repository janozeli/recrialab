"""The fit engine: one set of rules that rebuilds all 38 garments on the mannequin, instead of a fix per garment.

register.py takes each garment to the mannequin's landmarks; shell.py rebuilds what wears the body as a skin of
the low-poly mannequin (bottoms first: every top stays outside all of them); tube.py rebuilds skirts and hems
below the hip as welded tubes; loose_hood.py keeps hoods and collars. Then it measures the result:
- per garment: body crossing the garment, triangles, and identity.py on the print (tears and distortion);
- over the 345 looks, from 12 cameras, one ray per cm²: bottom showing in front of the top (the bottom is first
  and the top is less than 3 cm behind) and belly in view between the top's hem and the waistband.
Nothing here writes to site/assets: the output goes to WORK.
engine.json holds the baseline: per garment, the values recorded for it, which may only go down; and limits over
the 345 looks. A module of the engine that defines check(report) is called too and adds its own failures, so a new
rule brings its check without another CI step.
usage: python3 tools/fit/engine.py WORK            (builds everything and writes WORK/report.json)
       python3 tools/fit/engine.py WORK 016 004    (only these garments; no look measures)
       python3 tools/fit/engine.py WORK --check    (fails where a garment is worse than its baseline or a look limit is passed)
       python3 tools/fit/engine.py WORK --write    (records the baseline; values may only go down against the recorded ones)"""
import sys, os, json, glob, numpy as np, trimesh
from multiprocessing import Pool
from garment import Garment
from metric import measure, POSE_C
from paths import GARMENTS
import landmarks as L
import register as R
import mannequin, shell, tube, loose_hood, identity, looks

BASELINE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'engine.json')
# per-garment baseline: value read from the report and the slack a rerun may show over the recorded value
KEPT = {
    'body_crossing_pct': (lambda g: g['body_crossing_pct'], .2),
    'triangles': (lambda g: g['triangles'], 0),
    'tear_cm': (lambda g: g['shell']['identity']['tear_cm'], 15),
    'tear_back_cm': (lambda g: g['shell']['identity']['tear_back_cm'], 10),
    'distortion_pct': (lambda g: round(100 * abs(g['shell']['identity']['distortion'] - 1), 1), .5),
}
# over the 345 looks, in cm²
LOOK_LIMITS = {
    'poke_total_cm2': 600,
    'poke_worst_look_cm2': 40,
    'belly_total_cm2': 150,
    'belly_worst_look_cm2': 20,
}
MODULES = (
    'register',
    'shell',
    'tube',
    'loose_hood',
    'identity',
    'looks',
    'mannequin',
)
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
        b = trimesh.load(f'{work}/low-B.glb', process=False).to_geometry()
        rep['looks'] = looks.measure({p: parts(work, p) for p in ids}, b); v = np.array(list(rep['looks'].values()))
        rep['summary'] = {'poke_total_cm2': int(v[:, 0].sum()), 'poke_worst_look_cm2': int(v[:, 0].max()), 'belly_total_cm2': int(v[:, 1].sum()), 'belly_worst_look_cm2': int(v[:, 1].max()),
                          'body_crossing_mean_pct': round(float(np.mean([g['body_crossing_pct'] for g in rep['garments'].values()])), 2),
                          'triangles_max': max(g['triangles'] for g in rep['garments'].values())}
    json.dump(rep, open(f'{work}/report.json', 'w'), indent=1)
    return rep


def baseline(rep):
    return {pid: {k: f(g) for k, (f, _) in KEPT.items()} for pid, g in rep['garments'].items()}


def write(rep):
    """One garment per line, so changes to different garments do not conflict."""
    new = baseline(rep)
    if os.path.exists(BASELINE):
        old = json.load(open(BASELINE))
        up = [f'{p} {k}: {old[p][k]} -> {v}' for p, g in new.items() for k, v in g.items() if p in old and v > old[p][k] + KEPT[k][1]]
        if up: raise SystemExit('a baseline only goes down:\n' + '\n'.join(up))
    open(BASELINE, 'w').write('{\n' + ',\n'.join(f' "{p}": {json.dumps(g)}' for p, g in sorted(new.items())) + '\n}\n')


def check(rep):
    old = json.load(open(BASELINE)); bad = []
    for pid, g in baseline(rep).items():
        bad += [f'{pid} {k}: {v}, recorded {old[pid][k]}' for k, v in g.items() if v > old[pid][k] + KEPT[k][1]]
    bad += [f'{k}: {rep["summary"][k]}, limit {lim}' for k, lim in LOOK_LIMITS.items() if rep['summary'][k] > lim]
    for name in MODULES:
        m = __import__(name)
        if hasattr(m, 'check'): bad += [f'{name}: {x}' for x in m.check(rep)]
    return bad


if __name__ == '__main__':
    flags = [a for a in sys.argv[2:] if a.startswith('--')]
    work = sys.argv[1]; ids = [a for a in sys.argv[2:] if not a.startswith('--')] or [f'{n:03d}' for n in range(1, 39)]
    rep = run(work, ids)
    for pid, g in rep['garments'].items():
        print(pid, f"crossing {g['body_crossing_pct']}%  triangles {g['triangles']}  identity {g['shell']['identity']}")
    if 'summary' in rep: print(json.dumps(rep['summary']))
    if '--write' in flags: write(rep)
    if '--check' in flags:
        bad = check(rep); print('\n'.join(bad) or 'ok'); sys.exit(1 if bad else 0)
