/**
 * Reads the looks sent from the fitting room and prints `looks` entries for about-data.ts.
 * Usage: `RECRIALAB_INBOX_KEY=... bun inbox.ts [--json] [--url https://recrialab.com]`
 * Taking looks out (a test, junk): `--delete <time>...` with the `at` of each, as `--json` shows, or `--delete-all`.
 */
import { aboutLookLine, INBOX_PATH } from './look-inbox';
import type { StoredLook } from './inbox-server';

const args = process.argv.slice(2);
const base = args.includes('--url') ? args[args.indexOf('--url') + 1] : 'https://recrialab.com';
const key = process.env.RECRIALAB_INBOX_KEY;
if (!key) {
  console.error('set RECRIALAB_INBOX_KEY to the key that reads the inbox');
  process.exit(1);
}
const call = async (init: RequestInit = {}) => {
  const response = await fetch(`${base}${INBOX_PATH}`, { ...init, headers: { authorization: `Bearer ${key}`, 'content-type': 'application/json' } });
  if (!response.ok) {
    console.error(`${base}${INBOX_PATH}: HTTP ${response.status}`);
    process.exit(1);
  }
  return response.json();
};
if (args.includes('--delete') || args.includes('--delete-all')) {
  const at = args.includes('--delete-all') ? undefined : args.slice(args.indexOf('--delete') + 1).filter(a => !a.startsWith('--'));
  if (at && !at.length) {
    console.error('--delete needs the time of each look to take out (the `at` shown by --json)');
    process.exit(1);
  }
  const { removed, kept } = await call({ method: 'DELETE', body: JSON.stringify({ at }) }) as { removed: number; kept: number };
  console.error(`${removed} removed, ${kept} kept`);
} else {
  const { looks } = await call() as { looks: StoredLook[] };
  if (args.includes('--json')) console.log(JSON.stringify(looks, null, 2));
  else for (const look of looks) console.log(aboutLookLine(look));
  console.error(`${looks.length} look${looks.length === 1 ? '' : 's'}`);
}
