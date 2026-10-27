"""Visual QA: measures, on the pictures tools/verify-site/visual-qa.mjs took of the real site, what makes a
garment look wrong. Each measure is a class of defect seen when turning the mannequin on the site (front, profile,
back, from below and from above).

  python3 tools/visual-qa/measure.py DIR            # table per look
  python3 tools/visual-qa/measure.py DIR --ci       # fails a new defect and a fixed defect that is still listed

A known defect is never accepted silently: tools/visual-qa/defects.json links each look to an open known issue
that names one of its pieces (known_issues.py), or records it under `_accepted` with who accepted it and a cap
(what the thrift-shop photo has, like skin through a tear). A defect not on the list fails; a listed defect that went
away also fails (take it off the list and close the issue in the same change). Limits live in LIMITS, never per
garment.
"""
import glob, gzip, json, os, re, sys
import numpy as np
from PIL import Image
from scipy import ndimage as nd
from known_issues import FILE as KNOWN_ISSUES, known_issues

W, H = 720, 1200
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CM = 2 * 4.4 * np.tan(np.radians(15)) / H * 100  # cm per pixel on the mannequin plane (the site camera)
CM2 = CM * CM
TOP, TOP_BACK, BOTTOM, BOTTOM_BACK, BODY, BACKGROUND = 2, 3, 4, 5, 1, 0

# Limits per defect class (cm or cm² in the worst view). They hold for every garment.
LIMITS = {
    'midriff': 20.0,      # torso in view between the top and the bottom garment (cm²)
    'junction': 6.0,      # jagged bottom garment right below the top's hem (cm²)
    'threads': 12.0,      # thin loose tips of the garment: pointed fringe, thread, jagged hem (cm²)
    'pokes': 2.0,         # body poking through the garment: enclosed by garment, with the cloth right behind it (cm²); never natural
    'tear': 4.0,          # body seen through a hole or tear: enclosed by garment, with no cloth right behind (cm²)
    'see_through': 4.0,   # background enclosed by garment where the whole body would be (cm²): garment open over a hidden body
    'arm_gap': 4.0,       # background where the arm is, between the elbow and the armpit: arm clipped with nothing behind (cm²)
    'loose': 1.0,         # piece of garment floating in the air (cm²)
    'dark_patch': 6.0,    # texture darker than the darkest of the thrift-shop photo (% of the garment seen from the front)
    'waistband': 4.0,     # waistband sunken in the middle (front or back) relative to the sides (cm)
    'tone': 15.0,         # front brightness on stage away from the thrift-shop photo's (% of the median luminance)
}
# garment depth (.depth.gz from visual-qa.mjs): step in cm, the same DEPTH as there
DEPTH_CM = 100 * float(re.search(r'DEPTH = ([\d.]+)', open(f'{ROOT}/tools/verify-site/visual-qa.mjs', encoding='utf8').read()).group(1))
TIGHT = 3.0           # cm: cloth up to this behind the hole's outline is the same sheet passing behind the body (poking through)
LIP = 5               # px (1 cm): arm in a hole this close to the arm out of the sleeve is the arm going into the sleeve
MEASURES = []         # rows of measures*.json (what the browser measured: torso in view at the waist)


def read_cls(path):
    a = np.frombuffer(open(path, 'rb').read(), np.uint8)
    return np.repeat(a[0::2], a[1::2]).reshape(H, W)


def disk(r):
    return np.add.outer(np.arange(-r, r + 1) ** 2, np.arange(-r, r + 1) ** 2) <= r * r


def thin(m, r=3):
    """Part of the mask thinner than 2r+1 px (~1.4 cm): thread, pointed fringe, jagged edge."""
    if not m.any():
        return np.zeros_like(m)
    f = m & ~nd.binary_opening(m, disk(r))
    lab, n = nd.label(f)
    if not n:
        return f
    areas = nd.sum(f, lab, range(1, n + 1))
    return np.isin(lab, 1 + np.where(areas >= 12)[0])


# fraction of the neighborhood outside the garment that is body with garment behind. An edge with the arm or the hand
# passing on one side and the background on the other gives 0.45 to 0.50 (the side of the tank top behind the arm, the
# cuff beside the hand, the collar behind the neck); a real flap beside the body (waistband of 009 seen from above,
# slivers of the hem of 033) stays below 0.4
OVERLAP = .4


