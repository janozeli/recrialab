"""Builds a top from a shape Tripo generated on the neutral mannequin, painted from the views it was generated from.

The tops Tripo made from the shop photos came shaped on its own mannequin: on the neutral body the collar stood off the
nape and the shoulders sank, and the fixes that moved the cloth afterwards (hood.py, drape.py) stretched the print.
Here the shape comes from three views of the top dressed on renders of pose B (front, left, back: image-to-image), then
multiview-to-model without texture, the recipe of project_print.py:
  1. align: height, turn about y and ICP on the head and legs, which stay bare (they are the mannequin itself);
  2. remove the mannequin: skin is what lies close to the body (SKIN, NECK_SKIN on the neck and hip) connected to a
     bare end: the head, the feet, the hands. An arm is skin when it is closer to the arm than to the torso by ARM_GAP
     and does not face the arm (the side of the top hangs beside the arm and faces it). Below the sleeve (FOREARM) the
     arm goes whole. What dips into the body elsewhere is cloth (the generated shoulder is lower than the body's): it
     stays and push_out moves it out;
  3. shape: smooth the relief the generator made of the print (the number and a panel around it stood out as plates:
     SMOOTH rounds of Taubin), bring the front back to CHEST off the chest (it came 3.9 cm out, a box), and take the
     hem out over the 15 bottoms by SLACK (the hip was tight to the body and the jeans' hip poked through at the sides);
     then push out, simplify, smooth the sleeves' ends, push out, drop crumbs, close the small holes the arm's cut
     left and bring the lining below the front hem forward to the front (lining.py's computation; removing it opened a
     hole above the hem);
  4. print: UV unwrap (xatlas) and each texel takes the colour of the generated view that sees it most head-on with
     nothing in front (the top itself or the body's arm), above MIN_FACING; the right side, which no view shows, takes
     the left view mirrored. The views are what the shape was generated from, so print and shape agree. The camera is
     the one of the mannequin renders (fov 20°, framing the body, 1024 x 1536) with a 2D fit per view (VIEWS: scale and
     offset matching the outline of the generated shape, IoU 0.90 to 0.95). A pixel on the white background (connected
     to the image border) is left to another view; what no view sees takes the print source's colour along the normal.
usage: python3 tools/fit/project_top.py NNN SHAPE.glb VIEWS_DIR PRINT_SOURCE.glb OUT.glb
       (030: SHAPE = reference/originals/tripo-shape/030.glb, VIEWS_DIR = reference/originals/tripo-views/030,
        PRINT_SOURCE = reference/originals/print-source/030.glb)"""
import sys, numpy as np, trimesh
from PIL import Image
from scipy import ndimage
from scipy.spatial import cKDTree
from trimesh.ray.ray_pyembree import RayMeshIntersector
import project_print as pp
from garment import Garment
from metric import body
from paths import GARMENTS

W, H = 1024, 1536   # the mannequin renders the views were made on
# per piece: view, camera turn (degrees), 2D fit (x scale, y scale, x offset, y offset in pixels)
VIEWS = {
    '030': (('front', 0, (0.949, 1.008, 25.622, -6.504)), ('left', -90, (0.944, 1.01, 29.313, -5.565)),
            ('back', 180, (0.998, 1.011, 1.526, -14.578))),
}
MIN_FACING = .15    # a view this close to edge-on does not paint
BACKGROUND = 246    # the views' white background: every channel at least this
SLACK, BOTTOMS_Y = .006, (1.0, 1.1)   # hem this far out of the bottoms; full below the first height, none above the second
CHEST, SHOULDER = .012, (1.34, 1.46)  # gap to the chest; the front moves back fully below the first height, not above the second
SMOOTH = 30
SKIN, NECK_SKIN = .02, .011           # the generated mannequin sits ~0.7 cm off the body
NECK, HEM, SLEEVE, TORSO_X = 1.42, .88, 1.28, .17
ARM_GAP = .012
HIP, FOREARM = 1.05, 1.21             # the hip under the hem goes with the tight skin; below the sleeve (>= 1.22) the arm goes whole
FOREARM_SKIN = .04                    # below the sleeve the generated forearm stands up to 2.8 cm off the body's (030's left)


