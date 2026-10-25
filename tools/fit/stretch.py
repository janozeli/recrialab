"""Print of the bottoms not stretched beyond pant_leg_cloth.MAX against the GLB Tripo delivered, region by region.

Each shape tool (leg_shape.py, pant_leg_cloth.py, displacement_field.py...) refuses what stretches too much, but each
measures in its own way and against its own input. Here the published piece is compared with the one in ORIGINAL, per
region (pant_leg_cloth.regions: the middle between the legs, the cuff and the rest): p99 of the change in edge length
and in area of the faces that changed; and the printed area turned over (up to pant_leg_cloth.MAX_FLIPPED). Per region, because in the p99 of the whole piece a small region that
stretches a lot, like the bridge between the legs, does not show.
Each published vertex finds its own in the original by UV (slivers.py and islands.py remove triangles; separate_legs.py
cuts the bridge into two copies with the same UV). The inner walls of separate_legs.py (UV of a single point, plain
colour) have no print and stay out.
Skirt 009 stays out (EXCLUDED): hem.py shortened it as in the photo and cords.py removed the cords the photo does not have.
usage: python3 tools/fit/stretch.py [IDs]"""
import os, sys, tempfile, numpy as np
from garment import Garment
from pant_leg_cloth import MAX, MAX_FLIPPED, measures, weld, uvs
from paths import GARMENTS
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '../visual-qa'))
from known_issues import FILE as KNOWN_ISSUES, known_issues  # noqa: E402

ORIGINAL = 'tools/fit/reference/originals/tripo'   # pieces as the generator delivered them, slimmed and without crumbs
# piece: (known issue, {region: (edge, area)}) above MAX, held at the recorded baseline while the issue is open
AS_IS = {
    '014': ('waist-014', {'waist': (.106, .35)}),
}
EXCLUDED = {'009'}     # a requested shape change (the photo's hem, without the cords), not stretch
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def match(go, g, P):
    """Index in the original of each published vertex, or -1 (a wall of separate_legs.py). Those left from the original
    come in the same order within the primitive (the UV finds them walking forward only; a repeated UV does not
    confuse it); then come the copies from separate_legs.py's cut, each in the place of the vertex with the same UV and
    the same position. The tube of shin_tube.py (material shin-NNN) has no original."""
    UO, UG = uvs(go), uvs(g); start = np.cumsum([0] + [len(u) for u in UO])
    mats = [g.js['materials'][p.get('material', 0)].get('name', '') for _, _, p in g.parts]
    j, off = [], 0
    for u, mat in zip(UG, mats):
        idx = np.full(len(u), -1)
        if mat.startswith('shin-'):   # the tube of shin_tube.py: no original
            j.append(idx); off += len(u); continue
        # the original's primitive with the most UV in common (shin_tube.py may remove a whole primitive)
        cj = {tuple(x) for x in u}; q = max(range(len(UO)), key=lambda q: sum(tuple(x) in cj for x in UO[q][::7]))
        uo, off_o, k = UO[q], start[q], 0
        for i in range(len(u)):
            while k < len(uo) and not np.array_equal(uo[k], u[i]): k += 1
            if k == len(uo): break
            idx[i] = off_o + k; k += 1
        rest = np.flatnonzero(idx < 0)
        if len(rest):
            done = np.flatnonzero(idx >= 0); key = {}
            for i in done: key.setdefault(tuple(u[i]), []).append(i)
            for i in rest[rest >= len(done)]:
                c = key.get(tuple(u[i]))
                if not c: continue
                d = np.linalg.norm(P[off + np.array(c)] - P[off + i], axis=1)
                if d.min() < 1e-3: idx[i] = idx[c[d.argmin()]]   # a copy from the cut; the wall only has the same UV (the colour)
        j.append(idx); off += len(u)
    return np.concatenate(j)


def measure(pid):
    with tempfile.NamedTemporaryFile(suffix='.glb') as f:
        f.write(open(os.path.join(ROOT, ORIGINAL, f'{pid}.glb'), 'rb').read()); f.flush()
        go = Garment(f.name)
    g = Garment(GARMENTS + f'{pid}.glb')
    Po, P, F = go.vertices(), g.vertices(), g.mesh().faces
    j = match(go, g, P)
    has = (j[F] >= 0).all(1)                       # a printed face that existed in the original
    X, inv, FF = weld(P, F)   # welded by the published position: the two copies from separate_legs.py's cut stay apart
    Xo = X.copy(); k = j >= 0; Xo[inv[k]] = Po[j[k]]   # the wall (no original) welded to the cut keeps the cut's original
    m, flipped = measures(Xo, X, FF, has)
    return m, flipped


if __name__ == '__main__':
    issues = known_issues()
    bad = [f'{pid}: {issue} is not an open known issue naming it in {KNOWN_ISSUES}'
           for pid, (issue, _) in AS_IS.items() if pid not in issues.get(issue, ())]
    for pid in sys.argv[1:] or [f'{i:03d}' for i in range(1, 16) if f'{i:03d}' not in EXCLUDED]:
        m, flipped = measure(pid); ceiling = {**MAX, **AS_IS.get(pid, ('', {}))[1]}
        print(pid + ' ' + ', '.join(f'{k} {100 * e:.1f}% (area {100 * a:.1f}%)' for k, (e, a) in m.items()) + f', flipped {100 * flipped:.2f}%')
        bad += [f'{pid} {k} {100 * m[k][i]:.1f}% > {100 * ceiling[k][i]:.1f}%' for k in MAX for i in (0, 1) if m[k][i] > ceiling[k][i] + 1e-4]
        bad += [f'{pid} flipped {100 * flipped:.2f}% > {100 * MAX_FLIPPED:.1f}%'] * bool(flipped > MAX_FLIPPED)
    if bad: sys.exit('print stretched too much against the original: ' + ', '.join(bad))
