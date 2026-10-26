"""Clips the arm at the sleeve hem in the shader, instead of hiding whole triangles.

The mannequin's arm is made of long, thin triangles. Under a wide or slanted short sleeve (022) the mask hides the arm
triangle by triangle up to where the sleeve is far from it: seen from the front or the back, the arm ends in a
jagged stump below the hem, with the background showing between the stump and the sleeve. As at the collar
(collar.py), each top listed here carries in its mask the height of the sleeve hem around each arm (`sleeve_line`,
72 angles of 5° around the arm axis on the right side, then 72 on the left), and the site discards, per pixel, the
arm (beyond |x| = ARM_X, closer than RADIUS to the axis) between that line and BAND above it
(site/body-occlusion.ts). Whole triangles in that band, and below it down to BELOW, are no longer hidden: the shader
clips at the line. The arm axis leans like the mannequin's arm: AXIS_X and AXIS_Z at height AXIS_Y, moving by AXIS_DX
and AXIS_DZ per metre up (mirrored on the left).
usage: python3 tools/fit/sleeve.py [IDs]   (writes sleeve_line and shows the band again; run once, on the mask without the clip)
       python3 tools/fit/sleeve.py --check   (fails where a stored line is off line(): too low shows the background, too high the arm over the sleeve;
                                             and where the slit to the background differs from the recorded SLIT, which only goes down)"""
import sys, os, json, numpy as np, trimesh
from garment import Garment
from mask_io import hidden_indices, save
from metric import body
from gen_mask import first
from trimesh.ray.ray_pyembree import RayMeshIntersector
from paths import GARMENTS, MASKS
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'visual-qa'))
from known_issues import known_issues

STEP, ARM_X, RADIUS, BAND, BELOW, SLACK, FAR, DY = 5, .17, .06, .10, .08, .004, .12, .004   # degrees and meters
AXIS_Y, AXIS_X, AXIS_Z, AXIS_DX, AXIS_DZ = 1.15, .215, -.033, -.07, -.127   # arm axis: point and lean per metre up
LOW, HIGH = .9, 1.45   # the hem is looked for between the wrist and the armpit; no hem found: the line stays at HIGH
SPIKE = 5              # angles in the median that smooths the raised line
POKE = .15             # m: garment this close behind a visible arm point makes it an arm over the sleeve (poke_through.py)
INNER = (200, 350)     # degrees (0 front, 90 outward, 180 back): the side of the arm that faces the torso


def plane(P):
    """Offset from the arm axis at the point's height (x mirrored on the left: outward is +x on both sides)."""
    t = P[:, 1] - AXIS_Y
    return np.c_[np.abs(P[:, 0]) - (AXIS_X + AXIS_DX * t), P[:, 2] - (AXIS_Z + AXIS_DZ * t)]


def angle(P):
    q = plane(P); return np.degrees(np.arctan2(q[:, 0], q[:, 1])) % 360


def cameras():
    """Directions toward the site's orbit cameras: eight around, level and 22° from below and above."""
    out = []
    for el in (-22, 0, 22):
        for az in range(0, 360, 45):
            e, a = np.radians(el), np.radians(az); out.append([np.sin(a) * np.cos(e), np.sin(e), np.cos(a) * np.cos(e)])
    return np.array(out)


