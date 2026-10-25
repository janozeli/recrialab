"""Brightness of each garment on the site against the thrift-shop photo, and the colour gain the site applies to it (site/garment-tones.ts).

The 3D generator painted some textures darker and others lighter than the photo (front view, median luminance on
stage against that of the photo cut out by its alpha: up to 40% darker or 50% lighter). The site has a single light
for all of them; the per-garment gain multiplies the material colour (texture and print stay the same, only lighter or
darker).
usage: python3 tools/visual-qa/tone.py DIR              (DIR from visual-qa.mjs --beauty with the 38 garments: NNN and 001.NNN)
       python3 tools/visual-qa/tone.py DIR --fit        (corrects the gain by what is missing and rewrites site/garment-tones.ts)"""
import os, re, sys, numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from measure import ROOT, read_cls, TOP, BOTTOM, luminance, photo_brightness

FILE = f'{ROOT}/site/garment-tones.ts'
GAMMA = 1.6             # screen brightness ~ gain^k, k measured from 0.45 (light knit) to 1.4 (dark denim)
GAIN = (.35, 2.5)


def on_site(folder, pid):
    """Median luminance of the garment from the front on stage, or None if the folder does not have it."""
    for look in ([pid] if int(pid) <= 15 else [f'001.{pid}'] + [d for d in os.listdir(folder) if d.endswith('.' + pid)]):
        p = os.path.join(folder, look, 'eye-0')
        if os.path.exists(p + '.jpg') and os.path.exists(p + '.cls'):
            m = read_cls(p + '.cls') == (TOP if int(pid) > 15 else BOTTOM)
            return float(np.median(luminance(np.asarray(Image.open(p + '.jpg').convert('RGB'), float)[m])))
    return None


def load():
    return {k: float(v) for k, v in re.findall(r"'(\d{3})': ([\d.]+)", open(FILE, encoding='utf8').read())}


def save(g):
    lines = ''.join(f"  '{k}': {v:.3f},\n" for k, v in sorted(g.items()))
    open(FILE, 'w', encoding='utf8').write(
        '// Colour gain per garment (multiplies the material colour): the front brightness on stage stays close to the\n'
        "// thrift-shop photo's. Written by tools/visual-qa/tone.py --fit; the `tone` measure of tools/visual-qa/measure.py guards it.\n"
        f'export const TONE: Record<string, number> = {{\n{lines}}};\n')


if __name__ == '__main__':
    folder = sys.argv[1]
    g = load() if os.path.exists(FILE) else {}
    for i in range(1, 39):
        pid = f'{i:03d}'; s = on_site(folder, pid)
        if s is None: continue
        f = photo_brightness(pid); gain = g.get(pid, 1.0)
        new = float(np.clip(gain * (f / s) ** GAMMA, *GAIN))
        print(f'{pid} photo {f:5.1f} site {s:5.1f} {100 * (s / f - 1):+4.0f}%  gain {gain:.3f} → {new:.3f}')
        g[pid] = new
    if '--fit' in sys.argv:
        save({k: v for k, v in g.items() if abs(v - 1) > .005})