def align(m, B):
    v = m.vertices.copy()
    v = (v - [0, v[:, 1].min(), 0]) * (B.vertices[:, 1].max() / np.ptp(v[:, 1]))
    v[:, [0, 2]] -= v[:, [0, 2]].mean(0) - B.vertices[:, [0, 2]].mean(0)
    bare = lambda P: (P[:, 1] > 1.62) | (P[:, 1] < .75)
    target = B.vertices[bare(B.vertices)]; tree = cKDTree(target); c = B.vertices[:, [0, 2]].mean(0)
    best = None
    for k in range(4):
        R = trimesh.transformations.rotation_matrix(k * np.pi / 2, [0, 1, 0])
        w = v.copy(); w[:, [0, 2]] -= c; w = (np.c_[w, np.ones(len(w))] @ R.T)[:, :3]; w[:, [0, 2]] += c
        d = tree.query(w[bare(w)])[0].mean()
        if best is None or d < best[0]: best = (d, w)
    v = best[1]
    M, _, _ = trimesh.registration.icp(v[bare(v)], target, max_iterations=80, scale=True, reflection=False)
    return trimesh.Trimesh((np.c_[v, np.ones(len(v))] @ M.T)[:, :3], m.faces, process=False)


def flood(m, candidate, seed):
    """Candidate faces connected (by edges, through candidates only) to a seed face."""
    a = m.face_adjacency; a = a[candidate[a[:, 0]] & candidate[a[:, 1]]]
    g = trimesh.graph.nx.Graph(); g.add_nodes_from(np.flatnonzero(candidate)); g.add_edges_from(a)
    out = np.zeros(len(m.faces), bool)
    for comp in trimesh.graph.nx.connected_components(g):
        comp = np.fromiter(comp, int)
        if seed[comp].any(): out[comp] = True
    return out


def without_mannequin(m, B):
    c = m.triangles_center
    q, d, _ = trimesh.proximity.closest_point(B, c)
    outside = trimesh.proximity.signed_distance(B, c) < 0
    _, dt, _ = trimesh.proximity.closest_point(pp.without_arms(B), c)
    faces_arm = outside & (np.einsum('ij,ij->i', m.face_normals, q - c) > 0) & (d > .003)
    arm = (np.abs(q[:, 0]) > TORSO_X) & (d < dt - ARM_GAP) & ~faces_arm
    head = flood(m, (d < NECK_SKIN) & (q[:, 1] > NECK), c[:, 1] > 1.68)
    legs = flood(m, (d < SKIN) & (c[:, 1] < HEM) | (d < NECK_SKIN) & (c[:, 1] < HIP), c[:, 1] < .1)
    hands = arm & (q[:, 1] < FOREARM) & (d < FOREARM_SKIN) | flood(m, (d < SKIN) & arm & (q[:, 1] < SLEEVE), arm & (q[:, 1] < .85))
    return pp.keep(m, ~(head | legs | hands))


def chest(m, B):
    V = m.vertices.copy()
    band = lambda P: (np.abs(P[:, 0]) < .04) & (P[:, 1] > 1.2) & (P[:, 1] < 1.3)
    body_front, front = B.vertices[band(B.vertices), 2].max(), V[band(V), 2].max()
    z0 = B.vertices[:, 2].mean()
    w = pp.smooth((V[:, 2] - z0) / (front - z0)) * pp.smooth((SHOULDER[1] - V[:, 1]) / (SHOULDER[1] - SHOULDER[0])) \
        * pp.smooth((.22 - np.abs(V[:, 0])) / .04)
    V[:, 2] -= (front - body_front - CHEST) * w
    return trimesh.Trimesh(V, m.faces, process=False)


def over_bottoms(m, B):
    """Per slice of 1 cm and 5° around the body's axis, the whole slice of the top moves out by what its outermost layer
    lacks to stand SLACK past the largest radius of the 15 bottoms (moving each vertex to that radius put the hem's inner
    fold over the outer cloth, and its inside showed from behind); the move is smoothed over the slices."""
    zc = B.vertices[:, 2].mean()
    row = lambda y: np.clip(((y - .80) / .01).astype(int), 0, 39)
    col = lambda x, z: (((np.degrees(np.arctan2(x, z - zc)) % 360) / 5).astype(int)) % 72
    def outer(P):
        P = P[(P[:, 1] > .80) & (P[:, 1] < BOTTOMS_Y[1] + .02) & (np.abs(P[:, 0]) < .2)]
        R = np.zeros((40, 72)); np.maximum.at(R, (row(P[:, 1]), col(P[:, 0], P[:, 2])), np.hypot(P[:, 0], P[:, 2] - zc))
        return R
    bottoms = ndimage.maximum_filter(outer(np.vstack([Garment(GARMENTS + f'{i:03d}.glb').mesh().vertices
                                                      for i in range(1, 16)])), size=(3, 3), mode=('nearest', 'wrap'))
    top = outer(m.vertices)
    lack = np.where(top > 0, np.maximum(bottoms + SLACK - top, 0), 0)
    lack = ndimage.grey_dilation(lack, size=(3, 3), mode=('nearest', 'wrap'))
    lack = ndimage.gaussian_filter(lack, (1.5, 1.5), mode=('nearest', 'wrap'))
    V = m.vertices.copy(); r = np.hypot(V[:, 0], V[:, 2] - zc)
    out = lack[row(V[:, 1]), col(V[:, 0], V[:, 2])] * pp.smooth((BOTTOMS_Y[1] - V[:, 1]) / (BOTTOMS_Y[1] - BOTTOMS_Y[0]))
    k = r > 1e-6
    V[k, 0] += V[k, 0] / r[k] * out[k]; V[k, 2] += (V[k, 2] - zc) / r[k] * out[k]
    return trimesh.Trimesh(V, m.faces, process=False)


