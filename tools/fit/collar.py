"""Clips the neck at the collar line in the shader, instead of hiding whole triangles.

The mannequin's neck is thicker and straighter than that of the mannequin the pieces were generated on: the collar
sits tight on it or the neck pokes through. Hiding the whole triangle leaves, in profile, a gap between neck and
collar where the background shows. As at the waist (waist.py), each top carries in its
mask the height of the top of the collar around the neck (`neck_line`, 72 angles of 5° around the neck axis at
x = 0, z = AXIS_Z), and the site discards, per pixel, the body closer than RADIUS to the axis between that line and
BAND below it (site/body-occlusion.ts). Whole triangles in that band or above it, up to ABOVE, are no longer
hidden: the shader clips at the line.
usage: python3 tools/fit/collar.py [IDs]   (writes neck_line and shows the band again; run once, on the mask without the clip)"""
import sys, os, json, numpy as np
from garment import Garment
from mask_io import hidden_indices, save
from metric import body
from gen_mask import first
from trimesh.ray.ray_pyembree import RayMeshIntersector
from paths import GARMENTS, MASKS

STEP, AXIS_Z, RADIUS, BAND, ABOVE, SLACK, TIGHT, FAR = 5, -.008, .075, .08, .15, .003, .03, .06   # degrees and meters


def plane(P):
    return np.c_[P[:, 0], P[:, 2] - AXIS_Z]


def angle(P):
    q = plane(P); return np.degrees(np.arctan2(q[:, 0], q[:, 1])) % 360


def line(garment, b):
    """Top of the collar per angle, as the camera sees it: horizontal rays from outside towards the neck axis; at
    each height, the fabric found in front of the neck up to FAR from it or just behind (up to TIGHT, where the
    neck pokes through the collar) counts. The line is the highest such height, median of five rays in the step,
    minus SLACK."""
    C = b.triangles_center; neck = np.nonzero(np.linalg.norm(plane(C), axis=1) < RADIUS)[0]
    rg, rb = RayMeshIntersector(garment), RayMeshIntersector(b.submesh([neck], append=True))
    ys = np.arange(1.40, 1.66, .002); out = []
    for k in range(360 // STEP):
        tops = []
        for da in np.linspace(-STEP / 2, STEP / 2, 5):
            a = np.radians(k * STEP + da); d = -np.array([np.sin(a), 0, np.cos(a)])
            o = np.c_[-d[0] * np.ones(len(ys)), ys, AXIS_Z - d[2] * np.ones(len(ys))]; dd = np.repeat(d[None], len(ys), 0)
            tg, _ = first(rg, o, dd); tb, _ = first(rb, o, dd, front_only=True)
            with np.errstate(invalid='ignore'):
                covers = np.isfinite(tg) & (tg < tb + TIGHT) & ~(tg < tb - FAR)
            tops.append(ys[covers].max() if covers.any() else np.nan)
        out.append(np.nanmedian(tops) if np.isfinite(tops).any() else np.nan)
    y = np.array(out); ok = np.isfinite(y)
    return np.interp(np.arange(len(y)), np.nonzero(ok)[0], y[ok], period=len(y)) - SLACK


def on_line(P, L):
    t = angle(P) / STEP; i = np.floor(t).astype(int) % len(L); f = t - np.floor(t)
    return L[i] * (1 - f) + L[(i + 1) % len(L)] * f


def clipped(P, L):
    """What the shader discards: body near the neck axis between the collar line and BAND below it."""
    y = on_line(P, L)
    return (np.linalg.norm(plane(P), axis=1) < RADIUS) & (P[:, 1] < y) & (P[:, 1] > y - BAND)


def band(b, L):
    """Triangles the shader handles: every vertex near the axis, above the bottom of the band and below ABOVE."""
    V = b.vertices; y = on_line(V, L)
    ok = (np.linalg.norm(plane(V), axis=1) < RADIUS) & (V[:, 1] > y - BAND + .005) & (V[:, 1] < y + ABOVE)
    return ok[b.faces].all(1)


def cut_from(mask):
    L = mask.get('neck_line')
    return None if L is None else (lambda P: clipped(P, np.array(L)))


# pieces clipped at the collar: those where it closes the gap in profile without opening holes (poke_through.py)
IDS = [
    '016',
    '017',
    '018',
    '020',
    '021',
    '023',
    '024',
    '025',
    '031',
    '033',
    '035',
    '036',
    '037',
    '038',
]

if __name__ == '__main__':
    ids = sys.argv[1:] or IDS
    for pid in ids:
        g = Garment(GARMENTS + f'{pid}.glb').mesh()
        for pose, path in [('B', f'pose-b/{pid}.json'), ('C', f'pose-c/{pid}.json')]:
            if not os.path.exists(MASKS + path): continue
            b = body(pose); mask = json.load(open(MASKS + path)); L = line(g, b)
            hide = np.zeros(len(b.faces), bool); hide[hidden_indices(mask)] = True
            before = hide.sum(); hide &= ~band(b, L)
            mask['neck_line'] = [round(float(v), 4) for v in L]
            save(MASKS + path, mask, np.nonzero(hide)[0])
            print(pid, pose, 'line', round(L.min(), 3), '–', round(L.max(), 3), 'triangles returned', int(before - hide.sum()))
