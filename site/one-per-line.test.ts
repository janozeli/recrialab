// Pieces in a dict, set or list of tools/fit and tools/visual-qa stay one per line: two changes to different pieces
// touch different lines and git merges them on its own.
import { test, expect } from 'bun:test';
import { spawnSync } from 'node:child_process';

const ROOT = new URL('../', import.meta.url).pathname;
const PY = `
import ast, glob, re, sys, json
offenders = []
for f in sorted(glob.glob(sys.argv[1] + 'tools/fit/*.py') + glob.glob(sys.argv[1] + 'tools/visual-qa/*.py')):
    for n in ast.walk(ast.parse(open(f).read())):
        ks = n.keys if isinstance(n, ast.Dict) else n.elts if isinstance(n, (ast.Set, ast.List, ast.Tuple)) else []
        ids = [k for k in ks if isinstance(k, ast.Constant) and isinstance(k.value, str) and re.fullmatch(r'\\d{3}(\\.\\d{3})?', k.value)]
        if len(ids) >= 2 and len({k.lineno for k in ids}) < len(ids):
            offenders.append(f'{f[len(sys.argv[1]):]}:{n.lineno}')
print(json.dumps(offenders))
`;

test('one piece per line in tools/fit and tools/visual-qa', () => {
  const r = spawnSync('python3', ['-c', PY, ROOT], { encoding: 'utf8' });
  expect(r.stderr).toBe('');
  expect(JSON.parse(r.stdout)).toEqual([]);
});
