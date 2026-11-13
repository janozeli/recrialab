"""Saved pictures that hold a measure of measure.py to what it was written for.

  python3 tools/visual-qa/cases.py

edge-on: tops from the fit engine seen from below in profile. The front or back wall of the shell, seen edge-on, hangs
under the nearer hem as a strip 1 to 5 px wide, cut from the garment where it gets thinner than a pixel. `loose` read
it as a piece in the air (1.4 to 2.2 cm², limit 1.0). It has to read 0 here, and the same strip made flat in depth
(a shard facing the camera) has to count again.
"""
import glob, os, sys
import numpy as np
import measure as M

HERE = os.path.dirname(os.path.abspath(__file__))


def loose(c, depth):
    return sum(M.loose_area(c, np.isin(c, k), depth) for k in ((M.TOP, M.TOP_BACK), (M.BOTTOM, M.BOTTOM_BACK))) * M.CM2


def main():
    bad = []
    files = sorted(glob.glob(f'{HERE}/cases/edge-on/*.cls'))
    if not files: bad.append('edge-on: no saved picture')
    for f in files:
        name = os.path.basename(f)[:-4]
        c, depth = M.read_cls(f), M.read_depth(f[:-4] + '.depth.gz')
        seen = loose(c, depth)
        flat = loose(c, np.where(depth > 0, np.median(depth[depth > 0]), 0))
        print(f'edge-on {name}: loose {seen:.1f} cm², the same strips flat in depth {flat:.1f} cm²')
        if seen > 0: bad.append(f'edge-on {name}: a wall seen edge-on reads as a loose piece ({seen:.1f} cm²)')
        if flat <= M.LIMITS['loose']: bad.append(f'edge-on {name}: a strip facing the camera no longer counts ({flat:.1f} cm²)')
    if bad: sys.exit('\n'.join(bad))


if __name__ == '__main__':
    main()
