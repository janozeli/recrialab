// Checks the bundle in dist/ before publishing. Usage: bun verify-dist.ts [--stamp] [--require-clean]
import { execSync } from 'node:child_process';
import { readdirSync, readFileSync, statSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

const DIST = new URL('./dist/', import.meta.url).pathname;
const MAX_FILE_BYTES = 8 * 1024 * 1024;
const MAX_TOTAL_BYTES = 160 * 1024 * 1024;
const MAX_ENTRY_JS_BYTES = 1.5 * 1024 * 1024;   // masks are packed run lists, so the entry stays small
// _redirects: Workers static assets rules (the old /memorial leads to /sobre).
const ENTRIES = ['index.html', 'sobre.html', '_redirects'];
const args = new Set(process.argv.slice(2));
const errors: string[] = [];

const git = (cmd: string) => execSync(`git ${cmd}`, { encoding: 'utf8' }).trim();
const commit = process.env.GITHUB_SHA ?? git('rev-parse HEAD');
const dirty = !process.env.GITHUB_SHA && git('status --porcelain -- .') !== '';
if (args.has('--require-clean') && dirty) errors.push('site/ has uncommitted changes: publish only what is in git');

const files = readdirSync(DIST).filter(f => f !== 'build.json');
let total = 0;
for (const f of files) {
  const size = statSync(join(DIST, f)).size;
  total += size;
  if (size > MAX_FILE_BYTES) errors.push(`${f}: ${(size / 1048576).toFixed(1)} MiB (limit 8 MiB per file)`);
  if (/^index-.*\.js$/.test(f) && size > MAX_ENTRY_JS_BYTES) errors.push(`${f}: entry JS of ${(size / 1048576).toFixed(1)} MiB`);
}
if (total > MAX_TOTAL_BYTES) errors.push(`dist/ has ${(total / 1048576).toFixed(0)} MiB (limit 160)`);
for (const entry of ENTRIES) if (!files.includes(entry)) errors.push(`missing ${entry}`);

// Every file must be referenced by HTML, JS or CSS: leftovers of an old build are not published.
const text = files.filter(f => /\.(html|js|css)$/.test(f)).map(f => readFileSync(join(DIST, f), 'utf8')).join('\n');
for (const f of files) if (!ENTRIES.includes(f) && !text.includes(f)) errors.push(`${f}: not used by any page`);

if (errors.length) {
  console.error(`dist/ rejected:\n- ${errors.join('\n- ')}`);
  process.exit(1);
}
if (args.has('--stamp')) writeFileSync(join(DIST, 'build.json'), JSON.stringify({ commit, dirty }) + '\n');
console.log(`dist/ ok: ${files.length} files, ${(total / 1048576).toFixed(1)} MiB, commit ${commit.slice(0, 7)}${dirty ? ' (with local changes)' : ''}`);
