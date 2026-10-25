"""Forearm and hand of the mannequin at a person's length (poses B and C).

The mannequin is 1.825 m tall with the elbow in place (1.16 m, 0.64 of the height, as in a person), but its wrist sits
at 0.96 m and its fingertips at 0.81 m; in a person of that height they are about 0.87 and 0.69 (0.48 and 0.38 of
the height), so the long sleeves of the jackets, made for a real arm, would cover the whole hand. Here the arm below the elbow stretches vertically only:
forearm from WRIST to NEW_WRIST, hand 1.2 times longer, from the new wrist. Nothing else on the body changes and the
mesh keeps the same triangles, so the bottom garments' masks stay valid (only the hash changes).
Idempotent: an arm already stretched (fingertips below 0.75 m) does not change. Then: update the hashes in
poses.json and run install.py (tops) and install.py --bottom-line (bottoms).
usage: python3 tools/fit/arm.py"""
import os, hashlib, json, numpy as np
from glb_patch import read, write, accessor_view
from paths import BODY
TOP = 1.18           # m: above this (elbow and up) nothing changes
WRIST, NEW_WRIST = .96, .87
HAND = 1.2           # the hand (wrist to fingertips, 15 cm) becomes 18 cm
ARM_X = .17          # |x| of the arm below the elbow; hip and thigh stay within 0.165


def stretch(y):
    """(new y, local vertical scale) of a point on the arm."""
    k1 = (TOP - NEW_WRIST) / (TOP - WRIST)
    forearm = y >= WRIST
    yn = np.where(y >= TOP, y, np.where(forearm, TOP - (TOP - y) * k1, NEW_WRIST - (WRIST - y) * HAND))
    k = np.where(y >= TOP, 1.0, np.where(forearm, k1, HAND))
    return yn, k


def body(path):
    js, b = read(path)
    p = js['meshes'][0]['primitives'][0]['attributes']
    pa, ps, pst = accessor_view(js, b, p['POSITION']); na, ns, nst = accessor_view(js, b, p['NORMAL'])
    assert pst == nst == 12
    P = np.frombuffer(bytes(b[ps:ps + pa['count'] * 12]), '<f4').reshape(-1, 3).astype(float)
    N = np.frombuffer(bytes(b[ns:ns + na['count'] * 12]), '<f4').reshape(-1, 3).astype(float)
    arm = (np.abs(P[:, 0]) > ARM_X) & (P[:, 1] < TOP)
    assert arm.any()
    if P[arm, 1].min() < .75:
        return False
    assert np.abs(P[(P[:, 1] < TOP) & ~arm & (P[:, 1] > .5), 0]).max() < .165, 'hip touching the arm'
    yn, k = stretch(P[arm, 1])
    P[arm, 1] = yn
    n = N[arm]; n[:, 1] /= k; N[arm] = n / np.linalg.norm(n, axis=1, keepdims=True)
    b[ps:ps + pa['count'] * 12] = P.astype('<f4').tobytes(); b[ns:ns + na['count'] * 12] = N.astype('<f4').tobytes()
    pa['min'], pa['max'] = P.min(0).tolist(), P.max(0).tolist()
    write(path, js, b)
    return True


if __name__ == '__main__':
    reg = BODY + 'poses.json'; r = json.load(open(reg))
    for pose, d in r['poses'].items():
        changed = body(BODY + d['asset'])
        d['hash'] = hashlib.sha256(open(BODY + d['asset'], 'rb').read()).hexdigest()
        print(pose, 'stretched' if changed else 'already stretched', d['hash'][:12])
    open(reg, 'w').write(json.dumps(r, indent=2) + '\n')
