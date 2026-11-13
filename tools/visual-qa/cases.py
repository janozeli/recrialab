"""Saved pictures that hold a measure of measure.py to what it was written for.

  python3 tools/visual-qa/cases.py

edge-on: tops from the fit engine seen from below in profile. The shell is single-sided, so the inner face of the far
wall is not drawn, and the wall's lower edge shows as a strip under the nearer hem, 10 to 18 px away from the rest.
`loose` read it as a piece in the air (1.4 to 2.2 cm², limit 1.0). The depth pass, which draws both faces, has cloth
all the way between them. It has to read 0 here; with that cloth taken out of the depth (the strips alone in the air)
they have to count again; and a thread planted in the air, 2 px by 30 px, has to count at any angle to the picture.
"""
import glob, os, sys
import numpy as np
import measure as M

HERE = os.path.dirname(os.path.abspath(__file__))


def loose(c, depth):
    return sum(M.loose_area(c, np.isin(c, k), depth) for k in ((M.TOP, M.TOP_BACK), (M.BOTTOM, M.BOTTOM_BACK))) * M.CM2


def thread(c, depth, degrees, width=2, length=30):
    """The view with a thread of the top planted alone in the background, running away from the camera at that angle."""
    free = np.argwhere(~M.nd.binary_dilation(c != M.BACKGROUND, M.disk(8))[:M.H - length - 8, :M.W - width - 8])
    free = free[(free[:, 0] > 8) & (free[:, 1] > 8)]
    if not len(free): return None
    y, x = free[len(free) // 2]
    c, depth = c.copy(), depth.copy()
    c[y:y + length, x:x + width] = M.TOP
    depth[y:y + length, x:x + width] = (np.median(depth[depth > 0]) + np.tan(np.radians(degrees)) * M.CM * np.arange(length))[:, None]
    return c, depth


def main():
    bad = []
    files = sorted(glob.glob(f'{HERE}/cases/edge-on/*.cls'))
    if not files: bad.append('edge-on: no saved picture')
    for f in files:
        name = os.path.basename(f)[:-4]
        c, depth = M.read_cls(f), M.read_depth(f[:-4] + '.depth.gz')
        seen = loose(c, depth)
        flat = loose(c, np.where(c != M.BACKGROUND, depth, 0))
        print(f'edge-on {name}: loose {seen:.1f} cm², the same strips with no cloth between {flat:.1f} cm²')
        if seen > 0: bad.append(f'edge-on {name}: a wall seen edge-on reads as a loose piece ({seen:.1f} cm²)')
        if flat <= M.LIMITS['loose']: bad.append(f'edge-on {name}: a strip alone in the air no longer counts ({flat:.1f} cm²)')
        for degrees in (0, 20, 45, 70):
            planted = thread(c, depth, degrees)
            if planted is None: bad.append(f'edge-on {name}: no room in the background to plant a thread'); break
            extra = loose(*planted) - seen
            print(f'  thread planted at {degrees} degrees: {extra:.1f} cm²')
            if extra <= M.LIMITS['loose']: bad.append(f'edge-on {name}: a thread in the air at {degrees} degrees no longer counts ({extra:.1f} cm²)')
    if bad: sys.exit('\n'.join(bad))


if __name__ == '__main__':
    main()
