"""Body mask for a top: which body triangles disappear when it is worn.

A triangle disappears when it pokes through the garment (there is fabric just inside it) or touches it from
inside (< TOUCH). Body that sits deeper stays drawn: the garment already covers it, and so the collar and the
sleeve show neck and arm instead of a hollow. The arm below a short sleeve never disappears; in a long sleeve the
whole arm disappears down to the wrist. Last, what cameras around the mannequin see poking through the fabric
from the side disappears too (`poke_through`), which the ray along the normal misses."""
import numpy as np
from trimesh.ray.ray_pyembree import RayMeshIntersector

TOUCH = .012   # m
ARM_Y = .6     # m: no arm below this (the fingertips are at 0.69 m, arm.py); the hip never passes |x| = 0.165
INSIDE = .06   # m: how far to look for fabric inside the body


def hits(ri, o, d, maxd):
    loc, ir, _ = ri.intersects_location(o, d, multiple_hits=True)
    out = np.full(len(o), np.inf)
    if len(ir):
        dist = np.einsum('ij,ij->i', loc - o[ir], d[ir]); ok = dist > 0
        np.minimum.at(out, ir[ok], dist[ok])
    out[out > maxd] = np.inf
    return out


def samples(V, F):
    """Center, middle of each edge and near each vertex: the faceted triangle is large, and a corner that pokes
    through the garment escapes if only the center is tested."""
    C = V[F].mean(1)
    return [C] + [(V[F[:, k]] + C) / 2 for k in range(3)] + [.85 * V[F[:, k]] + .15 * C for k in range(3)]


def surrounded(ri, C, V, radius=.15, minimum=4):
    """Arm inside a sleeve: from the arm axis at that height, at least `minimum` of 8 horizontal directions find
    fabric. In a tank top's armhole only the torso side has fabric, and there the arm shows."""
    axis = C.copy()
    for side in (-1, 1):
        A = V[(side * V[:, 0] > .17) & (V[:, 1] > ARM_Y)]
        m = side * C[:, 0] > .17
        fx = np.interp(C[m, 1], *_profile(A, 0)); fz = np.interp(C[m, 1], *_profile(A, 2))
        axis[m, 0] = fx; axis[m, 2] = fz
    n = np.zeros(len(C), int)
    for a in np.radians(np.arange(0, 360, 45)):
        d = np.repeat([[np.sin(a), 0, np.cos(a)]], len(C), 0)
        n += np.isfinite(hits(ri, axis, d, radius))
    return n >= minimum


def _profile(A, k, step=.02):
    ys = np.arange(A[:, 1].min(), A[:, 1].max() + step, step)
    c = [np.median(A[np.abs(A[:, 1] - y) < step, k]) if (np.abs(A[:, 1] - y) < step).any() else np.nan for y in ys]
    c = np.array(c); ok = np.isfinite(c)
    return ys[ok], c[ok]


def cameras(step=.004, center=1.25, half=.5, elevs=(0, .25), turn=0):
    """Cameras around the mannequin, at chest height and a little above, as on the site: (origins, direction).
    The layers use another window (lower, also looking up at the hem)."""
    u, v = np.meshgrid(np.arange(-half, half, step), np.arange(-half, half, step))
    for ang in range(turn, 360 + turn, 20):
        for elev in elevs:
            a = np.radians(ang)
            d = -np.array([np.sin(a), 0, np.cos(a)]); d[1] = -elev; d /= np.linalg.norm(d)
            side = np.array([np.cos(a), 0, -np.sin(a)]); up = np.cross(side, d)
            o = np.array([0, center, 0]) - 3 * d + u.ravel()[:, None] * side + v.ravel()[:, None] * up
            yield o, np.repeat(d[None], len(o), 0)


def sleeve_hem(G):
    sleeve = G[np.abs(G[:, 0]) > .24, 1]   # outside the torso: sleeve only
    return np.percentile(sleeve, 2) if len(sleeve) > 50 else 1.3


