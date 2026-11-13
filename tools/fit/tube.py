"""The loose part of a garment in few polygons: a tube of rings around the vertical axis, welded to the shell.

A shell (shell.py) follows the body, so a skirt would turn into shorts and a long hem would hug the hip. The tube
takes over where the cloth hangs:
- a skirt is ONE tube from the waistband line to the hem, and nothing of its shell is kept: the print is mapped once
  and no seam crosses the skirt. Down to SEAM its rings lie on the shell (every top was built outside that shell);
  below SEAM it hangs like a hem;
- a top with a long hem keeps its shell down to SEAM; below it the tube's top ring IS the shell's cut edge.
The tube's shape is read from the garment itself (Profile): rays from the tube's axis find the garment's outer face
at each angle and height, so each angle has the garment's own width and the garment's own hem. Where the garment
ends earlier at one angle than at the others, the tube ends there too; it never borrows the width of another angle
(a sleeve beside the hip, a frayed tip). At SEAM the tube has the shell's radius; the difference to the garment's
shrinks by TAPER down the tube, so the cloth hangs from the weld with no step and no kink. The tube is never smaller
than the body plus CLEAR and, for a top, never inside the set of all the bottoms plus RISE (a long hem passes
outside every bottom); body and bottoms are looked for at each side's own angle, and where they need room on one
side the ring first moves as a whole and only then widens, so its girth stays the garment's.
The texture is baked from the garment (shell.bake). Sleeves are left whole: sleeve or torso is told by the mesh's
connectivity, not by distance to the body (the hand rests against the hip).

What it did to the garment is measured on every tube and held by tube.json, one garment per line, values that only
go down (check):
- wider_cm / narrower_cm: how far the tube stands outside / inside the garment's own outer face (95th percentile);
- hem_girth_pct: perimeter of the tube's hem against the garment's at the same heights;
- seam_cm: within SEAM_BAND below SEAM, how far the tube's change of radius is from the garment's own (a kink);
- tear_cm, distortion: identity.py on the tube's print; texture_without_source_pct: texels that found no cloth.
usage: python3 tools/fit/tube.py DENSE_BODY.glb SHELL.glb GARMENT.glb SHELL_CUT_OUT.glb TUBE_OUT.glb RINGS [ENVELOPE.npy]
       python3 tools/fit/tube.py --check [WORK]    (WORK: a folder engine.py already built; without it, builds one)
       python3 tools/fit/tube.py --record WORK     (rewrites tube.json from WORK/report.json)"""
import sys, os, json, tempfile, numpy as np, trimesh
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from paths import GARMENTS, piece_id
import landmarks as L
import shell as S
import identity

SEAM = .90             # m: height of the weld between a top's shell and its tube
CLEAR = .006           # m: the tube is never closer than this to the body
ARM_GAP = .004         # m: the tube stays this far inside the arm
ARMPIT = 1.28          # m: below this height a sleeve is a part of the shell not connected to the middle of the torso
BLEND = .15            # m below SEAM over which a ring gains the freedom to move as a whole and the texture rays turn from the shell's to the tube's
TAPER = .15            # m per m: how fast the tube goes from the shell's radius at SEAM to the garment's (a cloth that hangs, no kink)
# Profile: the garment read from the tube's axis
ANGLES, ROW = 72, .01  # rays per turn; m between rows of rays
FLOOR = .40            # m: lowest row
TOP_GAP = .06          # m: the garment may start this far below the top ring (uneven waistband)
JUMP = .02             # m per row: a wall this far from the one right above is another cloth (sleeve, cord, fringe)
HOLE = .04             # m: a gap of the wall up to this height is a hole of the cloth, not its end
NOTCH = 3              # angles to each side: a notch of the hem narrower than this many is a rip
MIN_TUBE = .02         # m: shortest tube at any angle
SKIRT_SIDES = 30       # sides of a skirt's tube
WAIST_OVER = .05       # m over SEAM: a waistband's edge is above this
SKIRT_TOP_RINGS = 2    # rings of a skirt from the waistband down to SEAM
WAIST_RING = .03       # m under the waistband: the first of them
# check
SEAM_BAND = .06        # m below the weld where the kink is measured
RECORD = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tube.json')
TOLERANCE = {          # what a measure may sit above its recorded value before the check fails: every tube of a top
    'wider_cm': .25,   # moves a little when any bottom changes (it passes outside all of them)
    'narrower_cm': .25,
    'hem_girth_pct': 1.,
    'seam_cm': .25,
    'tear_cm': 25.,
    'distortion': .015,
    'texture_without_source_pct': 1.,
}


