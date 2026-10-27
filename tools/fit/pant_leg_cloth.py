"""Dresses the trouser leg on the neutral body as cloth, in a single step, instead of patching the cuff.

013 (pose C) came from Tripo with the elastic cuff on an ankle lower and closer together than the neutral body's,
and the two legs joined by a bridge of fabric down to the cuff. Here the whole leg, from the knee down and with a
transition up to TOP, becomes cloth (position based dynamics): each edge returns to the length it had in Tripo's
ORIGINAL GLB, bending between neighbouring faces is weak, and what sits closer than SLACK to the body moves out along
its normal. Each vertex only collides with the leg of its own side (the mesh's, when separate_legs.py separated the
legs; otherwise the sign of x). No vertex moves away from the body beyond where it was, or FAR (the gap baseline of
penetration.py). First, the cuff moves whole to the center of the body's leg (center_cuffs). Only positions and
normals change; UV and texture stay the same.
The input is the piece already run through separate_legs.py (and shin_tube.py) and leg_shape.py, and the ORIGINAL
goes along (same mesh). The stretch is measured against the ORIGINAL per region (measures): the middle between the
legs, the cuff and the rest, each with its own p99 of edge and area (only of the faces that move), because in the
p99 of the whole piece a small region that stretches a lot does not show. Refuses (does not write) above MAX or
MAX_FLIPPED.
usage: python3 tools/fit/separate_legs.py ORIGINAL.glb INPUT.glb ORIGINAL_SEP.glb SEPARATED.glb; [piece with fabric outside the
       leg below the shin (cuff.py): python3 tools/fit/shin_tube.py ORIGINAL_SEP.glb SEPARATED.glb ORIGINAL_SEP.glb SEPARATED.glb NNN];
       python3 tools/fit/leg_shape.py SEPARATED.glb NNN.glb NNN --again (INPUT is the published GLB, already run through leg_shape.py)
       python3 tools/fit/pant_leg_cloth.py ORIGINAL_SEP.glb NNN.glb OUTPUT.glb   (ORIGINAL: tools/fit/reference/originals/tripo/NNN.glb;
       then install.py --bottom NNN, only the new mask (joining it with the old one opens holes), and install.py --bottom-line NNN)
       python3 tools/fit/pant_leg_cloth.py --whole ORIGINAL.glb INPUT.glb OUTPUT.glb   (the whole piece below the waistband as
       cloth in one step, with the edge lengths of the ORIGINAL and INPUT's waistband, for trousers whose fabric is wide
       enough for the neutral body: WHOLE_PIECES)"""
import sys, struct, numpy as np, trimesh
from scipy.spatial import cKDTree
from garment import Garment
from glb_patch import accessor_view
from metric import body, POSE_C
from paths import piece_id
from separate_legs import leg_side

SLACK = .004         # minimum distance from the body
FAR = .03            # what was closer than this does not move away beyond it
TOP, LOOSE = .80, .10   # above TOP nothing moves; the fabric comes loose over LOOSE below it
WAIST = .02          # band measured on its own around TOP
CROTCH = .80         # below this each side collides only with its own leg
STEPS, ROUNDS = 250, 12
WHOLE_TOP, WHOLE_STEPS = 2., 400   # --whole: only the waistband held (TOP stands for "no constant line"), and more steps
# the pieces dressed with --whole (stretch.py measures their waist below the waistband)
WHOLE_PIECES = {
    '002',
    '004',
}
WAISTBAND, EDGE_STEP = .05, 10   # dressed whole, the waistband: the band below the top edge, per slice of degrees
WALL_BEND = 1.       # the inner wall (separate_legs.py) is flat: when it bends it turns inside out
BEND = .1            # bending stiffness (stiffer bending stretches the print more)
ARM_X = .17          # the arm hangs beside the thigh: it is not a collider
MIDDLE, CUFF = .015, .20   # regions measured on their own: the middle between the legs (the cut bridge and the walls of
                           # separate_legs.py) and the cuff
MAX = {'middle': (.15, .35), 'cuff': (.10, .35), 'waist': (.10, .35), 'hip': (.10, .35), 'rest': (.10, .35)}   # p99 of the edge length and of the area of the faces that move
THIN = .1            # height / longest side below this: a sliver
MAX_FLIPPED = .007   # area of flipped faces (the cuff folding over the sneaker)
# fraction of the way to the center: wholly at the center, the wide hem of 006 moves in front of its back hem and the
# ankle shows through the fraying; less than this, the fraying leaves the leg (cuff.py)
CENTER_PIECES = {'006': .8}
CENTER = (.16, .20, .35)  # the cuff moves to the center of the body's leg (above .16: below is the sneaker), wholly up to .20, nothing from .35 up


