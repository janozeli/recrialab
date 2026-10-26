"""Print of the pieces project_print.py builds, measured against the piece it was taken from (PRINT_SOURCE).

stretch.py compares a piece with its own original vertex by vertex; a projected piece has a new mesh, and its original
(reference/originals/tripo/NNN.glb) is the projection itself, so stretch.py only sees what later tools move. Here both
cloths are unrolled the same way (project_print.Frame and print_map: per side, relative height by angle around the leg,
the outermost layer) and the side stripes are compared row by row, from STRIPE_T[0] to STRIPE_T[1] of the height:
  width: median arc length of the stripes (the white within project_print.STRIPES of the outer side), new over old, in
         WIDTH, above project_print.SOURCE_HEM: the stripes keep the source's width on the wider legs;
  rows:  share of the rows with stripes, at least MIN_ROWS: no stretch of leg without them (the seam where the hip met
         the legs broke them; at the hem, the source's fold over the shoe turned them sideways);
  jump:  p99 of the step of the stripes' middle from one row (1 mm) to the next, at most MAX_JUMP (no jag), and the
         largest step at most MAX_BREAK (the seam where the hip met the legs moved them 2.7 cm in one row);
  inner: white on the inner half of each leg below the crotch (more than 110° from the outer side), at most MAX_INNER
         of that area: the other leg's stripes stay on the other leg.
usage: python3 tools/fit/print_check.py [IDs]"""
import os, sys, numpy as np
from paths import GARMENTS
from project_print import Frame, print_map, print_source, STRIPES, WHITE, MAP, SOURCE_HEM

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PRINT_SOURCE = 'tools/fit/reference/originals/print-source'
PROJECTED = {
    '014',
}
STRIPE_T = (.02, .88)   # down to the hem (where the source folded over the shoe and the stripes ran sideways); the waistband out
INNER_T = (.08, .7)     # below the crotch
WIDTH = (.85, 1.15)
MIN_ROWS = .97
MAX_JUMP = .003          # metres
MAX_BREAK = .01
MAX_INNER = .005


def measure(path):
    m, uv, img = print_source(path); F = Frame(m.vertices)
    NT, NA = MAP; a = np.linspace(-np.pi, np.pi, NA); t = np.linspace(0, 1, NT)
    out = {}
    for s in (1, -1):
        cmap, _ = print_map(m, uv, img, F, s)
        white = cmap.min(2) > WHITE
        R = F.radius(t, s)[:, None]
        band = white & (a >= STRIPES[0]) & (a <= STRIPES[1])
        rows = (t >= STRIPE_T[0]) & (t <= STRIPE_T[1])
        arc = band.sum(1) * R[:, 0] * (2 * np.pi / NA)
        has = band.sum(1) > 3
        mid = np.where(has, (band * a).sum(1) / np.maximum(band.sum(1), 1), np.nan) * R[:, 0]
        k = rows & has; i = np.flatnonzero(k)
        step = np.abs(np.diff(mid[i]))[np.diff(i) == 1]
        inner = (t >= INNER_T[0]) & (t <= INNER_T[1])
        kw = k & (t >= SOURCE_HEM)   # the source's fold over the shoe has the stripes sideways, wider
        out[s] = dict(width=np.median(arc[kw]) if kw.any() else 0., rows=has[rows].mean(),
                      jump=np.percentile(step, 99) if len(step) else 1., brk=step.max() if len(step) else 1.,
                      inner=white[inner][:, np.abs(a) > np.radians(110)].mean())
    return out


if __name__ == '__main__':
    bad = []
    for pid in sys.argv[1:] or sorted(PROJECTED):
        new, old = measure(GARMENTS + f'{pid}.glb'), measure(os.path.join(ROOT, PRINT_SOURCE, f'{pid}.glb'))
        for s in (1, -1):
            n, o = new[s], old[s]; w = n['width'] / max(o['width'], 1e-9)
            print(f"{pid} leg {s:+d}: stripes {100 * n['width']:.1f} cm wide ({100 * o['width']:.1f} in the source, x{w:.2f}), "
                  f"in {100 * n['rows']:.0f}% of the rows, step p99 {1000 * n['jump']:.1f} mm (source {1000 * o['jump']:.1f}), "
                  f"largest {1000 * n['brk']:.1f} mm, white inside {100 * n['inner']:.2f}%")
            bad += [f'{pid} leg {s:+d} stripes x{w:.2f} the source width'] * bool(not WIDTH[0] <= w <= WIDTH[1])
            bad += [f"{pid} leg {s:+d} stripes in {100 * n['rows']:.0f}% of the rows < {100 * MIN_ROWS:.0f}%"] * bool(n['rows'] < MIN_ROWS)
            bad += [f"{pid} leg {s:+d} stripes step {1000 * n['jump']:.1f} mm > {1000 * MAX_JUMP:.0f}"] * bool(n['jump'] > MAX_JUMP)
            bad += [f"{pid} leg {s:+d} stripes break {1000 * n['brk']:.1f} mm > {1000 * MAX_BREAK:.0f}"] * bool(n['brk'] > MAX_BREAK)
            bad += [f"{pid} leg {s:+d} white inside {100 * n['inner']:.2f}% > {100 * MAX_INNER:.1f}%"] * bool(n['inner'] > MAX_INNER)
    if bad: sys.exit('projected print off its source: ' + ', '.join(bad))
