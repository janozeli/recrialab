"""Closes the fly of shorts 008, which the original model had open (flaps apart and lining showing).

The two front flaps move in x towards each other until they cross (OV of overlap per side); the lining between the
seams becomes a strip under the buttonhole flap. The displacement fades over 15 cm to the sides, at the back and
below the crotch, and the buttonhole side rises LIFT to line up the waistband. Only positions change: UV, texture
and triangles stay the same. Guarded by site/fit.test.ts (lining visible from the front < 1 cm²).
usage: python3 tools/fit/zipper.py ORIGINAL.glb OUTPUT.glb      (original: tools/fit/reference/originals/before-drape/008.glb)"""
import sys, hashlib, numpy as np
from garment import Garment

# seams of the open fly (x, y in meters, body B), read on the texture (dark lines) with rays from the front;
# above 0.958 the left edge is the tip of the waistband with the button
LEFT = np.array([[.006, .905], [0, .912], [-.015, .932], [-.030, .958], [.003, .963]])
RIGHT = np.array([[.010, .905], [.012, .908], [.017, .920], [.015, .932], [.012, .944], [.012, .958], [.0125, .963]])
GAP_WAISTBAND = .042    # the waistband moves with the cloth just below it
L, OV, LIFT = .15, .007, .007

ss = lambda t: np.clip(t, 0, 1) ** 2 * (3 - 2 * np.clip(t, 0, 1))
fade = lambda t: 1 - ss(t)


def close(V):
    V = V.copy(); x, y, z = V.T
    yc = np.clip(y, .905, .963)
    XL = np.interp(yc, LEFT[:, 1], LEFT[:, 0]); XR = np.interp(yc, RIGHT[:, 1], RIGHT[:, 0])
    G = np.where(yc > .958, GAP_WAISTBAND, XR - XL)
    k = ss((yc - .905) / .01)
    a = G / 2 + OV * k; b = -G / 2 - OV * k
    s = np.where(x <= XL, a * fade((XL - x) / L),
                 np.where(x >= XR, b * fade((x - XR) / L), a + (b - a) * (x - XL) / np.maximum(XR - XL, 1e-6)))
    front = ss((z - .02) / .03)
    V[:, 0] += s * front * ss((y - .88) / .025)
    V[:, 1] += np.where(x >= XR, LIFT * fade((x - XR) / L), 0) * front * ss((y - .85) / .11)
    return V


OPEN = '8941951f1536becf6ae4f19b09e917f038335a7e3b400314d3d03549e2c8f170'  # reference/originals/before-drape; applying twice crosses too far

if __name__ == '__main__':
    assert hashlib.sha256(open(sys.argv[1], 'rb').read()).hexdigest() == OPEN, 'the input is not the open 008 (reference/originals/before-drape)'
    g = Garment(sys.argv[1]); g.save(sys.argv[2], close(g.vertices()))
