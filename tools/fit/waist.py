"""Clips the body at the waistband line in the shader, instead of hiding whole triangles.

The trousers are narrower than the mannequin at the waist (those of pose C by 4 to 5 cm per side): the body pokes
through the waistband. Hiding the whole triangle leaves the torso edge jagged, with a gap between torso and
waistband, and showing it leaves a white point over it. So each bottom carries in its mask the height of the top
of the waistband around the body (`waist_line`, 72 angles of 5°, angle = atan2(x, z)), and the site discards, per
pixel, the torso (|x| < TORSO) between that line and BAND below it (site/body-occlusion.ts). Whole torso triangles in
that band or above it, up to ABOVE, are no longer hidden by the mask: the shader clips at the line.
usage: python3 tools/fit/waist.py [IDs]   (writes waist_line and shows the band again; run once, on the mask without the clip)"""
import sys, os, json, numpy as np
from garment import Garment
from mask_io import hidden_indices, save
from metric import body
from gen_mask import first
from trimesh.ray.ray_pyembree import RayMeshIntersector
from paths import GARMENTS, MASKS

STEP, TORSO, BAND, ABOVE, SLACK, TIGHT = 5, .17, .10, .10, .003, .06   # degrees, m, m, m, m, m


def angle(P):
    return np.degrees(np.arctan2(P[:, 0], P[:, 2])) % 360


def line(garment, b):
    """Top of the waistband per angle, as the camera sees it: horizontal rays from outside towards the axis; at each
    height, the fabric found up to TIGHT from the body counts (in front of it or just behind, where the body pokes
    through the waistband). The line is the highest such height, median of five rays in the step (a drawstring or
    label sticking up does not pull the line), minus SLACK: a little below, the torso covers the waistband edge, as
    on a person; above, a gap opened."""
    C = b.triangles_center; torso = np.nonzero(np.abs(C[:, 0]) < TORSO)[0]   # the arm at the side blocked the ray
    rg, rb = RayMeshIntersector(garment), RayMeshIntersector(b.submesh([torso], append=True))
    ys = np.arange(.85, 1.15, .002); out = []
    for k in range(360 // STEP):
        tops = []
        for da in np.linspace(-STEP / 2, STEP / 2, 5):
            a = np.radians(k * STEP + da); d = -np.array([np.sin(a), 0, np.cos(a)])
            o = np.c_[-d[0] * np.ones(len(ys)), ys, -d[2] * np.ones(len(ys))]; dd = np.repeat(d[None], len(ys), 0)
            tg, _ = first(rg, o, dd); tb, _ = first(rb, o, dd, front_only=True)
            with np.errstate(invalid='ignore'):
                covers = np.isfinite(tg) & (tg < tb + TIGHT)
            tops.append(ys[covers].max() if covers.any() else np.nan)
        out.append(np.nanmedian(tops) if np.isfinite(tops).any() else np.nan)
    y = np.array(out); ok = np.isfinite(y)
    return np.interp(np.arange(len(y)), np.nonzero(ok)[0], y[ok], period=len(y)) - SLACK


def on_line(P, L):
    t = angle(P) / STEP; i = np.floor(t).astype(int) % len(L); f = t - np.floor(t)
    return L[i] * (1 - f) + L[(i + 1) % len(L)] * f


def clipped(P, L):
    """What the shader discards: torso between the waistband line and BAND below it."""
    y = on_line(P, L)
    return (np.abs(P[:, 0]) < TORSO) & (P[:, 1] < y) & (P[:, 1] > y - BAND)


def band(b, L):
    """Torso triangles the shader handles: every vertex above the bottom of the band and below ABOVE."""
    V = b.vertices; y = on_line(V, L)
    ok = (np.abs(V[:, 0]) < TORSO) & (V[:, 1] > y - BAND + .005) & (V[:, 1] < y + ABOVE)
    return ok[b.faces].all(1)


def cut_from(mask):
    L = mask.get('waist_line')
    return None if L is None else (lambda P: clipped(P, np.array(L)))


if __name__ == '__main__':
    # without IDs: those the body pokes through at the waist (pose C, 002, 004, 007, 008) and skirt 010, with a
    # jagged edge at the back; on the others (001, 003, 005, 009, 015) the clip would open holes (poke_through.py)
    ids = sys.argv[1:] or [
        '002',
        '004',
        '006',
        '007',
        '008',
        '010',
        '011',
        '012',
        '013',
        '014',
    ]
    for pid in ids:
        g = Garment(GARMENTS + f'{pid}.glb').mesh()
        for pose, path in [('B', f'pose-b/{pid}.json'), ('C', f'pose-c/{pid}.json')]:
            if not os.path.exists(MASKS + path): continue
            b = body(pose); mask = json.load(open(MASKS + path)); L = line(g, b)
            hide = np.zeros(len(b.faces), bool); hide[hidden_indices(mask)] = True
            before = hide.sum(); hide &= ~band(b, L)
            mask['waist_line'] = [round(float(v), 4) for v in L]
            save(MASKS + path, mask, np.nonzero(hide)[0])
            print(pid, pose, 'line', round(L.min(), 3), '–', round(L.max(), 3), 'triangles returned', int(before - hide.sum()))
