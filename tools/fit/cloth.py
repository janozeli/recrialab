"""Brings long sleeves onto the body's arm as cloth, after the bone pose of repose_sleeves.py.

repose_sleeves.py puts the sleeve on the arm bone by bone, but it knows nothing of the body nor of the garment's own
layers. On an oversized sleeve (034) that leaves two defects: the fold under the armpit, which moves with the arm,
passes through the back panel, which does not (seen from behind, a hole showing the inside of the garment); and the
elastic cuff, as narrow as the neutral body's wrist (16.4 cm of opening around a 16.3 cm wrist), shows the hand going
through its cloth from below. Here the garment is cloth (Newton's VBD solver: stretch, bending, gravity, the body as
collider), in two passes:
  1. the armhole: the arm moves from where the generator left it to the pose, frame by frame, with the band between
     the torso and the arm loose and colliding with itself, so the fold stays in front of the back panel;
  2. the forearm: from the pose, the sleeve below the elbow settles around the wrist and the hand.
The garment takes the armhole from the first and the rest from the second.
The hem below the cuff keeps the place it had (the pose turns it with the forearm and slides it behind the bottoms).
The rest shape is the garment as the generator made it, so the cloth only stretches as far as the pose and the
collision make it. Only positions change; UV and texture stay.
Refuses (writes nothing) if the cloth stretches past MAX_STRETCH (p99 of the edges that move, as repose_sleeves.py),
a triangle flips, a vertex of the sleeve stays inside the hand, the cuff ends farther than MAX_CUFF from the hand, or
more of the inside of the garment shows from behind below the neck than before (MAX_BACK_INSIDE).
It runs repose_sleeves.py itself (the start is its input); then hood.py and install.py, as after repose_sleeves.py.
usage: python3 tools/fit/cloth.py in.glb out.glb   (in: the GLB repose_sleeves.py would take)"""
import sys, numpy as np
import warp as wp, newton
from scipy.spatial import cKDTree
from trimesh.ray.ray_pyembree import RayMeshIntersector
from back_inside import back_inside
from garment import Garment, kernel
from metric import body
from repose_sleeves import check, cuff_to_hand, dress, sleeve_end, MAX_CUFF, MAX_STRETCH

ELBOW = 1.02           # pass 2: the cloth is free below this height, fading in over FADE
FADE = .06
NEAR = .08             # and only near the arm (the hem of an oversized jacket beside the hip stays)
ARMHOLE = (.10, .26, 1.0, 1.5)   # pass 1: free band |x| from, |x| to, y from, y to
ARMHOLE_EDGE_KE = 20.  # pass 1 bends stiffer: the band folds around the armpit instead of creasing
ANIMATE = 40           # pass 1: frames from the generator's place to the pose
FRAMES, SUBSTEPS, ITERATIONS = 40, 10, 10   # frames of 1/60 s that each pass settles
TRI_KE, EDGE_KE, DENSITY, RADIUS = 1e5, 1., .2, .003   # stiff in plane, bending stiff enough not to fold the cuff
CONTACT_KE, CONTACT_KD, MU = 1e4, 1e-2, .3
SELF_RADIUS, SELF_MARGIN = .002, .004
HAND = .9              # below this the arm is wrist and hand, which the masks never hide
HEM_NEAR, HEM_RAMP = .04, .08   # hem: beyond HEM_NEAR from the arm, back to its place over HEM_RAMP below the cuff
MAX_BACK_INSIDE = .5   # cm² of inside seen from behind (back_inside.py) more than before


def inside(b, Q):
    """Points inside the body: odd number of crossings both forward and backward (the body is not watertight)."""
    ri = RayMeshIntersector(b)
    def odd(d):
        _, idx, _ = ri.intersects_location(Q, np.tile(d, (len(Q), 1)), multiple_hits=True)
        return np.bincount(idx, minlength=len(Q)) % 2 == 1
    return odd([0, 0, 1.]) & odd([0, 0, -1.])