def smooth_cuffs(m, rounds=10):
    """The cut of the arm (per face) leaves the sleeve's end jagged: the boundary loops of the sleeves (beyond TORSO_X)
    are smoothed along themselves."""
    w = trimesh.Trimesh(m.vertices, m.faces); w.merge_vertices()
    e = w.edges[trimesh.grouping.group_rows(w.edges_sorted, require_count=1)]
    g = trimesh.graph.nx.Graph(); g.add_edges_from(e)
    V = w.vertices.copy()
    for comp in trimesh.graph.nx.connected_components(g):
        loop = max(trimesh.graph.nx.cycle_basis(g.subgraph(comp)) or [[]], key=len)
        if len(loop) < 3 or np.abs(V[loop, 0].mean()) < TORSO_X: continue
        for _ in range(rounds): V[loop] = (np.roll(V[loop], 1, 0) + 2 * V[loop] + np.roll(V[loop], -1, 0)) / 4
    return trimesh.Trimesh(V, w.faces, process=False)


def close_small(m, limit=.3):
    """Fills each boundary loop shorter than LIMIT (the cut of the arm left a few beside it) with a fan from its centre;
    the collar, the hem and the sleeves are longer."""
    w = trimesh.Trimesh(m.vertices, m.faces); w.merge_vertices()
    e = w.edges[trimesh.grouping.group_rows(w.edges_sorted, require_count=1)]
    g = trimesh.graph.nx.Graph(); g.add_edges_from(e)
    V, F = list(w.vertices), list(w.faces)
    for comp in trimesh.graph.nx.connected_components(g):
        comp = np.fromiter(comp, int); ee = e[np.isin(e[:, 0], comp)]
        if np.linalg.norm(w.vertices[ee[:, 0]] - w.vertices[ee[:, 1]], axis=1).sum() > limit: continue
        c = len(V); V.append(w.vertices[comp].mean(0))
        for a, b in ee: F.append([b, a, c])
    return trimesh.Trimesh(np.array(V), np.array(F), process=False)


def lining_below_hem(V, F):
    """Faces of the lining below the front hem (the computation of lining.py, which does not read this layout), and the
    front of their column."""
    from lining import SHELL, LINING, WINDOW
    c = V[F].mean(1); out = np.zeros(len(c), bool); front = np.zeros(len(c))
    for x0 in np.arange(-.17, .171, .01):
        col = (np.abs(c[:, 0] - x0) < .005) & (c[:, 2] > 0) & (c[:, 1] > .5) & (c[:, 1] < 1.2)
        if col.sum() < 5: continue
        win = col & (c[:, 1] < c[col, 1].min() + WINDOW)
        zf = c[win, 2].max(); hem = c[win & (c[:, 2] > zf - SHELL), 1].min()
        k = col & (c[:, 1] < hem) & (c[:, 2] < zf - LINING); out |= k; front[k] = zf
    return out, front


def lining_out(m):
    """The lining below the front hem comes forward to the front of its column. It is the fold of the hem itself, joined
    to the shell: removing it left a hole above the hem, with the inside showing (030)."""
    from lining import SHELL
    V = m.vertices.copy()
    for _ in range(4):
        bad, front = lining_below_hem(V, m.faces)
        if not bad.any(): break
        for f in np.flatnonzero(bad): V[m.faces[f], 2] = np.maximum(V[m.faces[f], 2], front[f] - SHELL / 2)
    assert not lining_below_hem(V, m.faces)[0].any()
    return trimesh.Trimesh(V, m.faces, process=False)