def without_overlap(f, c, depth):
    """Removes from `f` (thin part) the piece that is thin only because the body passes in front of the garment (the arm
    in front of the skirt's edge, seen from above): much of its neighborhood outside the garment is body with garment behind."""
    lab, n = nd.label(f, np.ones((3, 3), bool))
    garment = c >= TOP
    for i in range(1, n + 1):
        reg = lab == i
        nb = nd.binary_dilation(reg, disk(2)) & ~garment
        if nb.any() and ((c[nb] == BODY) & (depth[nb] > 0)).mean() > OVERLAP:
            f = f & ~reg
    return f


def dark_pct(lum, mask, threshold):
    """Percentage of the area darker than `threshold` in patches (ignores the thin shadow of a fold)."""
    if mask.sum() < 200:
        return 0.0
    dark = nd.binary_opening(mask & (lum < threshold), disk(2))
    return float(dark.sum() / mask.sum() * 100)


def luminance(x):
    return .2126 * x[..., 0] + .7152 * x[..., 1] + .0722 * x[..., 2]


def photo_brightness(pid):
    """Median luminance of the garment in the thrift-shop photo (cut out by its alpha)."""
    a = np.asarray(Image.open(f'{ROOT}/site/assets/photos/{pid}.webp').convert('RGBA'), float)
    return float(np.median(luminance(a[a[..., 3] > 250][:, :3])))


def photo_threshold(pid):
    """Darker than the cloth in the thrift-shop photo: 80% of the 2nd percentile of the garment's luminance in the
    photo (the alpha cuts out the garment; the black background and a dark garment are not confused). A black
    texture patch (what the generator did not see) falls below this; stripes, numbers and dark prints, which the
    photo has, stay above."""
    a = np.asarray(Image.open(f'{ROOT}/site/assets/photos/{pid}.webp').convert('RGBA'), float)
    m = nd.binary_erosion(a[..., 3] > 250, disk(2))
    return .8 * np.percentile(a[..., :3].mean(2)[m], 2)


def read_body(path):
    """Where the whole body, without the mask and without garments, would cover the view: 1 body, 2 arm between the
    elbow and the armpit (visual-qa.mjs, ARM_X and ARM_Y0 to ARM_Y1), 0 nothing."""
    return np.frombuffer(gzip.open(path).read(), np.uint8).reshape(H, W)


def read_depth(path):
    """Distance from the garment to the camera in cm per pixel (0 = no garment), from a pass without the body."""
    return np.frombuffer(gzip.open(path).read(), np.uint8).reshape(H, W).astype(float) * DEPTH_CM


def enclosed(c, garment, target, depth=None, inside=None, top=None, whole=None):
    """Area of `target` in regions without garment enclosed only by garment (a component that does not touch the image
    border). With depth, splits the body into (poking, tear): poking is the body with the garment right behind it, at
    the depth of the hole's outline (the sheet passes behind the body, which goes through it); tear, the body seen
    through the opening, with the garment far behind (the other side of the leg) or no garment. With `top` and `whole`,
    a hole outlined only by the top, on the arm (whole == 2) and within LIP of the arm out of the garment is the arm
    going up into the sleeve, seen past the hem's lip from below: neither."""
    lab, n = nd.label(~garment, np.ones((3, 3), bool))
    if not n:
        return 0 if depth is None else (0, 0)
    border = np.unique(np.r_[lab[0], lab[-1], lab[:, 0], lab[:, -1]])
    areas = np.bincount(lab.ravel(), minlength=n + 1)
    ok = np.ones(n + 1, bool)
    ok[0] = False
    ok[border] = False
    # a hole is small: a larger region is the whole arm under the sleeve, the gap between the legs or the midriff (measured apart)
    ok &= areas <= 300
    if depth is None:
        return int((ok[lab] & (c == target) & (True if inside is None else inside)).sum())
    poking = tear = 0
    out = ~ok[lab] & (c == target)
    for i in np.nonzero(ok)[0]:
        reg = lab == i
        m = reg & (c == target)
        if not m.any():
            continue
        near = nd.binary_dilation(reg, disk(2)) & garment
        if top is not None and top[near].all() and (whole[m] == 2).mean() > .5 and (nd.binary_dilation(reg, disk(LIP)) & out).any():
            continue
        ring = depth[near]
        edge = np.median(ring[ring > 0]) if (ring > 0).any() else 0
        behind = depth[m]
        f = int(((behind > 0) & (behind - edge < TIGHT)).sum())
        poking += f
        tear += int(m.sum()) - f
    return poking, tear


