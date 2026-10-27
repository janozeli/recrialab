"""Clips the arm at the sleeve hem in the shader, instead of hiding whole triangles.

The mannequin's arm is made of long, thin triangles. Under a wide or slanted short sleeve (022) the mask hides the arm
triangle by triangle up to where the sleeve is far from it: seen from the front or the back, the arm ends in a
jagged stump below the hem, with the background showing between the stump and the sleeve. As at the collar
(collar.py), each top listed here carries in its mask the height of the sleeve hem around each arm (`sleeve_line`,
72 angles of 5° around the arm axis on the right side, then 72 on the left), and the site discards, per pixel, the
arm (beyond |x| = ARM_X, closer than RADIUS to the axis) between that line and BAND above it, only where the clothes,
drawn first into a depth buffer, are up to POKE behind the arm pixel in that view (site/body-occlusion.ts): the arm
over the sleeve's cloth vanishes, and where nothing is behind (the gap beside the torso) the arm shows, not the
background. Whole triangles in that band, and below it down to BELOW, are no longer hidden: the shader
clips at the line. The arm axis leans like the mannequin's arm: AXIS_X and AXIS_Z at height AXIS_Y, moving by AXIS_DX
and AXIS_DZ per metre up (mirrored on the left).
usage: python3 tools/fit/sleeve.py [IDs]   (writes sleeve_line and shows the band again; run once, on the mask without the clip)
       python3 tools/fit/sleeve.py --check   (fails where a stored line is off hem(): too low clips arm the sleeve does not cover, too high
                                             shows the arm over the sleeve)"""
import sys, os, json, numpy as np
from garment import Garment
from mask_io import hidden_indices, save
from metric import body
from gen_mask import first
from trimesh.ray.ray_pyembree import RayMeshIntersector
from paths import GARMENTS, MASKS

STEP, ARM_X, RADIUS, BAND, BELOW, SLACK, FAR = 5, .17, .06, .10, .08, .004, .12   # degrees and meters
DY = .004               # m: a stored line further than this from hem() fails --check
AXIS_Y, AXIS_X, AXIS_Z, AXIS_DX, AXIS_DZ = 1.15, .215, -.033, -.07, -.127   # arm axis: point and lean per metre up
LOW, HIGH = .9, 1.45    # the hem is looked for between the wrist and the armpit; no hem found: the line stays at HIGH
POKE = .15              # m: garment this close behind a visible arm point makes it an arm over the sleeve (shader: SLEEVE_POKE)
INNER = (200, 350)      # degrees (0 front, 90 outward, 180 back): the side of the arm that faces the torso


def plane(P):
    """Offset from the arm axis at the point's height (x mirrored on the left: outward is +x on both sides)."""
    t = P[:, 1] - AXIS_Y
    return np.c_[np.abs(P[:, 0]) - (AXIS_X + AXIS_DX * t), P[:, 2] - (AXIS_Z + AXIS_DZ * t)]


def angle(P):
    q = plane(P); return np.degrees(np.arctan2(q[:, 0], q[:, 1])) % 360


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


def on_line(P, L):
    """Line height at each point's angle, from the right or the left half of L."""
    n = len(L) // 2; t = angle(P) / STEP; i = np.floor(t).astype(int) % n; f = t - np.floor(t)
    o = np.where(P[:, 0] > 0, 0, n)
    return L[o + i] * (1 - f) + L[o + (i + 1) % n] * f


def near(P):
    return (np.abs(P[:, 0]) > ARM_X) & (np.linalg.norm(plane(P), axis=1) < RADIUS)


def clipped(P, L, h=BAND):
    """What the shader discards: arm near the axis between the hem line and the band (h) above it."""
    y = on_line(P, L)
    return near(P) & (P[:, 1] > y) & (P[:, 1] < y + h)


def band(b, L, h=BAND):
    """Triangles the shader handles: every vertex near the axis, below the top of the band (h above the line) and
    above BELOW under the line."""
    V = b.vertices; y = on_line(V, L)
    ok = near(V) & (V[:, 1] < y + h - .005) & (V[:, 1] > y - BELOW)
    return ok[b.faces].all(1)


def height(pid):
    """Band of the piece: WIDE where the arm is wider than the sleeve up to the armpit, else BAND."""
    return WIDE.get(pid, BAND)


def cut_from(mask, rg):
    """What the shader discards seen along the direction d: arm in the band (clipped()) where the nearest garment
    (rays rg, both faces) along d lies in front of it or up to POKE behind it. The site draws the clothes' depth
    before the body; with no cloth there, the arm stays and shows, never the background."""
    L = mask.get('sleeve_line')
    if L is None: return None
    L = np.array(L); h = mask.get('sleeve_band', BAND)

    def cut(P, d):
        c = clipped(P, L, h); k = np.nonzero(c)[0]
        if len(k):
            t, _ = first(rg, P[k] - 2 * d, np.repeat(d[None], len(k), 0)); c[k[~(t < 2 + POKE)]] = False
        return c
    return cut


def below_from(mask):
    """Arm below the clip line: outside the sleeve, it shows in front of the cloth like any arm (not a poke)."""
    L = mask.get('sleeve_line')
    return None if L is None else (lambda P: near(P) & (P[:, 1] < on_line(P, np.array(L))))


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
# band (m) of the pieces whose sleeve is narrower than the arm at the back up to the armpit (016, from behind: hiding
# that arm by triangles showed the background where it is); the mask carries it as sleeve_band
WIDE = {
    '016': .20,
}


def check():
    """Every stored line equal to hem() of the garment and body as they are now (CI): below it, the band clips arm
    where the sleeve does not cover it; above it, the arm shows over the sleeve's cloth."""
    bad = []
    for pid in IDS:
        g = Garment(GARMENTS + f'{pid}.glb').mesh()
        for pose, path in [('B', f'pose-b/{pid}.json'), ('C', f'pose-c/{pid}.json')]:
            if not os.path.exists(MASKS + path): continue
            b = body(pose); L = hem(g, b); stored = np.array(json.load(open(MASKS + path))['sleeve_line'])
            off = float(np.abs(L - stored).max())
            print(pid, pose, 'stored line off hem() by up to', round(off * 100, 1), 'cm', flush=True)
            if off > DY: bad.append(f'{pid} {pose}')
    if bad: sys.exit('sleeve line off hem() (rerun install.py on them): ' + ', '.join(bad))


if __name__ == '__main__' and sys.argv[1:] == ['--check']:
    check()
elif __name__ == '__main__':
    ids = sys.argv[1:] or IDS
    for pid in ids:
        g = Garment(GARMENTS + f'{pid}.glb').mesh()
        for pose, path in [('B', f'pose-b/{pid}.json'), ('C', f'pose-c/{pid}.json')]:
            if not os.path.exists(MASKS + path): continue
            b = body(pose); mask = json.load(open(MASKS + path)); L = hem(g, b)
            hide = np.zeros(len(b.faces), bool); hide[hidden_indices(mask)] = True
            before = hide.sum(); hide &= ~band(b, L, height(pid))
            mask['sleeve_line'] = [round(float(v), 4) for v in L]
            mask.pop('sleeve_band', None)
            if pid in WIDE: mask['sleeve_band'] = WIDE[pid]
            save(MASKS + path, mask, np.nonzero(hide)[0])
            print(pid, pose, 'line', round(L.min(), 3), '–', round(L.max(), 3), 'triangles returned', int(before - hide.sum()))
