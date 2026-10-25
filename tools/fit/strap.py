"""Shoulder poking through the strap of the tops.

The mannequin's shoulder is wider and higher than that of the mannequin the pieces were generated on: the shoulder
head pokes through the strap or the shoulder seam, and at 45° it shows as a white sliver in the armhole (tank top
031). The gen_mask.py mask leaves the arm outside the sleeve as it is (a tank top's armhole has no fabric around the
arm), and the shoulder above the sleeve falls in no zone. Here the shoulder (`shoulder`) disappears where the camera
sees it in front of the fabric with the fabric just behind (poke_through_without_holes), without hiding what some
camera would see with no fabric in front.
usage: python3 tools/fit/strap.py [IDs]   (without IDs: the tops; both poses; running again changes nothing)"""
import sys, os, json, numpy as np
from multiprocessing import Pool
from garment import Garment
from mask_io import hidden_indices, save
from metric import body
from gen_mask import poke_through_without_holes
from paths import GARMENTS, MASKS


def shoulder(b):
    C = b.triangles_center
    return (np.abs(C[:, 0]) > .17) & (C[:, 1] > 1.36) & (C[:, 1] < 1.5)


def extra(b, g, hide):
    """Shoulder triangles the camera sees poking through the fabric that can be hidden without opening a hole."""
    return poke_through_without_holes(b, g, hide) & shoulder(b) & ~hide


def install(pid):
    g = Garment(GARMENTS + f'{pid}.glb').mesh(); out = []
    for pose, path in [('B', f'pose-b/{pid}.json'), ('C', f'pose-c/{pid}.json')]:
        if not os.path.exists(MASKS + path): continue
        b = body(pose); mask = json.load(open(MASKS + path))
        hide = np.zeros(len(b.faces), bool); hide[hidden_indices(mask)] = True
        e = extra(b, g, hide)
        if e.any(): save(MASKS + path, mask, np.nonzero(hide | e)[0])
        out.append(f'{pid} {pose} shoulder hidden {int(e.sum())}')
    return out


if __name__ == '__main__':
    ids = sys.argv[1:] or [f'{i:03d}' for i in range(16, 39)]
    with Pool(os.cpu_count()) as pool:
        for lines in pool.map(install, ids): print('\n'.join(lines))