def zones(body, garment, ri):
    """Where a point poking through the fabric must disappear. near: torso (without the neck, which is right in
    front of the back collar) and arm inside a sleeve, body < 3 cm from the fabric. sleeve: arm inside a sleeve
    with any fabric behind it up to 15 cm (the arm coming out through the back of the sleeve). Arm inside a sleeve
    = fabric around the arm axis, below the shoulder head: never the arm beside the blouse nor the tank top's
    armhole."""
    F = body.faces; V = body.vertices; C = V[F].mean(1); G = garment.vertices
    arm = (np.abs(C[:, 0]) > .17) & (C[:, 1] > ARM_Y)
    hem = sleeve_hem(G)
    in_sleeve = arm & (C[:, 1] > hem - .01) & (C[:, 1] < 1.42) & surrounded(ri, C, V)
    near = (~arm | in_sleeve) & (C[:, 1] > G[:, 1].min() + .02) & (C[:, 1] < 1.45)
    hand = arm & (C[:, 1] < .9)   # the hand never disappears
    return near & ~hand, in_sleeve & (C[:, 1] > hem + .01) & ~hand


def poke_through(body, garment, hide, gap=.03, rounds=2, legs=False):
    """Body triangles the camera sees in front of the fabric with the fabric just behind (< gap): the points that
    poke through the garment from the side and escape the ray along the normal. legs: also the LEGS cameras
    (bottoms: the ankle poking through the trouser cuff)."""
    ri = RayMeshIntersector(garment)
    F = body.faces
    out = np.zeros(len(F), bool)
    for _ in range(rounds):
        vis = np.nonzero(~(hide | out))[0]
        rb = RayMeshIntersector(body.submesh([vis], append=True))
        new = np.zeros(len(F), bool)
        for o, dd in _cams(legs):
            tb, fb = first(rb, o, dd, front_only=True); tg, _ = first(ri, o, dd)
            with np.errstate(invalid='ignore'):
                m = np.isfinite(tb) & np.isfinite(tg) & (tb < tg) & (tg - tb < gap)
            new[vis[fb[m]]] = True
        if not new.any(): break
        out |= new
    return out


# the site's orbit (target at 1 m, looking from above and below); layer_check.py and the bottoms use it
ORBIT = dict(step=.008, center=1.0, half=.66, elevs=(-.4, -.15, .1, .35), turn=10)
# from the floor to the hip, with the same elevations: the site's orbit sees the ankle, which the others leave out
LEGS = dict(ORBIT, center=.45, half=.45)


def _cams(legs):
    """Cameras of poke_through() and exposed(): the parallel ones and the visual QA views (site_cameras)."""
    from itertools import chain
    return chain(cameras(), cameras(**LEGS), site_cameras()) if legs else chain(cameras(), site_cameras())


# the 14 visual QA views (visual-qa.mjs: target at 1.0 m, camera at 4.4 m, fov 30), in perspective: the parallel
# cameras() look at the hem from further below than the real camera, and miss an ankle that the site shows
SITE = [(az, 88) for az in range(0, 360, 45)] + [(az, 111.6) for az in range(0, 360, 90)] + [(0, 68.4), (180, 68.4)]


def site_cameras(step=.005, radius=4.4, target=1.0):
    u, v = np.meshgrid(np.arange(-.6, .6, step), np.arange(-1.15, 1.15, step))
    center = np.array([0, target, 0])
    for az, polar in SITE:
        a, p = np.radians(az), np.radians(polar)
        pos = center + radius * np.array([np.sin(p) * np.sin(a), np.cos(p), np.sin(p) * np.cos(a)])
        front = (center - pos) / radius; side = np.cross(front, [0, 1, 0]); side /= np.linalg.norm(side)
        up = np.cross(side, front)
        d = center + u.ravel()[:, None] * side + v.ravel()[:, None] * up - pos
        yield np.repeat(pos[None], len(d), 0), d / np.linalg.norm(d, axis=1)[:, None]


def exposed(body, garment, legs=False):
    """Body triangles that some camera (those of poke_through(), the site's orbit and the visual QA views) sees
    first, with no fabric just in front: hiding them shows the background."""
    rg, rb = RayMeshIntersector(garment), RayMeshIntersector(body)
    out = np.zeros(len(body.faces), bool)
    for o, dd in __import__('itertools').chain(_cams(legs), cameras(**ORBIT)):
        tg, _ = first(rg, o, dd); tb, fb = first(rb, o, dd, front_only=True)
        with np.errstate(invalid='ignore'):
            m = np.isfinite(tb) & ~(tg < tb + .05)
        out[fb[m]] = True
    return out