def measure_view(c, alb, depth, whole):
    r = {}
    top, bottom = np.isin(c, (TOP, TOP_BACK)), np.isin(c, (BOTTOM, BOTTOM_BACK))
    garment = top | bottom
    r['threads'] = float(without_overlap(thin(top), c, depth).sum() * CM2), float(without_overlap(thin(bottom), c, depth).sum() * CM2)
    poking, tear = enclosed(c, garment, BODY, depth, top=top, whole=whole)
    r['pokes'], r['tear'] = poking * CM2, tear * CM2
    # see-through: the background where the whole body would be (hidden body and open garment); outside it, it is the
    # gap of the armpit or between the legs, which a real garment also lets show
    r['see_through'] = enclosed(c, garment, BACKGROUND, inside=whole > 0) * CM2
    # armpit slit: the arm clipped under the sleeve with nothing behind it, so the background shows where the arm is
    # (022 from the front); open at the bottom, so see_through, which needs garment around it, does not count it. A strip
    # under 5 px wide along the outline is the arm a little wider than its sleeve (033, 027), not a slit: opened away
    r['arm_gap'] = float(nd.binary_opening((c == BACKGROUND) & (whole == 2), disk(2)).sum() * CM2)
    # loose piece: a garment component that only touches the background
    loose = 0
    for m in (top, bottom):
        lab, n = nd.label(m)
        if n > 1:
            areas = nd.sum(m, lab, range(1, n + 1))
            largest = 1 + int(np.argmax(areas))
            for i in range(1, n + 1):
                if i == largest or areas[i - 1] < 6:
                    continue
                reg = lab == i
                nb = nd.binary_dilation(reg, disk(1)) & ~reg
                if np.all(c[nb] == BACKGROUND):
                    loose += areas[i - 1]
    r['loose'] = loose * CM2
    # junction: jagged bottom garment in a 4 cm band below the top's hem
    if top.any() and bottom.any():
        fb = thin(bottom)
        base = np.where(top.any(0), H - 1 - np.argmax(top[::-1], 0), -1)
        rows = np.arange(H)[:, None]
        band = (base[None, :] >= 0) & (rows > base[None, :] - 3) & (rows < base[None, :] + 4 / CM)
        r['junction'] = float((fb & band).sum() * CM2)
    r['_lum'] = np.asarray(alb.convert('L'), float)
    return r


def edge_dip(m, from_top):
    """How much the middle of the edge (waistband or hem) sinks relative to the sides, in cm (positive = lower middle)."""
    cols = np.where(m.any(0))[0]
    if len(cols) < 60:
        return 0.0
    x0, x1 = cols[0], cols[-1]
    xs = np.arange(x0, x1 + 1)
    ys = np.array([np.argmax(m[:, x]) if from_top else H - 1 - np.argmax(m[::-1, x]) for x in xs], float)
    n = len(xs)
    middle = ys[int(.4 * n):int(.6 * n)].mean()
    sides = np.r_[ys[int(.08 * n):int(.2 * n)], ys[int(.8 * n):int(.92 * n)]].mean()
    return float((middle - sides) * CM)


def measure_look(folder):
    look = os.path.basename(folder.rstrip('/'))
    pieces = look.split('.')
    has_top = any(int(p) > 15 for p in pieces)
    has_bottom = any(int(p) <= 15 for p in pieces)
    midriff = {l['view']: l['midriff'] * l['metersPerPx'] ** 2 * 1e4 for l in MEASURES if l['look'] == look}
    out = {k: 0.0 for k in LIMITS}
    where = {}
    dark = {'top': [], 'bottom': []}

    def peak(k, v, view):
        if v > out[k]:
            out[k], where[k] = v, view

    for f in sorted(glob.glob(os.path.join(folder, '*.cls'))):
        view = os.path.basename(f)[:-4]
        c = read_cls(f)
        alb = Image.open(f[:-4] + '.albedo.jpg')
        if not os.path.exists(f[:-4] + '.depth.gz'):
            sys.exit(f'{f[:-4]}.depth.gz does not exist: take the pictures again with visual-qa.mjs (garment depth)')
        if not os.path.exists(f[:-4] + '.body.gz'):
            sys.exit(f'{f[:-4]}.body.gz does not exist: take the pictures again with visual-qa.mjs (whole body)')
        r = measure_view(c, alb, read_depth(f[:-4] + '.depth.gz'), read_body(f[:-4] + '.body.gz'))
        peak('threads', max(r['threads']), view)
        for k in ('pokes', 'tear', 'see_through', 'arm_gap', 'loose', 'junction'):
            if k in r:
                peak(k, r[k], view)
        if has_top and has_bottom:
            peak('midriff', midriff.get(view, 0.0), view)
        # dark patch: from the front only, the side the thrift-shop photo shows
        if view == 'eye-0':
            for name, k in (('top', TOP), ('bottom', BOTTOM)):
                ids = [p for p in pieces if (int(p) > 15) == (name == 'top')]
                if ids:
                    dark[name].append(dark_pct(r['_lum'], c == k, photo_threshold(ids[0])))
        # tone: from the front, lit (only with --beauty), the median brightness of each garment against the photo's
        if view == 'eye-0' and os.path.exists(f[:-4] + '.jpg'):
            screen = np.asarray(Image.open(f[:-4] + '.jpg').convert('RGB'), float)
            for p in pieces:
                if int(p) <= 15 and has_top: continue   # the bottom under the top only shows the legs
                m = c == (TOP if int(p) > 15 else BOTTOM)
                if m.sum() > 2000:
                    peak('tone', abs(100 * (np.median(luminance(screen[m])) / photo_brightness(p) - 1)), view)
        # waistband: only with the bottom garment alone (the top covers the waistband)
        if view in ('eye-0', 'eye-180') and has_bottom and not has_top:
            peak('waistband', edge_dip(np.isin(c, (BOTTOM, BOTTOM_BACK)), True), view)
    for name, ids in (('top', [p for p in pieces if int(p) > 15]), ('bottom', [p for p in pieces if int(p) <= 15])):
        if ids and dark[name]:
            peak('dark_patch', max(dark[name]), 'eye-0')
    return look, out, where


