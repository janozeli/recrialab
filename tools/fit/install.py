"""Regenerates the body masks (poses B and C) and the layer tables for tops already on the site.
usage: python3 tools/fit/install.py 016 017 ...          (no arguments: the 23 tops)
       python3 tools/fit/install.py --bottom 008         (bottom garment with new geometry: whole table and mask hash)
       python3 tools/fit/install.py --bottom-mask 006    (mask only: hides the body that pokes through the bottom garment)
       python3 tools/fit/install.py --mask 016 ...       (tops' masks only: after --bottom, which already rebuilt the pairs)
       python3 tools/fit/install.py --bottom-line 004    (bottom mask with the same hidden body: hash and waistband line only)"""
import sys, json, hashlib, os, trimesh, numpy as np
from garment import Garment
from gen_mask import hidden_triangles, poke_through_without_holes, legs_without_holes, exposed, poke_through
from gen_layers import pair
from mask_io import save, hidden_indices
import waist
import layer_tables
import collar, sleeve, strap
from paths import BODY, GARMENTS, LAYERS, MASKS
LONG_SLEEVE = {
    '027',
    '028',
    '033',
    '034',
    '035',
    '036',
    '037',
    '038',
}
sha = lambda p: hashlib.sha256(open(p, 'rb').read()).hexdigest()

line_only = sys.argv[1:2] == ['--bottom-line']
if line_only: sys.argv[1] = '--bottom-mask'
mask_only = sys.argv[1:2] in (['--bottom-mask'], ['--mask'])
if sys.argv[1:2] == ['--mask']: sys.argv[1:2] = []
bottoms = sys.argv[2:] if sys.argv[1:2] in (['--bottom'], ['--bottom-mask']) else []
assert sys.argv[1:2] not in (['--bottom'], ['--bottom-mask']) or bottoms, 'usage: install.py --bottom 008 (or --bottom-mask 008)'
tops = ([] if bottoms else sys.argv[1:]) or [f'{i:03d}' for i in range(16, 39)]
bodies = {}
for pose, f in [('B', 'pose-b.glb'), ('C', 'pose-c.glb')]:
    m = trimesh.load(BODY + f, process=False)
    bodies[pose] = (list(m.geometry.values())[0], sha(BODY + f))
meshes = {id: Garment(GARMENTS + f'{id}.glb').mesh() for id in tops} if bottoms and not mask_only else {}
for id in ([] if bottoms else tops):
    glb = GARMENTS + f'{id}.glb'
    g = Garment(glb).mesh(); meshes[id] = g
    for pose, path in [('B', f'pose-b/{id}.json'), ('C', f'pose-c/{id}.json')]:
        body, bhash = bodies[pose]
        mask = json.load(open(MASKS + path))
        hidden = hidden_triangles(body, g, id in LONG_SLEEVE)
        mask.pop('neck_line', None); mask.pop('sleeve_line', None)
        if id in collar.IDS:   # shader clip at the collar line (collar.py): line of the new geometry, band given back
            L = collar.line(g, body); mask['neck_line'] = [round(float(v), 4) for v in L]
            hide = np.zeros(len(body.faces), bool); hide[hidden] = True; hidden = np.nonzero(hide & ~collar.band(body, L))[0]
        if id in sleeve.IDS:   # shader clip at the sleeve hem (sleeve.py): line of the new geometry, band given back
            L = sleeve.hem(g, body); mask['sleeve_line'] = [round(float(v), 4) for v in L]
            hide = np.zeros(len(body.faces), bool); hide[hidden] = True; hidden = np.nonzero(hide & ~sleeve.band(body, L))[0]
        hide = np.zeros(len(body.faces), bool); hide[hidden] = True   # shoulder poking through the strap (strap.py)
        hidden = np.nonzero(hide | strap.extra(body, g, hide))[0]
        mask.update(body_sha256=bhash, garment_sha256=sha(glb))
        assert mask['meshes'][0]['triangle_count'] == len(body.faces)
        save(MASKS + path, mask, hidden)
    print(id, 'masks ok', flush=True)
for bid in bottoms:
    # a bottom garment's body mask keeps what it hid, plus the body that pokes through the garment (a white sliver
    # on the fly of 006) where hiding it opens no hole; and the hidden triangle the new geometry uncovers shows
    # again (exposed)
    g = Garment(GARMENTS + f'{bid}.glb').mesh()
    for pose, path in [('B', MASKS + f'pose-b/{bid}.json'), ('C', MASKS + f'pose-c/{bid}.json')]:
        if not os.path.exists(path): continue
        body = bodies[pose][0]
        mask = json.load(open(path)); mask.update(body_sha256=bodies[pose][1], garment_sha256=sha(GARMENTS + f'{bid}.glb'))
        hide = np.zeros(len(body.faces), bool); hide[hidden_indices(mask)] = True
        # new geometry that uncovers a hidden triangle (trimmed hem, fringe.py) gives the triangle back
        # (only one that does not poke through the cloth from another camera: that one would show as a poke-through)
        if not line_only:   # --bottom-line: islands.py only removed crumbs; giving the body back shows the leg through the tears (004, 014)
            ex = exposed(body, g); hide &= ~(ex & ~poke_through(body, g, np.zeros_like(hide)))
            hide |= poke_through_without_holes(body, g, hide, ex)
        # ankle through the hem and thigh at the crotch (the cameras above stop at the hip)
        hide |= legs_without_holes(body, g, hide)
        if 'waist_line' in mask:   # shader clip at the waistband line (waist.py): line of the new geometry, band given back
            L = waist.line(g, body); mask['waist_line'] = [round(float(v), 4) for v in L]; hide &= ~waist.band(body, L)
        save(path, mask, np.nonzero(hide)[0])
    print(bid, 'mask ok', flush=True)
if mask_only: sys.exit()
for n in ([int(b) for b in bottoms] or range(1, 16)):
    bid = f'{n:03d}'
    path = LAYERS + f'{bid}.json'
    table = json.load(open(path))
    bottom = Garment(GARMENTS + f'{bid}.glb')
    mesh_sizes = [{'vertices': s, 'triangles': bottom.js['accessors'][p['indices']]['count'] // 3} for s, (a, M, p) in zip(bottom.sizes, bottom.parts)]
    assert bottoms or mesh_sizes == table['meshes']   # a new mesh (hem.py) only with --bottom, which rebuilds every pair
    if bottoms: table.update(bottomHash=sha(GARMENTS + f'{bid}.glb'), meshes=mesh_sizes)
    for id in tops:
        table['pairs'][id] = pair(bottom, meshes[id])
        table['topHashes'][id] = sha(GARMENTS + f'{id}.glb')
    layer_tables.save(path, table)
    print(bid, 'layers ok', flush=True)
