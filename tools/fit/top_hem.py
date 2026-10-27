"""Hem of the top per angle around the body, the same as site/garment-hem.ts.

The layer table hides the whole triangle of the bottom that sits under the top; the site draws back the part of it
below the hem, clipped at this line (without it the trousers end jagged just below the hem). layer_check.py
measures with the same line: the hidden point below the hem is drawn.
The hem is the lowest height of the torso fabric (|x| < TORSO, leaving out the sleeve at the side) in each slice of
STEP degrees of atan2(x, z); an empty slice (open front) interpolates between its neighbours.
A top that hangs off the bottom leaves a gap under its hem, and from below the eye looks up into it past the cut: the
body showed above the trousers' cut edge (030 over 001). With the hem's radius (the innermost torso fabric up to BAND
above the line), the cut rises by LIFT times what the hem stands off the point, up to LIFT_MAX."""
import numpy as np

STEP, TORSO = 5, .18   # degrees per slice, half width of the torso (m): the same numbers as site/garment-hem.ts
BAND, LIFT, LIFT_MAX = .05, .6, .03   # m, m per m off, m: the same numbers as site/garment-hem.ts
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


def radius(V, hem):
    """Radius of the hem per slice: the innermost torso fabric (distance from the y axis) up to BAND above the line, so
    the cut rises only where every layer of the top (a hem folded inwards too) stands off the point; 0 in an empty
    slice (no lift there)."""
    V = V[np.abs(V[:, 0]) < TORSO]; k = np.floor(slice_of(V)).astype(int) % N
    ok = (V[:, 1] >= hem[k]) & (V[:, 1] < hem[k] + BAND)
    r = np.full(N, np.inf); np.minimum.at(r, k[ok], np.hypot(V[ok, 0], V[ok, 2]))
    return np.where(np.isfinite(r), r, 0)


def height(hem, P, rad=None):
    """Hem height at points P (interpolated between slices); with the hem's radius, raised by what it stands off P."""
    t = slice_of(P); i = np.floor(t).astype(int) % N; j = (i + 1) % N; f = t - np.floor(t)
    y = hem[i] * (1 - f) + hem[j] * f
    if rad is None: return y
    return y + np.minimum(LIFT_MAX, LIFT * np.maximum(0, (rad[i] * (1 - f) + rad[j] * f) - np.hypot(P[:, 0], P[:, 2])))
