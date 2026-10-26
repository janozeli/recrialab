"""The trousers' hem falls open above the sneaker; it does not wrap it like a boot cover.

The 014 built from a shape generated on the mannequin came with the hem moulded over the instep down to 7 cm from the
floor, the cloth lying on the shoe (and its print smeared with the shoe's colours). A hem that hangs, straight or
flared, is upright; one that wraps the shoe lies flat on it. Here, per bottom, the area of the cloth below INSTEP and
more than AHEAD in front of the shin that lies flat (|normal y| above FLAT): at most MAX cm².
usage: python3 tools/fit/shoe.py [IDs]   (without IDs: the 15 bottoms; exits with an error above MAX)"""
import os, sys, numpy as np
from garment import Garment
from metric import body, POSE_C
from paths import GARMENTS
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '../visual-qa'))
from known_issues import FILE as KNOWN_ISSUES, known_issues  # noqa: E402

INSTEP = .12   # the neutral body's ankle
SHIN = .16     # the front of the shin, at this height
AHEAD = .02
FLAT = .5
MAX = 15.      # cm² (the other trousers: up to 6.9)
# piece: (known issue, cm²) above MAX, held at the recorded value while the issue is open
AS_IS = {
}


def over_shoe(pid):
    b = body('C' if pid in POSE_C else 'B').vertices
    front = {s: b[(b[:, 0] * s > 0) & (np.abs(b[:, 1] - SHIN) < .02), 2].max() for s in (1, -1)}
    m = Garment(GARMENTS + f'{pid}.glb').mesh(); c = m.triangles_center
    ahead = c[:, 2] - np.where(c[:, 0] > 0, front[1], front[-1])
    k = (c[:, 1] < INSTEP) & (ahead > AHEAD) & (np.abs(m.face_normals[:, 1]) > FLAT)
    return m.area_faces[k].sum() * 1e4


if __name__ == '__main__':
    issues = known_issues()
    bad = [f'{pid}: {issue} is not an open known issue naming it in {KNOWN_ISSUES}'
           for pid, (issue, _) in AS_IS.items() if pid not in issues.get(issue, ())]
    for pid in sys.argv[1:] or [f'{i:03d}' for i in range(1, 16)]:
        a = over_shoe(pid); ceiling = AS_IS.get(pid, ('', MAX))[1]
        print(f'{pid} cloth lying on the sneaker: {a:.1f} cm²')
        if a > ceiling + .05: bad.append(f'{pid} {a:.1f} cm² > {ceiling:.1f}')
    if bad: sys.exit('hem wrapped over the sneaker: ' + ', '.join(bad))