def simulate(X0, start, target, F, b, free, animate, edge_ke, self_contact):
    """X0 rest shape, start and target positions (welded vertices); the vertices that are not free go from start to
    target over `animate` frames and the free ones follow as cloth, then settle FRAMES more."""
    wp.config.quiet = True
    builder = newton.ModelBuilder(up_axis=newton.Axis.Y)
    builder.add_cloth_mesh(pos=wp.vec3(0, 0, 0), rot=wp.quat_identity(), scale=1., vel=wp.vec3(0, 0, 0),
                           vertices=[wp.vec3(*v) for v in X0], indices=F.ravel().tolist(), density=DENSITY,
                           tri_ke=TRI_KE, tri_ka=TRI_KE, tri_kd=1e-5, edge_ke=edge_ke, edge_kd=0., particle_radius=RADIUS)
    B = b.vertices
    builder.add_shape_mesh(body=-1, mesh=newton.Mesh(B.astype(np.float32), b.faces.ravel().astype(np.int32)))
    builder.color(include_bending=True)
    model = builder.finalize()
    model.soft_contact_ke, model.soft_contact_kd, model.soft_contact_mu = CONTACT_KE, CONTACT_KD, MU
    model.set_gravity((0., -9.81, 0.))
    flags = model.particle_flags.numpy(); flags[~free] &= ~newton.ParticleFlags.ACTIVE; model.particle_flags = wp.array(flags)
    extra = dict(particle_enable_self_contact=True, particle_self_contact_radius=SELF_RADIUS,
                 particle_self_contact_margin=SELF_MARGIN, particle_rest_shape_contact_exclusion_radius=.01) if self_contact else {}
    solver = newton.solvers.SolverVBD(model, iterations=ITERATIONS, **extra)
    s0, s1, control = model.state(), model.state(), model.control()
    s0.particle_q.assign(start.astype(np.float32)); s1.particle_q.assign(start.astype(np.float32))
    pipeline = newton.CollisionPipeline(model); contacts = pipeline.contacts()
    for f in range(animate + FRAMES):
        driven = (start + min(1., (f + 1) / animate) * (target - start) if animate else target)[~free]
        def drive(s):
            q = s.particle_q.numpy(); q[~free] = driven; s.particle_q.assign(q.astype(np.float32))
        drive(s0)
        pipeline.collide(s0, contacts)
        for _ in range(SUBSTEPS):
            s0.clear_forces(); solver.step(s0, s1, control, contacts, 1 / 60 / SUBSTEPS); s0, s1 = s1, s0
            if animate: drive(s0)
    return s0.particle_q.numpy().astype(float)


if __name__ == '__main__':
    src, dst = sys.argv[1:3]
    b = body('B'); B = b.vertices
    arm = cKDTree(B[np.abs(B[:, 0]) > .17])
    g = Garment(src); P0 = g.vertices(); m = g.mesh(P0)
    _, inv = np.unique(np.round(P0, 5), axis=0, return_inverse=True); inv = inv.ravel()
    X0 = np.zeros((inv.max() + 1, 3)); X0[inv] = P0
    F = inv[m.faces]; F = F[(F[:, 0] != F[:, 1]) & (F[:, 1] != F[:, 2]) & (F[:, 0] != F[:, 2])]
    P1 = dress(P0, m.faces, B); X1 = np.zeros_like(X0); X1[inv] = P1
    K = kernel(X0, .02)
    # pass 1: the armhole, from the generator's place to the pose
    x0, x1, y0, y1 = ARMHOLE
    band = ((np.abs(X0[:, 0]) > x0) & (np.abs(X0[:, 0]) < x1) & (X0[:, 1] > y0) & (X0[:, 1] < y1)).astype(float)
    free = K @ band > .5
    X2 = simulate(X0, X0, X1, F, b, free, ANIMATE, ARMHOLE_EDGE_KE, True)
    # pass 2: the forearm settles around the wrist and the hand, from the pose
    free = np.clip((ELBOW - X1[:, 1]) / FADE, 0, 1) * np.clip((np.abs(X1[:, 0]) - .17) / .03, 0, 1)
    free = K @ (free * (arm.query(X1)[0] < NEAR)) > .5
    X3 = simulate(X0, X1, X1, F, b, free, 0, EDGE_KE, False)
    # the armhole from pass 1, the rest from pass 2
    w = np.clip(kernel(X0, .03) @ ((np.abs(X0[:, 0]) > x0) & (X0[:, 1] > y0)), 0, 1)
    X3 = X3 + w[:, None] * (X2 - X3)
    # the hem below the cuff, away from the arm, back to its place
    W = np.ones(len(X0))
    for s in (1, -1):
        h = s * X0[:, 0] > 0
        W[h] = np.clip((X0[h, 1] - (sleeve_end(X3[inv], B, s) - HEM_RAMP)) / HEM_RAMP, 0, 1)
    W = np.clip(kernel(X0, .015) @ np.maximum(W, arm.query(X3)[0] < HEM_NEAR), 0, 1)
    P = (X0 + W[:, None] * (X3 - X0))[inv]
    p95, p99, flipped = check(m, P0, P)
    cuff = max(cuff_to_hand(P, B, s) for s in (1, -1))
    hand = int(inside(b, P[(np.abs(P[:, 0]) > .19) & (P[:, 1] < HAND)]).sum())
    back, back0 = back_inside(m, P), back_inside(m, P0)
    print('%s: stretch p95 %.1f%% p99 %.1f%%; flipped %d; cuff to hand %.1f cm; %d vertices inside the hand; '
          'inside seen from behind %.1f cm² (before %.1f)' % (
        src.split('/')[-1], 100 * p95, 100 * p99, flipped, 100 * cuff, hand, back, back0))
    if p99 > MAX_STRETCH or flipped or cuff > MAX_CUFF or hand or back > back0 + MAX_BACK_INSIDE:
        sys.exit(f'{src}: the cloth does not settle within the limits; nothing written')
    g.save(dst, P, before=P0)