def main():
    root = sys.argv[1]
    ci = '--ci' in sys.argv
    for f in glob.glob(os.path.join(root, '**', 'measures*.json'), recursive=True):
        MEASURES.extend(json.load(open(f))['rows'])
    folders = sorted({os.path.dirname(f) for f in glob.glob(os.path.join(root, '**', '*.cls'), recursive=True)})
    table = {}
    for p in folders:
        look, out, where = measure_look(p)
        table[look] = {'measures': {k: round(v, 1) for k, v in out.items()}, 'worst_view': where}
    json.dump(table, open(os.path.join(root, 'visual-qa.json'), 'w'), indent=1, ensure_ascii=False)
    found = {}
    for look, t in table.items():
        for k, v in t['measures'].items():
            if v > LIMITS[k]:
                found.setdefault(k, []).append(look)
    print('limit  ' + '  '.join(f'{k}={v}' for k, v in LIMITS.items()))
    for k, looks in found.items():
        print(f'{k:11} {len(looks):3} looks: ' + ' '.join(f"{l}({table[l]['measures'][k]})" for l in looks))
    if not ci:
        return
    known = json.load(open(f'{ROOT}/tools/visual-qa/defects.json', encoding='utf8'))
    issues = known_issues()
    errors = []
    # accepted by a person (what the thrift-shop photo has, like skin through a tear): passes up to the recorded
    # cap and must not go away (the photo's tear closed is a defect too)
    accepted = known.get('_accepted', {})
    for k, looks in accepted.items():
        for look, a in looks.items():
            if not a.get('by'):
                errors.append(f'{k} on {look}: accepted without saying by whom')
            if look not in table:
                continue
            v = table[look]['measures'][k]
            if v > a['up_to']:
                errors.append(f'{k} on {look} went past the accepted value ({v} > {a["up_to"]}, view {table[look]["worst_view"][k]})')
            elif v < LIMITS[k] / 2:
                errors.append(f'{k} on {look} went away, but it was accepted ({a["by"]}): check it against the photo')
            if v > LIMITS[k] and k in found and look in found[k]:
                found[k].remove(look)
    for k, looks in known.items():
        if k.startswith('_'):
            continue
        for key, stream in looks.items():
            if stream not in issues:
                errors.append(f'{k} {key}: {stream} is not an open known issue in {KNOWN_ISSUES}')
            elif not issues[stream] & set(key.split('.')):
                errors.append(f'{k} {key}: known issue {stream} names none of the pieces of {key}')
    for k, looks in found.items():
        for look in looks:
            if look not in known.get(k, {}):
                errors.append(f'new defect: {k} on {look} ({table[look]["measures"][k]} > {LIMITS[k]}, '
                              f'view {table[look]["worst_view"][k]})')
    measured = set(table)
    for k, looks in known.items():
        if k.startswith('_'):
            continue
        for key in looks:
            target = [l for l in measured if l == key]
            # really gone: below half the limit on every measured look (near the limit it is render noise)
            if target and all(table[l]['measures'][k] < LIMITS[k] / 2 for l in target):
                errors.append(f'{k} on {key} went away: take it off tools/visual-qa/defects.json and close the known issue')
    print('\n'.join(errors) or 'visual QA ok')
    sys.exit(1 if errors else 0)


if __name__ == '__main__':
    main()
