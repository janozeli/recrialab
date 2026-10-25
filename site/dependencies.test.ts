// Every import of the Python scripts in tools/fit and tools/visual-qa is in the folder's requirements.txt: a clean
// environment must be able to run them.
import { test, expect } from 'bun:test';
import { spawnSync } from 'node:child_process';

const ROOT = new URL('../', import.meta.url).pathname;
const PACKAGE: Record<string, string> = { pillow: 'PIL', 'warp-lang': 'warp' };   // pip name → import name

const PY = `
import ast, sys, glob, os, json
folder = sys.argv[1]
local = {os.path.basename(f)[:-3] for f in glob.glob(folder + '/../*/*.py')}   # tools/fit imports measure from tools/visual-qa
outside = {}
for f in sorted(glob.glob(folder + '/*.py')):
    for n in ast.walk(ast.parse(open(f).read())):
        mods = [a.name for a in n.names] if isinstance(n, ast.Import) else [n.module] if isinstance(n, ast.ImportFrom) and n.level == 0 and n.module else []
        for m in mods:
            m = m.split('.')[0]
            if m not in sys.stdlib_module_names and m not in local: outside.setdefault(m, []).append(os.path.basename(f))
print(json.dumps(outside))
`;

for (const folder of ['tools/fit', 'tools/visual-qa']) {
  test(`imports of ${folder} are in requirements.txt`, async () => {
    const r = spawnSync('python3', ['-c', PY, ROOT + folder], { encoding: 'utf8' });
    expect(r.stderr).toBe('');
    const used: Record<string, string[]> = JSON.parse(r.stdout);
    const req = (await Bun.file(`${ROOT}${folder}/requirements.txt`).text()).split('\n').map(l => l.split(/[=<>\[ ]/)[0].trim().toLowerCase()).filter(Boolean);
    const allowed = new Set(req.map(p => PACKAGE[p] ?? p));
    const missing = Object.fromEntries(Object.entries(used).filter(([m]) => !allowed.has(m)));
    expect(missing).toEqual({});
  });
}
