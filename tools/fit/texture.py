"""Black patches in the texture of the bottoms: area the generator did not see (between the legs) and painted flat
black. On 005 a black panel showed on each side of the crotch, from the front and from the back.

With cameras at the front, back and sides at leg height, it measures the fraction of the visible fabric that falls on
an almost black texel (largest channel < 30) belonging to a large patch (> 300 texels) on a light fabric (median
brightness > 60). With --paint, each such patch falling between the legs (|x| < 15 cm, below the waistband) takes the
colour of the fabric around it (nearest neighbour, smoothed); geometry and UV do not change.
The reference is the shop photo: the black the photo also has (the black suede panels inside the thighs of jeans
005) is the design of the piece, not a patch. Each piece's limit is N plus the photo's black in large pieces
(PHOTO_PIECE of the garment, cut out by the photo's alpha); --paint only applies where the photo has no black.
usage: python3 tools/fit/texture.py [--max N] [IDs]          (without IDs: the 15 bottoms; exits with an error above N% + the photo's black)
       python3 tools/fit/texture.py --paint INPUT.glb OUTPUT.glb
       python3 tools/fit/texture.py --tone INPUT.glb OUTPUT.glb NNN   (the black the photo also has, in the photo's tone)"""
import io, sys, numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy import ndimage
from trimesh.ray.ray_pyembree import RayMeshIntersector
import trimesh
from garment import Garment
from glb_patch import read, write, accessor_view
from gen_mask import cameras
from paths import GARMENTS, PHOTOS


DARK, PATCH, LIGHT, UV_MAX = 30, 300, 60, 5000
PHOTO_PIECE = .01   # black piece of the photo that counts: at least 1% of the garment (shadow and seams stay out)


def image(js):
    """bufferView of the base colour texture of the first material."""
    t = js['textures'][js['materials'][0]['pbrMetallicRoughness']['baseColorTexture']['index']]
    src = t.get('source', t.get('extensions', {}).get('EXT_texture_webp', {}).get('source'))
    return js['images'][src]


def read_texture(js, b):
    v = js['bufferViews'][image(js)['bufferView']]
    return np.array(Image.open(io.BytesIO(bytes(b[v.get('byteOffset', 0):v.get('byteOffset', 0) + v['byteLength']]))).convert('RGB'))


def replace_view(js, b, vi, data_new):
    """Replaces the bytes of a bufferView and repacks the buffer (offsets aligned to 4)."""
    out = bytearray(); views = js['bufferViews']
    for i, v in enumerate(views):
        s = v.get('byteOffset', 0); data = data_new if i == vi else bytes(b[s:s + v['byteLength']])
        out += b'\0' * (-len(out) % 4); v['byteOffset'] = len(out); v['byteLength'] = len(data); out += data
    js['buffers'][0]['byteLength'] = len(out)
    return out


def uv_and_faces(g):
    """UV (TEXCOORD_0) per vertex, in the same order as Garment.mesh(), and which faces use the texture read (the
    restored waistband of some trousers is another primitive, with another material)."""
    uvs, uses = [], []
    for a, M, p in g.parts:
        n = g.js['accessors'][p['indices']]['count'] // 3; uses.append(np.full(n, p.get('material', 0) == 0))
        ai = p['attributes']['TEXCOORD_0']; acc, s, stride = accessor_view(g.js, g.bin, ai)
        stride = g.js['bufferViews'][acc['bufferView']].get('byteStride', 8)
        uvs.append(np.array([np.frombuffer(bytes(g.bin[s + i * stride:s + i * stride + 8]), '<f4') for i in range(acc['count'])]))
    return np.vstack(uvs), g.mesh(), np.concatenate(uses)


def patches(tex, uv, m, uses):
    """Labels of the large black patches and, per patch, the median position of the faces that use it."""
    H, W, _ = tex.shape
    face = Image.new('I', (W, H), 0); d = ImageDraw.Draw(face)
    px = np.c_[uv[:, 0] % 1 * W, uv[:, 1] % 1 * H]   # glTF: v grows downward in the image
    T = px[m.faces]; e1, e2 = T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]; area = np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]) / 2
    # largest first (the small ones overwrite); a giant UV triangle crosses the atlas and owns nothing
    for k in sorted(np.nonzero(uses & (area < UV_MAX))[0], key=lambda k: -area[k]):
        d.polygon([tuple(p) for p in T[k]], fill=int(k) + 1)
    face = np.array(face)
    lab, n = ndimage.label(tex.max(2) < DARK)
    C = m.triangles_center; out = {}
    for L, size in enumerate(ndimage.sum(np.ones_like(lab), lab, range(1, n + 1)), 1):
        if size < PATCH: continue
        fs = np.unique(face[lab == L]); fs = fs[fs > 0] - 1
        if len(fs): out[L] = np.median(C[fs], 0)
    return lab, out, face


def visible_black(pid):
    g = Garment(GARMENTS + f'{pid}.glb'); tex = read_texture(g.js, g.bin); uv, m, uses = uv_and_faces(g)
    lab, ps, _ = patches(tex, uv, m, uses); H, W, _ = tex.shape
    ri = RayMeshIntersector(m); total = black = 0; brightness = []
    for o, d in cameras(.008, center=.7, half=.45, elevs=(0,)):
        loc, ir, it = ri.intersects_location(o, d, multiple_hits=False)
        it, loc = it[uses[it]], loc[uses[it]]
        if not len(it): continue
        bc = trimesh.triangles.points_to_barycentric(m.triangles[it], loc)
        u = (uv[m.faces[it]] * bc[:, :, None]).sum(1)
        x, y = (u[:, 0] % 1 * W).astype(int).clip(0, W - 1), (u[:, 1] % 1 * H).astype(int).clip(0, H - 1)
        total += len(it); black += int(np.isin(lab[y, x], list(ps)).sum()); brightness.append(tex[y, x].max(1))
    return pid, 100 * black / total if np.median(np.concatenate(brightness)) > LIGHT else 0.0