def weld(P, F):
    _, inv = np.unique(np.round(P, 5), axis=0, return_inverse=True); inv = inv.ravel()
    X = np.zeros((inv.max() + 1, 3)); X[inv] = P
    return X, inv, inv[F]


def uvs(g):
    out = []
    for _, _, p in g.parts:
        a, s, st = accessor_view(g.js, g.bin, p['attributes']['TEXCOORD_0'])
        out.append(np.array([struct.unpack_from('<2f', g.bin, s + i * st) for i in range(a['count'])]))
    return out


def correspondence(go, g):
    """Index in the original of each input vertex. islands.remove (slivers.py, islands.py) takes triangles away and the
    vertices left stay in the same order: the UV finds each one, walking forward only."""
    idx, off = [], 0
    for uo, u in zip(uvs(go), uvs(g)):
        j = 0
        for i in range(len(u)):
            while not np.array_equal(uo[j], u[i]): j += 1
            idx.append(off + j); j += 1
        off += len(uo)
    return np.array(idx)


def constrain(X, idx, rest, k):
    d = X[idx[:, 1]] - X[idx[:, 0]]; l = np.linalg.norm(d, axis=1, keepdims=True) + 1e-12
    c = (l - rest[:, None]) / l * d * .5 * k
    acc = np.zeros_like(X); n = np.zeros(len(X))
    np.add.at(acc, idx[:, 0], c); np.add.at(acc, idx[:, 1], -c); np.add.at(n, idx[:, 0], 1); np.add.at(n, idx[:, 1], 1)
    return acc / np.maximum(n, 1)[:, None]


