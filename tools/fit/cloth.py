"""Settles the forearm of long sleeves as cloth around the body's arm and hand, after repose_sleeves.py.

repose_sleeves.py puts the sleeve on the arm bone by bone, but it knows nothing of the body: the cuff that the pose
centers on the hand can cross the wrist. An elastic cuff as narrow as the neutral body's wrist (034: 16.4 cm of
opening around a 16.3 cm wrist) then shows the hand going through its cloth from below. Here the sleeve below the
elbow is cloth (Newton's VBD solver: stretch, bending, gravity) with the body as collider, and the rest of the
garment stays where it is; the rest shape is the garment as the generator made it, so the cloth only stretches as
far as the collision makes it. Only positions change; UV and texture stay.
Refuses (writes nothing) if the cloth stretches past MAX_STRETCH (p99 of the edges that move, as repose_sleeves.py),
a triangle flips, a vertex of the sleeve stays inside the hand or the cuff ends farther than MAX_CUFF from the hand.
It runs repose_sleeves.py itself (the rest shape is its input), for the pieces whose cuff crosses the wrist after it;
then hood.py and install.py, as after repose_sleeves.py.
usage: python3 tools/fit/cloth.py in.glb out.glb   (in: the GLB repose_sleeves.py would take)"""
import sys, numpy as np, trimesh
import warp as wp, newton
from scipy.spatial import cKDTree
from trimesh.ray.ray_pyembree import RayMeshIntersector
from garment import Garment, kernel
from metric import body
from repose_sleeves import check, cuff_to_hand, dress, MAX_CUFF, MAX_STRETCH

ELBOW = 1.02           # the cloth is free below this height, fading in over FADE
FADE = .06
NEAR = .08             # and only near the arm (the hem of an oversized jacket beside the hip stays)
FRAMES, SUBSTEPS, ITERATIONS = 40, 10, 10   # 40 frames of 1/60 s
TRI_KE, EDGE_KE, DENSITY, RADIUS = 1e5, 1., .2, .003   # stiff in plane, bending stiff enough not to fold the cuff
CONTACT_KE, CONTACT_KD, MU = 1e4, 1e-2, .3
HAND = .9              # below this the arm is wrist and hand, which the masks never hide


def inside(b, Q):
    """Points inside the body: odd number of crossings both forward and backward (the body is not watertight)."""
    ri = RayMeshIntersector(b)
    def odd(d):
        _, idx, _ = ri.intersects_location(Q, np.tile(d, (len(Q), 1)), multiple_hits=True)
        return np.bincount(idx, minlength=len(Q)) % 2 == 1
    return odd([0, 0, 1.]) & odd([0, 0, -1.])


def settle(X0, X1, F, b):
    """X0 rest shape, X1 start (welded vertices); returns the positions after the cloth settles."""
    B = b.vertices
    free = np.clip((ELBOW - X1[:, 1]) / FADE, 0, 1) * np.clip((np.abs(X1[:, 0]) - .17) / .03, 0, 1)
    free *= cKDTree(B[np.abs(B[:, 0]) > .17]).query(X1)[0] < NEAR
    free = kernel(X1, .02) @ free > .5
    wp.config.quiet = True
    builder = newton.ModelBuilder(up_axis=newton.Axis.Y)
    builder.add_cloth_mesh(pos=wp.vec3(0, 0, 0), rot=wp.quat_identity(), scale=1., vel=wp.vec3(0, 0, 0),
                           vertices=[wp.vec3(*v) for v in X0], indices=F.ravel().tolist(), density=DENSITY,
                           tri_ke=TRI_KE, tri_ka=TRI_KE, tri_kd=1e-5, edge_ke=EDGE_KE, edge_kd=0., particle_radius=RADIUS)
    builder.add_shape_mesh(body=-1, mesh=newton.Mesh(B.astype(np.float32), b.faces.ravel().astype(np.int32)))
    builder.color(include_bending=True)
    model = builder.finalize()
    model.soft_contact_ke, model.soft_contact_kd, model.soft_contact_mu = CONTACT_KE, CONTACT_KD, MU
    model.set_gravity((0., -9.81, 0.))
    flags = model.particle_flags.numpy(); flags[~free] &= ~newton.ParticleFlags.ACTIVE; model.particle_flags = wp.array(flags)
    solver = newton.solvers.SolverVBD(model, iterations=ITERATIONS)
    s0, s1, control = model.state(), model.state(), model.control()
    s0.particle_q.assign(X1.astype(np.float32)); s1.particle_q.assign(X1.astype(np.float32))
    pipeline = newton.CollisionPipeline(model); contacts = pipeline.contacts()
    for _ in range(FRAMES):
        pipeline.collide(s0, contacts)
        for _ in range(SUBSTEPS):
            s0.clear_forces(); solver.step(s0, s1, control, contacts, 1 / 60 / SUBSTEPS); s0, s1 = s1, s0
    return s0.particle_q.numpy().astype(float)


if __name__ == '__main__':
    src, dst = sys.argv[1:3]
    b = body('B'); B = b.vertices
    g = Garment(src); P0 = g.vertices(); m = g.mesh(P0)
    _, inv = np.unique(np.round(P0, 5), axis=0, return_inverse=True); inv = inv.ravel()
    X0 = np.zeros((inv.max() + 1, 3)); X0[inv] = P0
    F = inv[m.faces]; F = F[(F[:, 0] != F[:, 1]) & (F[:, 1] != F[:, 2]) & (F[:, 0] != F[:, 2])]
    P1 = dress(P0, m.faces, B); X1 = np.zeros_like(X0); X1[inv] = P1
    P = settle(X0, X1, F, b)[inv]
    p95, p99, flipped = check(m, P0, P)
    cuff = max(cuff_to_hand(P, B, s) for s in (1, -1))
    hand = int(inside(b, P[(np.abs(P[:, 0]) > .19) & (P[:, 1] < HAND)]).sum())
    print('%s: stretch p95 %.1f%% p99 %.1f%%; flipped %d; cuff to hand %.1f cm; %d vertices inside the hand' % (
        src.split('/')[-1], 100 * p95, 100 * p99, flipped, 100 * cuff, hand))
    if p99 > MAX_STRETCH or flipped or cuff > MAX_CUFF or hand:
        sys.exit(f'{src}: the cloth does not settle within the limits; nothing written')
    g.save(dst, P, before=P0)
