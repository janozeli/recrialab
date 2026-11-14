"""Brightness of each garment on the site against the thrift-shop photo, and the colour gain the site applies to it (site/garment-tones.ts).

The 3D generator painted some textures darker and others lighter than the photo (front view, median luminance on
stage against that of the photo cut out by its alpha: up to 40% darker or 50% lighter). The site has a single light
for all of them; the per-garment gain multiplies the material colour (texture and print stay the same, only lighter or
darker). The saturation per garment brings the chroma (median Lab a, b) to the photo's in the same way: the generator
painted some textures more saturated, and the gain that lifts a dark garment lifts its chroma with it.
usage: python3 tools/visual-qa/tone.py DIR              (DIR from visual-qa.mjs --beauty with the 38 garments: NNN and 001.NNN)
       python3 tools/visual-qa/tone.py DIR --fit        (corrects the gain by what is missing and rewrites site/garment-tones.ts)"""
import os, re, sys, numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from measure import ROOT, read_cls, TOP, BOTTOM, luminance, photo_brightness

FILE = f'{ROOT}/site/garment-tones.ts'
GAMMA = 1.6             # screen brightness ~ gain^k, k measured from 0.45 (light knit) to 1.4 (dark denim)
SATURATION = (.4, 1.3)
HUE = (-30, 30)          # degrees around the grey axis (site/fabric.ts colourMatrix)
CHROMA_MIN = 8          # below this chroma (near grey, black, white) the hue is noise: saturation stays at 1
GAIN = (.35, 4)       # ceiling raised 13/11 with the self light carrying the gain: 020, 032 and 037 stayed 16-30% dark at 2.5


def lab(rgb):
    c = rgb / 255.; c = np.where(c > .04045, ((c + .055) / 1.055) ** 2.4, c / 12.92)
    x = c @ np.array([[.4124, .3576, .1805], [.2126, .7152, .0722], [.0193, .1192, .9505]]).T / [.95047, 1, 1.08883]
    f = np.where(x > .008856, np.cbrt(x), 7.787 * x + 16 / 116)
    return np.stack([116 * f[:, 1] - 16, 500 * (f[:, 0] - f[:, 1]), 200 * (f[:, 1] - f[:, 2])], 1)


def chroma(rgb):
    """Chroma and hue (degrees) of the garment's median colour, and the 95th percentile of its pixels' chroma (the strongest accents)."""
    L = lab(rgb); a, b = np.median(L, 0)[1:]
    return float(np.hypot(a, b)), float(np.percentile(np.hypot(L[:, 1], L[:, 2]), 95)), float(np.degrees(np.arctan2(b, a)))


def on_site(folder, pid):
    """Median luminance and chroma of the garment from the front on stage, or None if the folder does not have it."""
    for look in ([pid] if int(pid) <= 15 else [f'001.{pid}'] + [d for d in os.listdir(folder) if d.endswith('.' + pid)]):
        p = os.path.join(folder, look, 'eye-0')
        if os.path.exists(p + '.jpg') and os.path.exists(p + '.cls'):
            m = read_cls(p + '.cls') == (TOP if int(pid) > 15 else BOTTOM)
            px = np.asarray(Image.open(p + '.jpg').convert('RGB'), float)[m]
            return float(np.median(luminance(px))), chroma(px)
    return None


def photo_chroma(pid):
    a = np.asarray(Image.open(f'{ROOT}/site/assets/photos/{pid}.webp').convert('RGBA'), float)
    return chroma(a[a[..., 3] > 250][:, :3])


def load():
    text = open(FILE, encoding='utf8').read() if os.path.exists(FILE) else ''
    tables = re.split(r'export const (?:SATURATION|HUE)', text) + ['', '']
    read = lambda t: {k: float(v) for k, v in re.findall(r"'(\d{3})': (-?[\d.]+)", t)}
    return read(tables[0]), read(tables[1]), read(tables[2])


def save(g, sat, hue):
    table = lambda d: ''.join(f"  '{k}': {v:.3f},\n" for k, v in sorted(d.items()))
    open(FILE, 'w', encoding='utf8').write(
        '// Colour gain per garment (multiplies the material colour): the front brightness on stage stays close to the\n'
        "// thrift-shop photo's. Written by tools/visual-qa/tone.py --fit; the `tone` measure of tools/visual-qa/measure.py guards it.\n"
        f'export const TONE: Record<string, number> = {{\n{table(g)}}};\n'
        "\n// Colour saturation per garment (1 = the texture's): written by tools/visual-qa/tone.py --fit from the chroma of the photo.\n"
        f'export const SATURATION: Record<string, number> = {{\n{table(sat)}}};\n'
        "\n// Hue turn per garment in degrees (0 = the texture's): written by tools/visual-qa/tone.py --fit from the photo's Lab hue.\n"
        f'export const HUE: Record<string, number> = {{\n{table(hue)}}};\n')


if __name__ == '__main__':
    folder = sys.argv[1]
    g, sat, hue = load()
    for i in range(1, 39):
        pid = f'{i:03d}'; site = on_site(folder, pid)
        if site is None: continue
        s, c = site
        f, fc = photo_brightness(pid), photo_chroma(pid)
        gain, k = g.get(pid, 1.0), sat.get(pid, 1.0)
        new = float(np.clip(gain * (f / s) ** GAMMA, *GAIN))
        (c, c95, h), (fc, fc95, fh) = c, fc
        turn = hue.get(pid, 0.0)
        # hue only where both colours have one: on near-grey garments it is noise
        newh = float(np.clip(turn + (fh - h + 180) % 360 - 180, *HUE)) if min(c, fc) >= CHROMA_MIN else turn
        newk = float(np.clip(k * fc / c, *SATURATION)) if max(c, fc) >= CHROMA_MIN and c > 0 else k
        # the strongest accents never end below the photo's: a navy body must not drain the orange pocket of 021
        if c95 > 0 and newk < 1: newk = float(np.clip(max(newk, k * fc95 / c95), SATURATION[0], 1))
        print(f'{pid} photo {f:5.1f} site {s:5.1f} {100 * (s / f - 1):+4.0f}%  gain {gain:.3f} → {new:.3f}'
              f'  chroma {fc:5.1f} site {c:5.1f} accents {fc95:5.1f} site {c95:5.1f}  saturation {k:.3f} → {newk:.3f}  hue {turn:+.1f} → {newh:+.1f}')
        g[pid], sat[pid], hue[pid] = new, newk, newh
    if '--fit' in sys.argv:
        save({k: v for k, v in g.items() if abs(v - 1) > .005}, {k: v for k, v in sat.items() if abs(v - 1) > .005},
             {k: round(v, 1) for k, v in hue.items() if abs(v) >= 2})
