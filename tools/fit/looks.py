"""The 345 looks of the engine's output, measured from 12 cameras around the mannequin, one ray per cm².

- POKE: the bottom shows in front of the top (the bottom is the first surface and the top is less than 3 cm behind);
- BELLY: the torso is the first surface between the top's hem and the waistband.
Both in cm², for every bottom with every top. engine.py calls measure() on the parts it built.
usage: from looks import measure; measure(meshes, low_poly_body)  ->  {'BBB.TTT': [poke, belly]}"""
import numpy as np, trimesh
import landmarks as L

BEHIND = .03           # m: a top this close behind the bottom is being poked through
BAND = (.90, 1.05)     # m: heights where a torso in view is belly


def depth(m, X, Y, angles):
    out = []
    for a in angles:
        d = np.array([np.sin(a), 0, np.cos(a)]); r = np.array([np.cos(a), 0, -np.sin(a)])
        o = X[:, None] * r + Y[:, None] * [0, 1, 0] + d * 3
        t = np.full(len(o), np.inf); loc, ir, _ = m.ray.intersects_location(o, np.repeat(-d[None], len(o), 0), multiple_hits=False)
        t[ir] = np.linalg.norm(loc - o[ir], axis=1); out.append(t)
    return np.array(out)


def measure(meshes, low):
    """meshes: {id: trimesh of the garment as built}; low: the low-poly mannequin of pose B."""
    angles = np.arange(12) * np.pi / 6; X, Y = (a.ravel() for a in np.meshgrid(np.arange(-.45, .45, .01), np.arange(.60, 1.20, .01)))
    D = {p: depth(m, X, Y, angles) for p, m in meshes.items()}
    lab = L.limb(np.asarray(low.vertices))
    torso = depth(trimesh.Trimesh(low.vertices, low.faces[(lab[low.faces] == 0).all(1)], process=False), X, Y, angles)
    band = (Y > BAND[0]) & (Y < BAND[1]); out = {}
    for b in [p for p in meshes if int(p) <= 15]:
        for t in [p for p in meshes if int(p) > 15]:
            with np.errstate(invalid='ignore'):
                poke = int(((D[b] < D[t]) & (D[t] - D[b] < BEHIND)).sum())
            belly = int(((torso < np.minimum(D[b], D[t]) - .002) & np.isfinite(torso))[:, band].sum())
            out[f'{b}.{t}'] = [poke, belly]
    return out
