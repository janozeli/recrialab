"""Layer tables (site/assets/layers/NNN.json): one per bottom garment, one line per top.
Each pair is derived from the two GLBs only (gen_layers.pair), and the table stores the hash of each. With one line
per top, git merges on its own two PRs that change different tops. The pair of a top and a bottom that changed in
different PRs always conflicts, and is not resolved by hand:

    python3 tools/fit/layer_tables.py      (after `git merge`, with or without a conflict in the tables)

A conflicting table goes back whole to the side that already has the current bottom (hash and pair go together).
After that, every pair whose hash does not match the current GLB is rebuilt: if the top changed, only its line is
rebuilt (about 15 s); if the bottom changed, the whole table. Each table also stores the hash of gen_layers.py, so a
change to the rule rebuilds all 15 tables (and nothing is left built by the old rule). site/layers.test.ts fails a
table written in another format, and site/integrity.test.ts fails a stale hash. With --check, only lists what is stale (exit 1 if anything)."""
import json, os, sys, hashlib, subprocess

c = lambda v: json.dumps(v, separators=(',', ':'))
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '../..')
from paths import GARMENTS, LAYERS
sha = lambda p: hashlib.sha256(open(p, 'rb').read()).hexdigest()
GENERATOR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'gen_layers.py')


def text(t):
    lines = lambda d: ',\n'.join(f'{c(k)}:{c(d[k])}' for k in sorted(d))
    return (f'{{"bottomHash":{c(t["bottomHash"])},\n"generatorHash":{c(t["generatorHash"])},\n"meshes":{c(t["meshes"])},\n'
            f'"topHashes":{{\n{lines(t["topHashes"])}\n}},\n"pairs":{{\n{lines(t["pairs"])}\n}}}}\n')


def save(path, t):
    assert set(t) == {'bottomHash', 'generatorHash', 'meshes', 'topHashes', 'pairs'}, sorted(t)
    s = text(t); assert json.loads(s) == t
    open(path, 'w').write(s)


def conflicted():
    out = subprocess.run(['git', 'diff', '--name-only', '--diff-filter=U'], cwd=ROOT, capture_output=True, text=True).stdout
    return {os.path.basename(f) for f in out.split() if f.startswith('site/assets/layers/')}


def main(args):
    conflict = conflicted()
    for f in sorted(conflict):   # one whole side: the one that already has the current bottom (only tops to rebuild)
        sides = [json.loads(subprocess.run(['git', 'show', f':{n}:site/assets/layers/{f}'], cwd=ROOT, capture_output=True,
                                           text=True, check=True).stdout) for n in (2, 3)]
        current = sha(GARMENTS + f'{f[:3]}.glb')
        t = next((t for t in sides if t['bottomHash'] == current), sides[1])
        save(LAYERS + f, {'generatorHash': '', **t})   # a side from before generatorHash: rebuilt whole below
    tops = [f'{i:03d}' for i in range(16, 39)]
    hashes = {id: sha(GARMENTS + f'{id}.glb') for id in tops}
    redo = {}; generator = sha(GENERATOR)
    for n in range(1, 16):
        bid = f'{n:03d}'; t = json.load(open(LAYERS + f'{bid}.json'))
        if t['bottomHash'] != sha(GARMENTS + f'{bid}.glb') or t.get('generatorHash') != generator:
            redo[bid] = None   # None: the whole table
        else:
            stale = [id for id in tops if t['topHashes'].get(id) != hashes[id]]
            if stale: redo[bid] = stale
        if bid not in redo: save(LAYERS + f'{bid}.json', t)   # the format only
    for bid, ids in redo.items(): print(bid, 'whole table' if ids is None else 'pairs ' + ' '.join(ids), flush=True)
    if not redo or '--check' in args: return 1 if redo and '--check' in args else 0
    from garment import Garment
    from gen_layers import pair
    meshes = {}
    for bid, ids in redo.items():
        path = LAYERS + f'{bid}.json'; t = json.load(open(path))
        bottom = Garment(GARMENTS + f'{bid}.glb')
        if ids is None:
            t.update(bottomHash=sha(GARMENTS + f'{bid}.glb'), generatorHash=generator, meshes=[
                {'vertices': s, 'triangles': bottom.js['accessors'][p['indices']]['count'] // 3}
                for s, (a, M, p) in zip(bottom.sizes, bottom.parts)])
            ids = tops
        for id in ids:
            if id not in meshes: meshes[id] = Garment(GARMENTS + f'{id}.glb').mesh()
            t['pairs'][id] = pair(bottom, meshes[id]); t['topHashes'][id] = hashes[id]
        save(path, t); print(bid, 'layers ok', flush=True)
    if conflict: subprocess.run(['git', 'add', '--'] + [f'site/assets/layers/{f}' for f in conflict], cwd=ROOT, check=True)
    return 0


if __name__ == '__main__':
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    sys.exit(main(sys.argv[1:]))
