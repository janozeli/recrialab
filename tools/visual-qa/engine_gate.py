"""Which garments may go on the site in the fit engine's version: none whose looks get worse than the published ones.

  python3 tools/visual-qa/engine_gate.py PUBLISHED ENGINE [--sheet WORK/sheet/sheet.json]

PUBLISHED and ENGINE are folders measured by measure.py over the same looks, photographed by
tools/verify-site/visual-qa.mjs without and with --engine (the engine run with every garment off hold). A look is
worse when a measure is above its limit with the engine and above the published value by more than a tenth of the
limit. Garments are then put on hold, the one with the most worse looks first, until no look of two engine garments
is worse; a garment flagged by the engine sheet (silhouette, print or body crossing against the published garment)
is held too. Prints the lines for site/engine-hold.ts and exits 1 if a garment held here is missing there.
"""
import json, os, re, sys
from measure import LIMITS, ROOT


def worse_looks(published, engine):
    out = {}
    for look, e in engine.items():
        p = published.get(look, {}).get('measures', {})
        bad = {k: (p.get(k), v) for k, v in e['measures'].items()
               if v > LIMITS[k] and v > (p.get(k) or 0) + LIMITS[k] / 10}
        if bad: out[look] = bad
    return out


def hold(worse, flagged):
    """Greedy cover: the garment in the most worse looks goes on hold until every worse look has one held."""
    held = {g: 'engine sheet: ' + ', '.join(f) for g, f in flagged.items()}
    left = {look: bad for look, bad in worse.items() if not set(look.split('.')) & set(held)}
    while left:
        count = {}
        for look in left:
            for g in look.split('.'): count[g] = count.get(g, 0) + 1
        g = max(sorted(count), key=count.get)
        mine = {look: bad for look, bad in left.items() if g in look.split('.')}
        look, bad = max(mine.items(), key=lambda kv: max(e / LIMITS[k] for k, (_, e) in kv[1].items()))
        k, (p, e) = max(bad.items(), key=lambda kv: kv[1][1] / LIMITS[kv[0]])
        held[g] = f'{len(mine)} look{"s" if len(mine) > 1 else ""} worse than published, worst {look} {k} {e} (published {p}, limit {LIMITS[k]})'
        left = {look: bad for look, bad in left.items() if g not in look.split('.')}
    return dict(sorted(held.items()))


def main():
    published, engine = (json.load(open(os.path.join(d, 'visual-qa.json'))) for d in sys.argv[1:3])
    flagged = {}
    if '--sheet' in sys.argv:
        sheet = json.load(open(sys.argv[sys.argv.index('--sheet') + 1]))
        flagged = {g['id']: g['flags'] for g in sheet['garments'] if g['flags']}
    missing = sorted(set(engine) - set(published))
    if missing: sys.exit(f'looks measured with the engine only: {", ".join(missing[:8])}')
    worse = worse_looks(published, engine)
    held = hold(worse, flagged)
    print(f'{len(engine)} looks, {len(worse)} worse with the engine; {len(held)} garments on hold')
    for g, why in held.items(): print(f"  '{g}': '{why}',")
    listed = set(re.findall(r"'(\d{3})':", open(f'{ROOT}/site/engine-hold.ts', encoding='utf8').read()))
    out = sorted(set(held) - listed)
    if out: sys.exit(f'not on hold in site/engine-hold.ts: {", ".join(out)}')


if __name__ == '__main__':
    main()