def waistband(Xo):
    """Dressed whole: per vertex, its slice of EDGE_STEP degrees around the hip, the hip's center (x, z) and the height
    of the top edge per slice."""
    h = Xo[Xo[:, 1] >= CROTCH]; o = h[:, [0, 2]].mean(0)
    sl = lambda P: (np.degrees(np.arctan2(P[:, 0] - o[0], P[:, 2] - o[1])) % 360 // EDGE_STEP).astype(int)
    edge = np.full(360 // EDGE_STEP, -np.inf); np.maximum.at(edge, sl(h), h[:, 1])
    return sl, o, edge


def regions(Xo, F, whole=False):
    """Region of each face: 'middle' (center closer than MIDDLE to x = 0, below CROTCH), 'cuff' (below CUFF), 'waist'
    (within WAIST of TOP, where the held fabric meets the loose one and a pleat can form; dressed whole, the held part is
    the waistband and TOP is WAISTBAND below its top edge, per slice of EDGE_STEP degrees around the hip),
    'hip' (from CROTCH up, which leg_shape.py moves), 'rest'. Each is measured on its own so that a small region that
    stretches shows."""
    c = Xo[F].mean(1); top = Xo[F, 1].max(1)
    base = Xo[F, 1].min(1)
    if whole:
        sl, _, edge = waistband(Xo)
        line = edge[sl(c)] - WAISTBAND
        waist = (top >= CROTCH) & (top >= line - WAIST) & (base < line + WAIST)
    else:
        waist = (top >= TOP - WAIST) & (base < TOP + WAIST)
    return np.where((np.abs(c[:, 0]) < MIDDLE) & (top < CROTCH), 'middle', np.where(top < CUFF, 'cuff',
                    np.where(waist, 'waist', np.where(base >= CROTCH, 'hip', 'rest'))))


def measures(Xo, X, F, printed=None, moved=None, whole=False):
    """Per region: p99 of the change in edge length and in area of the faces that move, against the original; and the
    fraction of the area in flipped faces. A face without print (the three UVs on the same point: the walls of
    separate_legs.py, of a single colour) does not distort any design and stays out of the p99. The area only counts
    faces whose height is at least THIN of the longest side: on a sliver (sides 6.2, 2.8 and 3.5 cm) the area changes 59%
    with equal sides; its sides are already counted."""
    l = lambda P, i, j: np.linalg.norm(P[F[:, i]] - P[F[:, j]], axis=1)
    L0 = np.stack([l(Xo, 0, 1), l(Xo, 1, 2), l(Xo, 2, 0)], 1); L1 = np.stack([l(X, 0, 1), l(X, 1, 2), l(X, 2, 0)], 1)
    est = np.abs(L1 / np.maximum(L0, 1e-9) - 1)
    n0 = np.cross(Xo[F[:, 1]] - Xo[F[:, 0]], Xo[F[:, 2]] - Xo[F[:, 0]]); n1 = np.cross(X[F[:, 1]] - X[F[:, 0]], X[F[:, 2]] - X[F[:, 0]])
    a0 = np.linalg.norm(n0, axis=1); area = np.abs(np.linalg.norm(n1, axis=1) / np.maximum(a0, 1e-12) - 1)
    move = (np.linalg.norm(X - Xo, axis=1) > 1e-4)[F].any(1) & (a0 > 1e-7)
    if printed is not None: move &= printed
    if moved is not None: move &= moved[F].any(1)   # only what this step moved (the rest comes from earlier steps)
    full = a0 / np.maximum(L0.max(1), 1e-9) ** 2 >= THIN
    r, out = regions(Xo, F, whole), {}
    for name in MAX:
        k = move & (r == name); e = est[k][L0[k] > 1e-5]
        out[name] = (np.percentile(e, 99) if len(e) else 0.0, np.percentile(area[k & full], 99) if (k & full).any() else 0.0)
    flipped = (np.einsum('ij,ij->i', n0, n1) < 0) & (True if moved is None else moved[F].any(1))   # flipped in this step
    if printed is not None: flipped &= printed   # a wall without print folding is no design turned over
    return out, a0[flipped].sum() / a0.sum()


def center_cuffs(X0, side, b, strength=1.):
    """The cuff of each leg moves, whole, to the center of the body's leg at the same height (013 came with the left
    cuff 4.5 cm inwards: pushed along the normal, half of it came out on each side of the ankle, as flaps)."""
    from leg_shape import centers, DY
    low, full, loose = CENTER; V = b.vertices; X = X0.copy()
    for s in (1, -1):
        sel = np.flatnonzero((side == s) & (X0[:, 1] < loose + DY))
        if not len(sel): continue
        ys = np.arange(X0[sel, 1].min() - DY, loose + 2 * DY, DY)
        dc = centers(V[(np.sign(V[:, 0]) == s) & (V[:, 1] > low) & (V[:, 1] < loose + .15)], ys) - centers(X0[sel], ys)
        f = np.clip((X0[sel, 1] - ys[0]) / DY, 0, len(ys) - 1); i = np.arange(len(ys))
        r = np.clip((loose - X0[sel, 1]) / (loose - full), 0, 1) * strength
        X[sel, 0] += np.interp(f, i, dc[:, 0]) * r; X[sel, 2] += np.interp(f, i, dc[:, 1]) * r
    return X


def dress(orig, src, dst):
    pid = piece_id(src)
    b = body('C' if pid in POSE_C else 'B')
    S, fi = trimesh.sample.sample_surface_even(b, 400000, seed=1); SN = b.face_normals[fi]
    out = (np.abs(S[:, 0]) > ARM_X) & (S[:, 1] > .6); S, SN = S[~out], SN[~out]
    leg = {s: (S[:, 0] * s > -.005) | (S[:, 1] > CROTCH + .03) for s in (1, -1)}
    KD = {s: (cKDTree(S[leg[s]]), S[leg[s]], SN[leg[s]]) for s in (1, -1)}

    go = Garment(orig); Po = go.vertices(); Fo = go.mesh(Po).faces
    g = Garment(src); P1 = g.vertices(); F1 = g.mesh(P1).faces
    if len(Po) != len(P1) or len(Fo) != len(F1) or (Fo != F1).any():   # triangles removed after the original
        Po = Po[correspondence(go, g)]; Fo = F1
    Xo, inv, F = weld(Po, Fo); X0 = np.zeros_like(Xo); X0[inv] = P1
    mw = trimesh.Trimesh(Xo, F, process=False)
    E = mw.edges_unique; L = np.linalg.norm(Xo[E[:, 0]] - Xo[E[:, 1]], axis=1)
    def opposite(f, e):
        r = np.setdiff1d(F[f], e); return r[0] if len(r) else -1
    D = np.array([[opposite(a, e), opposite(c, e)] for (a, c), e in zip(mw.face_adjacency, mw.face_adjacency_edges)])
    uv = np.vstack(uvs(g))[F1]; plain = (uv == uv[:, :1]).all((1, 2))   # no print: the walls of separate_legs.py
    stiff = plain[mw.face_adjacency].any(1)[(D >= 0).all(1)]
    D = D[(D >= 0).all(1)]; LD = np.linalg.norm(Xo[D[:, 0]] - Xo[D[:, 1]], axis=1)
    Dd, LDd, D, LD = D[stiff], LD[stiff], D[~stiff], LD[~stiff]
    side = leg_side(Xo, F)
    X0 = center_cuffs(X0, side, b, CENTER_PIECES.get(pid, 1.))
    # nothing of the original's hip moves: where displacement_field.py lowered the hip, the band below TOP would pull it
    # back to the original's length and stretch it
    whole = TOP >= WHOLE_TOP
    if whole:
        # dressed whole, the waistband stays as in INPUT (already fitted by waist.py and waistband.py) and the cloth
        # starts below it: Tripo's waistband of 004 is 1 to 3 cm narrower than the body at the sides and back; dressed as
        # cloth it slid 3 cm down the small of the back and folded over, pushed out whole it stretches 38%, and held as
        # Tripo made it the body pokes through it 212 times (poke_through.py) instead of INPUT's 99
        sl, _, edge = waistband(Xo); top = edge[sl(Xo)] - WAISTBAND
    else:
        top = TOP
    w = np.clip((top - np.maximum(X0[:, 1], Xo[:, 1])) / LOOSE, 0, 1); movable = w > 0

    def collide(X):
        sd = np.zeros(len(X)); n = np.zeros_like(X); d = np.zeros(len(X))
        for s in (1, -1):
            k = side == s; kd, P, N = KD[s]; d[k], j = kd.query(X[k])
            sd[k] = np.einsum('ij,ij->i', X[k] - P[j], N[j]); n[k] = N[j]
        return sd, n, d

    sd0, _, _ = collide(X0); ceiling = np.maximum(sd0, FAR)
    # at TOP the fabric may stay where it was, like the held hip just above, and the gap grows to SLACK over LOOSE
    # below: pushed to SLACK right below a hip that goes into the body, it would fold into a pleat on the TOP line
    smooth = w * w * (3 - 2 * w); slack = smooth * SLACK + (1 - smooth) * np.minimum(sd0, SLACK)
    X = X0.copy()
    for _ in range(STEPS):
        for _ in range(ROUNDS):
            X += constrain(X, E, L, 1.6) * w[:, None]
            X += constrain(X, D, LD, BEND) * w[:, None]
            X += constrain(X, Dd, LDd, WALL_BEND) * w[:, None]
        sd, n, d = collide(X)
        inside = movable & (sd < slack) & (d < .06)
        X[inside] += ((slack[inside] - sd[inside]) * w[inside])[:, None] * n[inside]
        far = movable & (sd > ceiling) & (d < .10)
        X[far] -= ((sd[far] - ceiling[far]) * w[far])[:, None] * n[far]
    m, flipped = measures(Xo, X, F, ~plain, np.linalg.norm(X - X0, axis=1) > 1e-4, whole)
    sd, _, d = collide(X)
    print(f'{pid}: ' + ', '.join(f'{k} {100 * e:.1f}% (area {100 * a:.1f}%)' for k, (e, a) in m.items()) +
          f'; flipped {100 * flipped:.2f}% of the area; inside the body {int(((sd < -.003) & movable & (d < .06)).sum())} vertices')
    bad = [k for k in MAX if m[k][0] > MAX[k][0] or m[k][1] > MAX[k][1]] + (['flipped'] if flipped > MAX_FLIPPED else [])
    if bad: sys.exit(f'{src}: print distorts too much ({", ".join(bad)}); nothing written')
    g.save(dst, X[inv], before=P1)


if __name__ == '__main__':
    if sys.argv[1] == '--whole':
        # the whole piece below the waistband (WHOLE_PIECES: the cloth is wide enough for the neutral body, it only sat
        # inside it); more steps, or the band at the crotch stays pleated
        TOP, STEPS = WHOLE_TOP, WHOLE_STEPS
        dress(*sys.argv[2:5])
    else:
        dress(*sys.argv[1:4])