def sleeves(V, F):
    """Mask of the shell's vertices that belong to a sleeve."""
    _, inv = np.unique(np.round(V, 4), axis=0, return_inverse=True); inv = inv.ravel(); G = inv[F]
    G = G[(V[F][:, :, 1] < ARMPIT).all(1)]; n = inv.max() + 1
    e = np.vstack([G[:, [0, 1]], G[:, [1, 2]], G[:, [2, 0]]])
    _, comp = connected_components(coo_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(n, n)), directed=False)
    cv = comp[inv]; low = V[:, 1] < ARMPIT; out = np.zeros(len(V), bool)
    for c in np.unique(cv[low]):
        s = low & (cv == c)
        if s.sum() > 2 and np.abs(V[s, 0]).min() > .08: out |= s
    return out


def cut_shell(src, dst):
    """Keeps the shell above SEAM (sleeves whole) and returns the points of the cut edge and the shell's normals there."""
    m = trimesh.load(src, process=False).to_geometry(); V = np.asarray(m.vertices); F = np.asarray(m.faces)
    s = np.where(sleeves(V, F), 1.0, V[:, 1] - SEAM)
    P, F2, (N, UV) = S.cut(V, F, s, [np.asarray(m.vertex_normals), np.asarray(m.visual.uv)])
    u = np.unique(F2); r = -np.ones(len(P), int); r[u] = np.arange(len(u)); P, N, UV, F2 = P[u], N[u], UV[u], r[F2]
    S.export(dst, P, F2, N / (np.linalg.norm(N, axis=1)[:, None] + 1e-9), UV, m.visual.material.baseColorTexture)
    on = (np.abs(P[:, 1] - SEAM) < 2e-3) & ~sleeves(P, F2)
    edge, i = np.unique(np.round(P[on], 4), axis=0, return_index=True)
    return edge, N[on][i]


def waistband_edge(src):
    """A bottom shell's upper edge as a ring of SKIRT_SIDES of its own points: the waistband, with the curve and the
    corners the shell gave it. The points dropped are the ones that change the outline least (a ring at equal angles
    cuts the corners of the hip and the waist reads thinner)."""
    m = trimesh.load(src, process=False).to_geometry(); V = np.asarray(m.vertices)
    _, inv = np.unique(np.round(V, 4), axis=0, return_inverse=True); F = inv.ravel()[np.asarray(m.faces)]
    e = np.sort(np.vstack([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]]), axis=1); u, c = np.unique(e, axis=0, return_counts=True)
    P = np.zeros((inv.max() + 1, 3)); P[inv.ravel()] = V
    B = P[np.unique(u[c == 1])]; B = B[B[:, 1] > SEAM + WAIST_OVER]         # open edge at the top, not the rims of the legs
    cen = B[:, [0, 2]].mean(0); B = list(B[np.argsort(np.arctan2(B[:, 2] - cen[1], B[:, 0] - cen[0]))])
    while len(B) > SKIRT_SIDES:
        Q = np.array(B)[:, [0, 2]]; a, b = np.roll(Q, 1, 0) - Q, np.roll(Q, -1, 0) - Q
        B.pop(int(np.argmin(np.abs(a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0]))))
    while len(B) < SKIRT_SIDES:                             # a coarse shell: the longest side is split
        Q = np.array(B); i = int(np.argmax(np.linalg.norm(np.roll(Q, -1, 0) - Q, axis=1)))
        B.insert(i + 1, (Q[i] + Q[(i + 1) % len(Q)]) / 2)
    return np.array(B)


def around(a, t):
    """Angle from t to a, in -pi..pi."""
    return (a - t + np.pi) % (2 * np.pi) - np.pi