def photo(pid):
    """Shop photo (cut out by its alpha): pixels, the garment and its large almost black pieces."""
    a = np.asarray(Image.open(PHOTOS + f'{pid}.webp').convert('RGBA'), float)
    m = ndimage.binary_erosion(a[..., 3] > 250, iterations=2); p = (a[..., :3].max(2) < DARK) & m
    lab, n = ndimage.label(p); s = np.asarray(ndimage.sum(p, lab, range(1, n + 1)))
    return a, m, np.isin(lab, 1 + np.nonzero(s >= PHOTO_PIECE * m.sum())[0])


def photo_black(pid):
    """% of the garment in the photo in large almost black pieces. A garment that is dark in the photo (median
    brightness up to LIGHT) gets no allowance: its visible_black is already 0, and dark denim would otherwise raise
    the limit a lot."""
    a, m, large = photo(pid)
    if np.median(a[..., :3].max(2)[m]) <= LIGHT: return 0.0
    return 100 * float(large.sum() / m.sum())


def tone(src, dst, pid):
    """The black the photo also has stays, in the photo's tone: the 3D generator painted it darker than the suede in
    the photo. The luminance of each patch texel goes to the same quantile of the photo, added
    equally to the three channels (the colour of the black, slightly blue, stays)."""
    g = Garment(src); tex = read_texture(g.js, g.bin); uv, m, uses = uv_and_faces(g)
    lab, ps, _ = patches(tex, uv, m, uses); sel = np.isin(lab, list(ps))
    a, _, large = photo(pid); target = a[..., :3][ndimage.binary_erosion(large)].mean(1)
    q = tex[sel].astype(float); lum = q.mean(1)
    rank = np.argsort(np.argsort(lum, kind='stable'), kind='stable') / max(len(lum) - 1, 1)
    new = tex.copy(); new[sel] = np.clip(q + (np.quantile(target, rank) - lum)[:, None], 0, 255).round().astype(np.uint8)
    js, b = read(src); img = image(js); buf = io.BytesIO()
    Image.fromarray(new).save(buf, 'WEBP', quality=90)
    write(dst, js, replace_view(js, b, img['bufferView'], buf.getvalue()))
    print(f'{src}: {sel.sum()} texels, mean luminance {lum.mean():.1f} → {new[sel].mean():.1f} (photo {target.mean():.1f})')


def paint(src, dst):
    g = Garment(src); tex = read_texture(g.js, g.bin); uv, m, uses = uv_and_faces(g)
    lab, ps, face = patches(tex, uv, m, uses)
    # per texel, by the face that uses it: a patch can cover the inside of the leg and the back waistband at once
    C = np.vstack([[9, 9, 9], m.triangles_center])[face]
    leg = (np.abs(C[..., 0]) < .15) & (C[..., 1] < .95)
    target = np.isin(lab, list(ps)) & leg
    # the patch border is a dark gradient: it goes too, or the nearest neighbour brings the dark back; the dilation
    # does not leave the leg faces (nor enter the waistband) except in the atlas margin that no face owns
    target = ndimage.binary_dilation(target, iterations=10) & (tex.max(2) < 70) & (leg | (face == 0))
    # the colour comes only from the leg's own fabric, in its dominant colour (no seam, label or rivet)
    dom = np.median(tex[leg & (tex.max(2) >= 70)], 0)
    source = leg & ~target & (tex.max(2) >= 70) & (np.abs(tex.astype(int) - dom).max(2) < 40)
    _, (iy, ix) = ndimage.distance_transform_edt(~source, return_indices=True)
    new = tex.copy(); new[target] = tex[iy, ix][target]
    smooth = np.array(Image.fromarray(tex[iy, ix]).filter(ImageFilter.GaussianBlur(4)))
    new[target] = smooth[target]
    js, b = read(src); img = image(js); buf = io.BytesIO()
    Image.fromarray(new).save(buf, 'WEBP', quality=90)
    b = replace_view(js, b, img['bufferView'], buf.getvalue())
    write(dst, js, b)
    print(f'{src}: {target.sum()} texels painted')


if __name__ == '__main__':
    a = sys.argv[1:]
    if a[:1] == ['--paint']: paint(a[1], a[2]); sys.exit()
    if a[:1] == ['--tone']: tone(a[1], a[2], a[3]); sys.exit()
    lim = float(a[1]) if a[:1] == ['--max'] else 1e9; a = a[2:] if a[:1] == ['--max'] else a
    from multiprocessing import Pool
    with Pool(8) as p: res = p.map(visible_black, a or [f'{i:03d}' for i in range(1, 16)])
    in_photo = {pid: photo_black(pid) for pid, _ in res}
    for pid, f in res: print(pid, f'visible black {f:.1f}% (in the photo {in_photo[pid]:.1f}%)')
    bad = [f'{pid} {f:.1f}% (photo {in_photo[pid]:.1f}%)' for pid, f in res if f > lim + in_photo[pid]]
    if bad: sys.exit('black patch above the limit: ' + ', '.join(bad))
