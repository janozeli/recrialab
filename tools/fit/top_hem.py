"""Hem of the top per angle around the body, the same as site/garment-hem.ts.

The layer table hides the whole triangle of the bottom that sits under the top; the site draws back the part of it
below the hem, clipped at this line (without it the trousers end jagged just below the hem). layer_check.py
measures with the same line: the hidden point below the hem is drawn.
The hem is the lowest height of the torso fabric (|x| < TORSO, leaving out the sleeve at the side) in each slice of
STEP degrees of atan2(x, z); an empty slice (open front) interpolates between its neighbours."""
import numpy as np

STEP, TORSO = 5, .18   # degrees per slice, half width of the torso (m): the same numbers as site/garment-hem.ts
N = 360 // STEP


def slice_of(P):
    return (np.degrees(np.arctan2(P[:, 0], P[:, 2])) % 360) / STEP


def line(V):
    """Hem height per slice, from the vertices of the top."""
    V = V[np.abs(V[:, 0]) < TORSO]
    hem = np.full(N, np.inf)
    np.minimum.at(hem, np.floor(slice_of(V)).astype(int) % N, V[:, 1])
    ok = np.isfinite(hem)
    if not ok.any():
        return np.full(N, -np.inf)   # no torso: nothing comes back
    if not ok.all():
        k = np.nonzero(ok)[0]
        hem = np.interp(np.arange(N), np.r_[k - N, k, k + N], np.tile(hem[k], 3))
    return hem


def height(hem, P):
    """Hem height at points P (interpolated between slices)."""
    t = slice_of(P); i = np.floor(t).astype(int) % N; f = t - np.floor(t)
    return hem[i] * (1 - f) + hem[(i + 1) % N] * f