class Profile:
    """The garment's outer face as seen from a vertical axis: radius per angle and height, and where it ends."""
    def __init__(self, piece, cen, top):
        self.cen, self.top = cen, top
        self.ang = -np.pi + (np.arange(ANGLES) + .5) * 2 * np.pi / ANGLES; self.y = np.arange(top, FLOOR, -ROW)
        A, Y = np.meshgrid(self.ang, self.y)
        o = np.c_[np.full(A.size, cen[0]), Y.ravel(), np.full(A.size, cen[1])]; d = np.c_[np.cos(A.ravel()), np.zeros(A.size), np.sin(A.ravel())]
        loc, ir, _ = piece.ray.intersects_location(o, d, multiple_hits=True)
        t = np.hypot(loc[:, 0] - cen[0], loc[:, 2] - cen[1])
        first = np.full(A.size, np.inf); np.minimum.at(first, ir, t)
        same = t <= first[ir] + S.WALL                       # lining and outer face are one wall
        raw = np.full(A.size, -np.inf); np.maximum.at(raw, ir[same], t[same]); raw = np.where(np.isfinite(raw), raw, np.nan).reshape(A.shape)
        side = np.stack([np.roll(raw, -1, 1), np.roll(raw, 1, 1)]); alone = np.isnan(side).all(0)
        mid = np.sort(np.where(np.isnan(side), raw[None], side), axis=0)   # a stray hit between its neighbors is not the wall: median of the three
        raw = np.where(alone, raw, np.clip(raw, mid[0], mid[1]))
        rows, n = raw.shape; r = np.full(raw.shape, np.nan); end = np.zeros(n, int); found = np.zeros(n, bool)
        for a in range(n):
            last = None; at = 0
            for i in range(rows):
                v = raw[i, a]
                if last is None:
                    if self.top - self.y[i] > TOP_GAP: break
                    if not np.isnan(v): last, at = v, i; r[:i + 1, a] = v; found[a] = True
                    continue
                if (i - at) * ROW > HOLE: break
                if not np.isnan(v) and abs(v - last) < JUMP * (i - at): last, at = v, i
                r[i, a] = last
            r[at + 1:, a] = last if last is not None else np.nan; end[a] = at
        if not found.any(): raise SystemExit('tube: no cloth found from the axis below the top ring')
        idx = np.flatnonzero(found)                          # an angle without cloth at the top takes its neighbors'
        for row in r: row[~found] = np.interp(np.flatnonzero(~found), idx, row[idx], period=n)
        hem = self.y[end].astype(float); hem[~found] = np.interp(np.flatnonzero(~found), idx, hem[idx], period=n)
        hem = np.median([np.roll(hem, i) for i in range(-NOTCH, NOTCH + 1)], axis=0)   # a rip that reaches the hem is not the hem
        self.r = r; self.hem_y = np.convolve(np.r_[hem[-1], hem, hem[0]], [.25, .5, .25], mode='valid')

    def _angle(self, a):
        x = (np.asarray(a) - self.ang[0]) / (2 * np.pi / ANGLES); i = np.floor(x).astype(int)
        return i % ANGLES, (i + 1) % ANGLES, x - i

    def hem(self, a):
        i, j, f = self._angle(a)
        return np.minimum(self.hem_y[i] * (1 - f) + self.hem_y[j] * f, self.top - MIN_TUBE)

    def at(self, a, y):
        """Radius of the garment at angle a and height y; below the garment's end at that angle, its last radius."""
        i, j, f = self._angle(a); x = np.clip((self.top - np.asarray(y)) / ROW, 0, len(self.y) - 1); k = np.floor(x).astype(int); k2 = np.minimum(k + 1, len(self.y) - 1); g = x - k
        col = lambda c: self.r[k, c] * (1 - g) + self.r[k2, c] * g
        return col(i) * (1 - f) + col(j) * f


def polar(P, cen):
    return np.arctan2(P[:, 2] - cen[1], P[:, 0] - cen[0]), np.hypot(P[:, 0] - cen[0], P[:, 2] - cen[1]), P[:, 1]


def measure(prof, ang, r_seam, V):
    """How far the shape V (a tube's vertices) is, below SEAM, from the garment prof was read from. ang, r_seam: the
    tube's ring at SEAM."""
    a, r, y = polar(V, prof.cen); low = y < SEAM - 2e-3
    d = (r - prof.at(a, y))[low]
    r_top = np.interp(a, ang, r_seam, period=2 * np.pi)
    band = low & (y > SEAM - SEAM_BAND)
    kink = np.abs((r - r_top) - (prof.at(a, y) - prof.at(a, np.full(len(a), SEAM))))[band]
    a, r, y = a[low], r[low], y[low]
    # hem: the lowest vertices per angle
    bins = np.floor((a + np.pi) / (2 * np.pi) * 36).astype(int) % 36; hem = []
    for b in range(36):
        s = np.flatnonzero(bins == b)
        if len(s): hem.append(s[np.argmin(y[s])])
    hem = np.array(hem)[np.argsort(a[hem])]
    ring = lambda rr: np.c_[rr * np.cos(a[hem]), rr * np.sin(a[hem])]
    girth = lambda p: float(np.linalg.norm(p - np.roll(p, 1, 0), axis=1).sum())
    return {'wider_cm': round(100 * float(np.percentile(np.maximum(d, 0), 95)), 2), 'narrower_cm': round(100 * float(np.percentile(np.maximum(-d, 0), 95)), 2),
            'hem_girth_pct': round(100 * (girth(ring(r[hem])) / girth(ring(prof.at(a[hem], y[hem]))) - 1), 1),
            'seam_cm': round(100 * float(np.percentile(kink, 95)), 2) if band.any() else 0.0}