def hem(garment, b):
    """Hem height per angle and side, from the sleeve itself: rays from the arm axis outward; at each height the sleeve
    (garment beyond |x| = ARM_X) found outside the arm up to FAR from it, or just inside it (where the arm pokes
    through), counts. The line is the lowest height from which the sleeve covers the next 2 cm, median of five rays
    in the step, plus SLACK (the arm goes a little into the sleeve, so no background shows between them). On the
    inner side (INNER, facing the torso) the shirt's own side hangs beside the arm and would read as sleeve down to
    the wrist; there the line joins the front and the back."""
    C = b.triangles_center; arm = np.nonzero((np.abs(C[:, 0]) > ARM_X) & (C[:, 1] > .6))[0]
    G = garment.triangles_center
    ys = np.arange(LOW, HIGH, .002); out = []
    for s in (1, -1):
        sleeve = garment.submesh([np.nonzero(s * G[:, 0] > ARM_X)[0]], append=True)
        rg = RayMeshIntersector(sleeve)
        rb = RayMeshIntersector(b.submesh([arm[s * C[arm, 0] > 0]], append=True))
        t = ys - AXIS_Y
        axis = np.c_[s * (AXIS_X + AXIS_DX * t), ys, AXIS_Z + AXIS_DZ * t]
        side = []
        for k in range(360 // STEP):
            if INNER[0] < k * STEP < INNER[1]:
                side.append(np.nan); continue
            lows = []
            for da in np.linspace(-STEP / 2, STEP / 2, 5):
                a = np.radians(k * STEP + da); d = np.array([s * np.sin(a), 0, np.cos(a)])
                dd = np.repeat(d[None], len(ys), 0)
                tg, _ = first(rg, axis, dd); tb, _ = first(rb, axis, dd)
                tb = np.where(np.isfinite(tb), tb, 0)
                with np.errstate(invalid='ignore'):
                    covers = np.isfinite(tg) & (tg < tb + FAR)
                run = np.convolve(covers, np.ones(11), 'valid') == 11   # covered over the next 2 cm
                lows.append(ys[np.argmax(run)] if run.any() else np.nan)
            side.append(np.nanmedian(lows) if np.isfinite(lows).any() else HIGH - SLACK)
        y = np.array(side); ok = np.isfinite(y)
        out += list(np.interp(np.arange(len(y)), np.nonzero(ok)[0], y[ok], period=len(y)))
    return np.array(out) + SLACK


def views(garment, b):
    """What the site's cameras (cameras()) see of the arm, per angle and side (rows) and height every DY from LOW
    (columns): rays from the arm axis outward find the arm's surface. covered: the line from every camera through
    the point meets the garment or the rest of the body, so clipping it shows no background. poke: some camera that
    faces the point sees it first, with the garment less than POKE behind it (the arm over the sleeve's cloth)."""
    C = b.triangles_center; ys = np.arange(LOW, HIGH, DY); D = cameras(); covered, poke = [], []
    for s in (1, -1):
        arm = (s * C[:, 0] > ARM_X) & (C[:, 1] > .6)
        am = b.submesh([np.nonzero(arm)[0]], append=True); ra = RayMeshIntersector(am)
        ro = RayMeshIntersector(trimesh.util.concatenate([garment, b.submesh([np.nonzero(~arm)[0]], append=True)]))
        rg = RayMeshIntersector(garment)
        t = ys - AXIS_Y
        axis = np.c_[s * (AXIS_X + AXIS_DX * t), ys, AXIS_Z + AXIS_DZ * t]
        for k in range(360 // STEP):
            a = np.radians(k * STEP); d = np.array([s * np.sin(a), 0, np.cos(a)])
            tb, fb = first(ra, axis, np.repeat(d[None], len(ys), 0))
            ok = np.isfinite(tb); p = (axis + np.where(ok, tb, 0)[:, None] * d)[ok]; n = am.face_normals[fb[ok]]
            cov = np.ones(len(ys), bool); pk = np.zeros(len(ys), bool)
            for c in D:
                cc = np.repeat(c[None], len(p), 0)
                cov[ok] &= ro.intersects_any(p + 2 * c, -cc)
                front, _ = first(ro, p + 2 * c, -cc); behind, _ = first(rg, p - 1e-3 * c, -cc)
                pk[ok] |= (n @ c > 0) & ~(front < 2 - 1e-3) & (behind < POKE)
            covered.append(cov); poke.append(pk)
    return ys, np.array(covered), np.array(poke)


def line(garment, b, seen=None):
    """The hem line (hem()), raised on the side facing the torso (INNER) to where clipping shows no background over
    the whole band (BAND). There the shirt's own side hangs beside the arm and hem() joins the front and the back
    across it: the line fell below where the sleeve covers, and the clip opened a slit to the background between the
    arm and the torso (022, seen from the front). The line is not raised where the arm it would show sits over the
    sleeve's cloth (views() poke: 021, at the back), nor outside INNER; a lift at one or two angles only is dropped
    by the median over SPIKE angles."""
    L = hem(garment, b); ys, cov, poke = seen or views(garment, b); nb = int(round(BAND / DY)); M = L.copy(); n = len(L) // 2
    for k in range(len(L)):
        if not INNER[0] < (k % n) * STEP < INNER[1]: continue
        run = np.convolve(cov[k], np.ones(nb), 'valid') == nb
        if not run.any(): continue
        B = ys[np.argmax(run)] + SLACK
        if B > L[k] and not poke[k, (ys >= L[k] - SLACK) & (ys < B)].any(): M[k] = B
    M = np.concatenate([np.median([np.roll(h, k) for k in range(-(SPIKE // 2), SPIKE // 2 + 1)], 0) for h in (M[:n], M[n:])])
    inner = np.array([INNER[0] < (k % n) * STEP < INNER[1] for k in range(len(L))])
    return np.where(inner, np.maximum(L, M), L)


def slit(L, ys, cov):
    """Cells (angle in INNER, height every DY) inside the clip band of line L that a camera sees against the background:
    arm discarded with nothing behind it, the slit between the arm and the torso."""
    n = len(L) // 2
    return int(sum((~cov[k][(ys >= L[k]) & (ys < L[k] + BAND)]).sum() for k in range(len(L)) if INNER[0] < (k % n) * STEP < INNER[1]))


def on_line(P, L):
    """Line height at each point's angle, from the right or the left half of L."""
    n = len(L) // 2; t = angle(P) / STEP; i = np.floor(t).astype(int) % n; f = t - np.floor(t)
    o = np.where(P[:, 0] > 0, 0, n)
    return L[o + i] * (1 - f) + L[o + (i + 1) % n] * f


def near(P):
    return (np.abs(P[:, 0]) > ARM_X) & (np.linalg.norm(plane(P), axis=1) < RADIUS)


def clipped(P, L):
    """What the shader discards: arm near the axis between the hem line and BAND above it."""
    y = on_line(P, L)
    return near(P) & (P[:, 1] > y) & (P[:, 1] < y + BAND)


def band(b, L):
    """Triangles the shader handles: every vertex near the axis, below the top of the band and above BELOW under
    the line."""
    V = b.vertices; y = on_line(V, L)
    ok = near(V) & (V[:, 1] < y + BAND - .005) & (V[:, 1] > y - BELOW)
    return ok[b.faces].all(1)


def cut_from(mask):
    L = mask.get('sleeve_line')
    return None if L is None else (lambda P: clipped(P, np.array(L)))


def below_from(mask, H):
    """Arm below the clip line and the hem line H (hem()): outside the sleeve, it shows in front of the cloth like
    any arm (not a poke). Taking the lower of the two keeps the arm a raised line shows over the sleeve counted."""
    L = mask.get('sleeve_line')
    return None if L is None else (lambda P: near(P) & (P[:, 1] < on_line(P, np.minimum(np.array(L), H))))


# pieces clipped at the sleeve hem: short sleeves where it closes the gap under the hem without the arm poking
# through the sleeve (poke_through.py)
IDS = [
    '016',
    '017',
    '018',
    '019',
    '020',
    '021',
    '022',
    '024',
    '025',
    '026',
    '029',
    '030',
    '032',
]
# slit cells (slit()) left per piece and pose, where raising the line would show the arm over the sleeve; only goes down,
# and holds only while the known issue sleeve-slit names the piece (tools/known-issues.yaml)
SLIT = {
    '017 B': 18,
    '017 C': 18,
    '018 B': 14,
    '018 C': 14,
    '019 B': 12,
    '019 C': 12,
    '020 B': 20,
    '020 C': 20,
    '021 B': 10,
    '021 C': 10,
    '022 B': 545,
    '022 C': 545,
    '024 B': 45,
    '024 C': 45,
    '026 B': 11,
    '026 C': 11,
    '029 B': 160,
    '029 C': 160,
    '030 B': 12,
    '030 C': 12,
}


def check():
    """Every stored line equal to line() of the garment and body as they are now (CI): below it, the clip cuts arm
    that a camera sees against the background; above it, the arm shows over the sleeve's cloth."""
    bad = []; issue = known_issues().get('sleeve-slit', set())
    for pid in IDS:
        g = Garment(GARMENTS + f'{pid}.glb').mesh()
        for pose, path in [('B', f'pose-b/{pid}.json'), ('C', f'pose-c/{pid}.json')]:
            if not os.path.exists(MASKS + path): continue
            b = body(pose); seen = views(g, b); L = line(g, b, seen); stored = np.array(json.load(open(MASKS + path))['sleeve_line'])
            low = L - stored; s = slit(stored, seen[0], seen[1]); cap = SLIT.get(f'{pid} {pose}', 0) if pid in issue else 0
            print(pid, pose, 'stored line off line() by up to', round(float(np.abs(low).max()) * 100, 1), 'cm, slit', s, 'cells (recorded', cap, ')', flush=True)
            if np.abs(low).max() > DY: bad.append(f'{pid} {pose}')
            if s != cap: bad.append(f'{pid} {pose} slit {s}, recorded {cap} (only goes down: record the new value)' if s < cap else f'{pid} {pose} slit {s} > {cap}')
    if bad: sys.exit('sleeve line off line() (rerun install.py on them) or slit to the background above SLIT: ' + ', '.join(bad))


if __name__ == '__main__' and sys.argv[1:] == ['--check']:
    check()
elif __name__ == '__main__':
    ids = sys.argv[1:] or IDS
    for pid in ids:
        g = Garment(GARMENTS + f'{pid}.glb').mesh()
        for pose, path in [('B', f'pose-b/{pid}.json'), ('C', f'pose-c/{pid}.json')]:
            if not os.path.exists(MASKS + path): continue
            b = body(pose); mask = json.load(open(MASKS + path)); L = line(g, b)
            hide = np.zeros(len(b.faces), bool); hide[hidden_indices(mask)] = True
            before = hide.sum(); hide &= ~band(b, L)
            mask['sleeve_line'] = [round(float(v), 4) for v in L]
            save(MASKS + path, mask, np.nonzero(hide)[0])
            print(pid, pose, 'line', round(L.min(), 3), '–', round(L.max(), 3), 'triangles returned', int(before - hide.sum()))
