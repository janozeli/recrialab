/**
 * Reads the looks sent from the fitting room and prints `looks` entries for about-data.ts.
 * Usage: `RECRIALAB_INBOX_KEY=... bun inbox.ts [--json] [--url https://recrialab.com]`
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
const response = await fetch(`${base}${INBOX_PATH}`, { headers: { authorization: `Bearer ${key}` } });
if (!response.ok) {
  console.error(`${base}${INBOX_PATH}: HTTP ${response.status}`);
  process.exit(1);
}
const { looks } = await response.json() as { looks: StoredLook[] };
if (args.includes('--json')) console.log(JSON.stringify(looks, null, 2));
else for (const look of looks) console.log(aboutLookLine(look));
console.error(`${looks.length} look${looks.length === 1 ? '' : 's'}`);