def project(P, yaw, fit, B):
    lo, hi = B.bounds; c = (lo + hi) / 2; dist = (hi - lo)[1] / 2 / np.tan(np.radians(10)) * 1.08
    y = np.radians(yaw); eye = c + np.array([np.sin(y) * dist, 0, np.cos(y) * dist])
    f = (c - eye) / np.linalg.norm(c - eye); r = np.cross(f, [0, 1, 0]); r /= np.linalg.norm(r); u = np.cross(r, f)
    d = P - eye; z = d @ f; t = np.tan(np.radians(10))
    px = np.c_[((d @ r) / (z * t * W / H) + 1) / 2 * W, (1 - (d @ u) / (z * t)) / 2 * H]
    return px * fit[:2] + fit[2:], eye


def background(im):
    """The white connected to the image border, grown by 2 px (a white collar is not background)."""
    lab, _ = ndimage.label(im.min(2) >= BACKGROUND)
    edge = np.unique(np.r_[lab[0], lab[-1], lab[:, 0], lab[:, -1]]); edge = edge[edge > 0]
    return ndimage.binary_dilation(np.isin(lab, edge), iterations=2)


def along_normal(old, uv, img, P, n):
    ri = RayMeshIntersector(old)
    tri = np.full(len(P), -1); hit = P.copy(); best = np.full(len(P), np.inf)
    for s in (1, -1):
        loc, ir, it = ri.intersects_location(P, n * s, multiple_hits=False)
        d = np.linalg.norm(loc - P[ir], axis=1); ok = (d < .06) & (d < best[ir])
        tri[ir[ok]] = it[ok]; hit[ir[ok]] = loc[ok]; best[ir[ok]] = d[ok]
    miss = tri < 0
    if miss.any():
        q, _, t = trimesh.proximity.closest_point(old, P[miss]); hit[miss] = q; tri[miss] = t
    bc = trimesh.triangles.points_to_barycentric(old.triangles[tri], hit)
    return pp.bilinear(img, np.einsum('ij,ijk->ik', bc, uv[old.faces[tri]]))


def from_views(pid, views_dir, B):
    def sample(old, uv, img, P, new, striped=True):
        _, _, t = trimesh.proximity.closest_point(new, P); n = new.face_normals[t]
        blocker = RayMeshIntersector(trimesh.util.concatenate([new, B]))
        colour = np.zeros((len(P), 3)); best = np.full(len(P), MIN_FACING)
        views = VIEWS[pid] + tuple((name, -yaw, fit) for name, yaw, fit in VIEWS[pid] if name == 'left')
        for name, yaw, fit in views:
            im = np.array(Image.open(f'{views_dir}/{name}.png').convert('RGB')); bg = background(im)
            px, eye = project(P, yaw, np.array(fit), B)
            if name == 'left' and yaw > 0: px, _ = project(P * [-1, 1, 1], -yaw, np.array(fit), B)   # mirrored
            to = eye - P; to /= np.linalg.norm(to, axis=1)[:, None]
            w = np.einsum('ij,ij->i', n, to)
            k = np.flatnonzero(w > best)
            _, ir, _ = blocker.intersects_location(P[k] + to[k] * .002, to[k], multiple_hits=False)
            free = np.ones(len(k), bool); free[ir] = False; k = k[free]
            h, w_ = bg.shape
            cloth = ~bg[np.clip((px[k, 1] / H * h).astype(int), 0, h - 1), np.clip((px[k, 0] / W * w_).astype(int), 0, w_ - 1)]
            k = k[cloth]
            colour[k] = pp.bilinear(im, px[k] / [W, H]); best[k] = w[k]
        unseen = best <= MIN_FACING
        if unseen.any(): colour[unseen] = along_normal(old, uv, img, P[unseen], n[unseen])
        print(f'{unseen.mean() * 100:.1f}% of the texels seen by no view (most inside the top)')
        return colour
    return sample


def main(pid, shape, views_dir, source, out):
    B = body('B')
    m = without_mannequin(align(pp.load(shape), B), B)
    trimesh.smoothing.filter_taubin(m, iterations=SMOOTH)
    m = over_bottoms(chest(m, B), B)
    m = pp.drop_crumbs(pp.push_out(smooth_cuffs(pp.simplify(pp.push_out(m, B), pp.FACES)), B, rounds=3))
    m = lining_out(close_small(m))
    old, uv, img = pp.print_source(source)
    pp.sample = from_views(pid, views_dir, B)
    V, F, UV, image = pp.bake(m, old, uv, img)
    pp.save(out, V, F, UV, image)
    print(f'{out}: {len(F)} triangles, hem {V[:, 1].min():.3f} m, top {V[:, 1].max():.3f} m')


if __name__ == '__main__':
    main(*sys.argv[1:6])