def build(dense_path, shell_path, garment_path, shell_out, tube_out, n, envelope=None):
    n = int(n); pid = piece_id(garment_path); skirt = pid in L.SKIRTS
    b = S.load_body(dense_path); BV = np.asarray(b.vertices); lab = L.limb(BV)
    arms = BV[(lab == 1) | (lab == 2)]; BV = BV[(lab != 1) & (lab != 2)]
    if skirt:                                             # one tube from the waistband down: no shell is kept
        edge = waistband_edge(shell_path); sm = trimesh.load(shell_path, process=False).to_geometry()
        if os.path.exists(shell_out): os.remove(shell_out)
    else: edge, weld = cut_shell(shell_path, shell_out)
    top = float(np.median(edge[:, 1]))
    cen = edge[:, [0, 2]].mean(0); ang = np.arctan2(edge[:, 2] - cen[1], edge[:, 0] - cen[0]); o = np.argsort(ang); edge, ang = edge[o], ang[o]
    if not skirt: weld = weld[o] / (np.linalg.norm(weld[o], axis=1)[:, None] + 1e-9)
    k = len(ang); u = np.c_[np.cos(ang), np.sin(ang)]
    piece = S.Piece(garment_path); prof = Profile(piece, cen, top)
    hem = np.minimum(prof.hem(ang), SEAM - MIN_TUBE)
    # heights: a skirt follows its shell down to SEAM (every top was built outside that shell), then hangs like a hem
    ys = [np.maximum(edge[:, 1] - WAIST_RING, SEAM + MIN_TUBE), np.full(k, SEAM)] if skirt else []   # one ring right under the waistband, where the waist is read, and one at SEAM
    ys = ys + [SEAM - (SEAM - hem) * j / n for j in range(1, n + 1)]
    if skirt:
        def on_shell(y):
            o3 = np.c_[np.full(k, cen[0]), y, np.full(k, cen[1])]; d3 = np.c_[u[:, 0], np.zeros(k), u[:, 1]]
            loc, ir, _ = sm.ray.intersects_location(o3, d3, multiple_hits=True); r = np.zeros(k)
            np.maximum.at(r, ir, np.hypot(loc[:, 0] - cen[0], loc[:, 2] - cen[1]))
            return np.where(r > 0, r, np.interp(np.arange(k), np.flatnonzero(r > 0), r[r > 0], period=k))
        r_seam = on_shell(np.full(k, SEAM))
    else: r_seam = np.hypot(edge[:, 0] - cen[0], edge[:, 2] - cen[1])
    off = r_seam - prof.at(ang, np.full(k, SEAM))
    ba, br, by = polar(BV, cen); aa, ar, ay = polar(arms, cen)
    if envelope is not None: ea, er, ey = polar(envelope, cen)
    rings = [edge]; span = np.gradient(np.unwrap(np.r_[ang, ang[0] + 2 * np.pi]))[:k]
    for j, y in enumerate(ys):
        if skirt and j < SKIRT_TOP_RINGS:
            r = on_shell(y); rings.append(np.c_[cen[0] + r * u[:, 0], y, cen[1] + r * u[:, 1]]); continue
        x = np.clip((SEAM - y) / BLEND, 0, 1); fade = x * x * (3 - 2 * x)
        r = prof.at(ang, y) + np.sign(off) * np.maximum(np.abs(off) - TAPER * (SEAM - y), 0)
        up = np.abs(ys[j - 1] - y) if j else SEAM - y; down = np.abs(ys[j + 1] - y) if j + 1 < len(ys) else np.zeros(k)
        floor = np.zeros(k); reach = np.full(k, np.inf)
        for i, t in enumerate(ang):
            s = (np.abs(around(aa, t)) < span[i]) & (ay > y[i] - down[i] / 2 - .01) & (ay < y[i] + up[i] / 2 + .01)
            if s.sum() >= 3: reach[i] = ar[s].min() - ARM_GAP               # the hem passes between the hip and the arm
            s = (np.abs(around(ba, t)) < span[i]) & (by > y[i] - down[i] - .01) & (by < y[i] + up[i] + .01)   # up to the rings above and below: the faces between them do not cut the body
            if s.any(): floor[i] = br[s].max() + CLEAR
            if envelope is not None:
                s = (np.abs(around(ea, t)) < span[i]) & (ey > y[i] - down[i] - .01) & (ey < y[i] + up[i] + .01)
                if s.sum() >= 3: floor[i] = max(floor[i], er[s].max() + S.RISE)
        # where the body (or a bottom) needs room on one side, the ring first moves as a whole, as cloth hanging from
        # the hip does, and only then widens: its girth stays the garment's
        move = (np.maximum(floor - r, 0) * span) @ u / np.pi
        r = np.maximum(np.minimum(r + (u @ move) * fade, reach), floor)
        rings.append(np.c_[cen[0] + r * u[:, 0], y, cen[1] + r * u[:, 1]])
    n = len(ys)
    V = np.vstack(rings); F = []
    for i in range(n):
        for j in range(k):
            p, q = i * k + j, i * k + (j + 1) % k; F += [(p, q, p + k), (q, q + k, p + k)]
    F = np.array(F)
    if trimesh.Trimesh(V, F, process=False).volume < 0: F = F[:, ::-1]
    N = np.asarray(trimesh.Trimesh(V, F, process=False).vertex_normals)
    if not skirt:                                        # at the weld the texture rays are the shell's own, so the print runs on across it; they turn to the tube's little by little
        x = np.clip((SEAM - V[:, 1]) / BLEND, 0, 1)[:, None]; N = np.tile(weld, (n + 1, 1)) * (1 - x) + N * x; N /= np.linalg.norm(N, axis=1)[:, None] + 1e-9
    base = V - N * .03                                   # the texture rays leave 3 cm inside the tube
    dense, _ = trimesh.sample.sample_surface(trimesh.Trimesh(base, F, process=False), 40000, seed=1)
    trace = {}
    V2, N2, UV, F2, img, missing = S.bake(piece, cKDTree(dense), dense, V, base, N, F, .10, limbs=False, trace=trace)
    S.export(tube_out, V2, F2, N2, UV, img)
    ident = identity.measure(trace, piece, S.Piece(GARMENTS + f'{pid}.glb'))
    return {'triangles': int(len(F2)), 'sides': k, 'rings': n, 'top': round(top, 3), 'hem': [round(float(hem.min()), 2), round(float(hem.max()), 2)],
            'texture_without_source_pct': round(100 * missing, 1), **measure(prof, ang, r_seam, V), 'tear_cm': ident['tear_cm'], 'distortion': round(abs(ident['distortion'] - 1), 3)}