def poke_through_without_holes(body, garment, hide, exposed_faces=None, legs=False):
    """Points (above) that can be hidden without showing the background: left out is the triangle that, in some
    camera (those of poke_through() and the site's orbit), is the first of the body with no fabric just in front
    (the waistband, where the trousers are narrower than the body)."""
    extra = poke_through(body, garment, hide, legs=legs)
    return extra & ~(exposed(body, garment, legs) if exposed_faces is None else exposed_faces)


def legs_without_holes(body, garment, hide, below=.9):
    """Body of the legs and hip (below `below`) that pokes through the bottom, seen by the LEGS cameras (the ankle
    crossing the trouser hem, the thigh at the shorts' crotch), where hiding it does not show the background. It
    only adds: the rest of the mask stays."""
    C = body.vertices[body.faces].mean(1)
    return poke_through(body, garment, hide, legs=True, rounds=3) & ~exposed(body, garment, True) & ~hide & (C[:, 1] < below)


def first(ri, o, d, front_only=False, cut=None):
    """First intersection of each ray. front_only ignores back faces (the site does not draw them) and cut(points)
    says which points the shader discards (the body under the waistband, waist.py)."""
    t = np.full(len(o), np.inf); tri = np.full(len(o), -1)
    loc, ir, it = ri.intersects_location(o, d, multiple_hits=True)
    if front_only and len(ir):
        f = np.einsum('ij,ij->i', ri.mesh.face_normals[it], d[ir]) < 0
        loc, ir, it = loc[f], ir[f], it[f]
    if cut is not None and len(ir):
        f = ~cut(loc); loc, ir, it = loc[f], ir[f], it[f]
    if len(ir):
        dist = np.einsum('ij,ij->i', loc - o[ir], d[ir])
        k = np.lexsort((dist, ir)); head = np.r_[True, ir[k][1:] != ir[k][:-1]]
        t[ir[k][head]] = dist[k][head]; tri[ir[k][head]] = it[k][head]
    return t, tri


def hidden_triangles(body, garment, long_sleeve=False):
    ri = RayMeshIntersector(garment)
    F = body.faces; V = body.vertices; n = body.face_normals
    C = V[F].mean(1)
    hide = np.zeros(len(F), bool)
    # vertex corners only on the torso: at the neck the collar shows neck, not hollow, and the arm has its own rules
    torso = (np.abs(C[:, 0]) <= .17) & (C[:, 1] < 1.45)
    for k, p in enumerate(samples(V, F)):
        o = p + n * 1e-4
        h = np.isfinite(hits(ri, o, n, TOUCH)) | np.isfinite(hits(ri, o, -n, INSIDE))
        hide |= h if k < 4 else h & torso
    arm = (np.abs(C[:, 0]) > .17) & (C[:, 1] > ARM_Y)
    hem = sleeve_hem(garment.vertices)
    hide &= ~(arm & (C[:, 1] < hem + .02))   # the arm below the sleeve stays
    # arm inside the sleeve: it disappears when there is fabric around it (outside or poking through), as in a long
    # sleeve; in a tank top's armhole (no fabric around the arm) the arm stays
    in_sleeve = arm & (C[:, 1] > hem + .02) & (C[:, 1] < 1.45)
    in_sleeve[in_sleeve] = surrounded(ri, C[in_sleeve], V)
    idx = np.nonzero(in_sleeve)[0]
    if len(idx):
        o = C[idx] + n[idx] * 1e-4
        hide[idx] |= np.isfinite(hits(ri, o, n[idx], .15)) | np.isfinite(hits(ri, o, -n[idx], INSIDE))
    if long_sleeve:
        hide |= arm & (C[:, 1] > hem + .03) & (C[:, 1] < 1.5)
    # Points the camera sees and the ray along the normal misses (the arm coming out through the back of the sleeve,
    # whose neighbours already disappear by the normal rule).
    near, sleeve = zones(body, garment, ri)
    hide |= poke_through(body, garment, hide) & near
    hide |= poke_through(body, garment, hide, gap=.15) & sleeve
    hide &= ~(arm & (C[:, 1] < .9))                  # the hand never disappears
    return np.nonzero(hide)[0]
