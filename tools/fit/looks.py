"""The 345 looks of the engine's output, measured from 12 cameras around the mannequin, one ray per cm².

- POKE: the bottom shows in front of the top (the bottom is the first surface and the top is less than 3 cm behind);
- BELLY: the torso is the first surface between the top's hem and the waistband.
Both in cm², for every bottom with every top. engine.py calls measure() on the parts it built.
- THROUGH, per garment: the body is the first surface and the garment's cloth over that same part of the body is less
  than 3 cm behind it (the body shows through the cloth: a hole at the armpit, a vertex of the mannequin through a
  skirt). A hand in front of a jacket's side is another part of the body and does not count.
usage: from looks import measure; measure(meshes, low_poly_body)  ->  {'BBB.TTT': [poke, belly]}
       from looks import through; through(garment, low_poly_body)  ->  cm²"""
import numpy as np, trimesh
from scipy.spatial import cKDTree
import landmarks as L

BEHIND = .03           # m: a top this close behind the bottom is being poked through
REACH = .08            # m: the body a piece of cloth wears lies this close under it
BAND = (.90, 1.05)     # m: heights where a torso in view is belly


def depth(m, X, Y, angles, facing=False):
    """facing: also whether the first surface met shows its outer face to the camera."""
    out = []; face = []
    for a in angles:
        d = np.array([np.sin(a), 0, np.cos(a)]); r = np.array([np.cos(a), 0, -np.sin(a)])
        o = X[:, None] * r + Y[:, None] * [0, 1, 0] + d * 3
        t = np.full(len(o), np.inf); loc, ir, tri = m.ray.intersects_location(o, np.repeat(-d[None], len(o), 0), multiple_hits=False)
        t[ir] = np.linalg.norm(loc - o[ir], axis=1); out.append(t)
        f = np.zeros(len(o), bool); f[ir] = m.face_normals[tri] @ d > 0; face.append(f)
    return (np.array(out), np.array(face)) if facing else np.array(out)


def measure(meshes, low):
    """meshes: {id: trimesh of the garment as built}; low: the low-poly mannequin of pose B."""
    angles = np.arange(12) * np.pi / 6; X, Y = (a.ravel() for a in np.meshgrid(np.arange(-.45, .45, .01), np.arange(.60, 1.20, .01)))
    D = {}; OUT = {}
    for p, m in meshes.items(): D[p], OUT[p] = depth(m, X, Y, angles, facing=True)
    lab = L.limb(np.asarray(low.vertices))
    torso = depth(trimesh.Trimesh(low.vertices, low.faces[(lab[low.faces] == 0).all(1)], process=False), X, Y, angles)
    band = (Y > BAND[0]) & (Y < BAND[1]); out = {}
    for b in [p for p in meshes if int(p) <= 15]:
        for t in [p for p in meshes if int(p) > 15]:
            with np.errstate(invalid='ignore'):
                # the top's outer face behind the bottom: a bottom seen under an uneven hem, with the inside of the
                # top's far wall behind it, is in view, not poking through
                poke = int(((D[b] < D[t]) & (D[t] - D[b] < BEHIND) & OUT[t]).sum())
            belly = int(((torso < np.minimum(D[b], D[t]) - .002) & np.isfinite(torso))[:, band].sum())
            out[f'{b}.{t}'] = [poke, belly]
    return out


def worn(low, lab, kd, p, n):
    """Label of the body part under each point p of the cloth: where the ray from p against the cloth's normal n meets
    the body within REACH, the label of that face; otherwise that of the nearest vertex."""
    out = lab[kd.query(p)[1]]
    loc, ir, tri = low.ray.intersects_location(p, -n, multiple_hits=False)
    near = np.linalg.norm(loc - p[ir], axis=1) < REACH
    out[ir[near]] = lab[low.faces[tri[near], 0]]
    return out


def through(garment, low):
    """cm² of body in view through the garment's cloth, from the 12 cameras, one ray per cm². The cloth just behind the
    body must show its outer face to the camera: at an opening of the garment itself (an armhole, the end of a sleeve,
    the hem of shorts) the body is in view with the inside of the far wall behind it, and that is not a hole."""
    angles = np.arange(12) * np.pi / 6; X, Y = (a.ravel() for a in np.meshgrid(np.arange(-.60, .60, .01), np.arange(0, 1.85, .01)))
    v = np.asarray(low.vertices); lab = L.limb(v); kd = cKDTree(v); n = 0
    for a in angles:
        d = np.array([np.sin(a), 0, np.cos(a)]); r = np.array([np.cos(a), 0, -np.sin(a)])
        o = X[:, None] * r + Y[:, None] * [0, 1, 0] + d * 3; back = np.repeat(-d[None], len(o), 0)
        hb, ib, _ = low.ray.intersects_location(o, back, multiple_hits=False)
        hg, ig, fg = garment.ray.intersects_location(o, back, multiple_hits=False)
        tb = np.full(len(o), np.inf); tb[ib] = np.linalg.norm(hb - o[ib], axis=1); pb = np.zeros((len(o), 3)); pb[ib] = hb
        tg = np.full(len(o), np.inf); tg[ig] = np.linalg.norm(hg - o[ig], axis=1); pg = np.zeros((len(o), 3)); pg[ig] = hg
        outer = np.zeros(len(o), bool); outer[ig] = garment.face_normals[fg] @ d > 0
        nrm = np.zeros((len(o), 3)); nrm[ig] = garment.face_normals[fg]
        with np.errstate(invalid='ignore'):
            k = np.flatnonzero((tb < tg - .002) & (tg - tb < BEHIND) & outer)
        if not len(k): continue
        # the part of the body the cloth wears is the one under it, along its own normal: beside the torso the nearest
        # vertex of the body is often the arm's, and a bare arm in front of the side of a top is not a hole in a sleeve
        n += int((lab[kd.query(pb[k])[1]] == worn(low, lab, kd, pg[k], nrm[k])).sum())
    return n