def recorded():
    return json.load(open(RECORD))


def check(report):
    """Compares the tubes of an engine report with tube.json; returns the list of failures (engine.py --check calls it)."""
    rep = report['garments']; base = recorded(); bad = []
    built = {p for p, g in rep.items() if 'tube' in g}
    if len(rep) == 38 and built != set(base): bad.append(f'tubes built {sorted(built)} differ from the recorded {sorted(base)}')
    for p in sorted(built & set(base)):
        for key, tol in TOLERANCE.items():
            if rep[p]['tube'][key] > base[p][key] + tol: bad.append(f"{p} {key} {rep[p]['tube'][key]} > recorded {base[p][key]}")
    return bad


def record(report):
    """Rewrites tube.json, one garment per line; a recorded value only goes down."""
    rep = report['garments']; new = {p: {key: g['tube'][key] for key in TOLERANCE} for p, g in sorted(rep.items()) if 'tube' in g}
    old = recorded() if os.path.exists(RECORD) else {}
    up = [f'{p} {key}: {old[p][key]} -> {v}' for p, g in new.items() for key, v in g.items() if key in old.get(p, {}) and v > old[p][key] + TOLERANCE[key]]
    if up: raise SystemExit('a baseline only goes down:\n' + '\n'.join(up))
    new = {p: {key: min(v, old.get(p, {}).get(key, v)) for key, v in g.items()} for p, g in new.items()}   # inside the slack the recorded value stays
    open(RECORD, 'w').write('{\n' + ',\n'.join(f' "{p}": {json.dumps(g)}' for p, g in new.items()) + '\n}\n')


if __name__ == '__main__':
    a = sys.argv[1:]
    if a and a[0] in ('--check', '--record'):
        if len(a) > 1: rep = json.load(open(f'{a[1]}/report.json'))
        else:
            import engine
            rep = engine.run(tempfile.mkdtemp(), [f'{i:03d}' for i in range(1, 39)])
        if a[0] == '--record': record(rep); sys.exit(0)
        bad = check(rep)
        print('\n'.join(bad) if bad else 'tubes within the recorded values')
        sys.exit(1 if bad else 0)
    print(build(*a[:6], envelope=np.load(a[6]) if len(a) > 6 else None))
