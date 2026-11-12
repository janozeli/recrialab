// Looks sent from the fitting room reach the team: what the form accepts, what the server keeps and who may read it.
import { expect, test } from 'bun:test';
import { readFileSync } from 'node:fs';
import { aboutLookLine, checkSentLook, INBOX_LIMITS, INBOX_PATH, LAST_BOTTOM, LAST_PIECE } from './look-inbox';
import { CATALOG } from './catalog-data';
import { handle, INBOX_KEY_SHA256, LookInbox, MAX_STORED, type InboxStorage, type StoredLook } from './inbox-server';

const KEY = 'a key only this test knows';

function memory(): InboxStorage & { data: Map<string, unknown> } {
  const data = new Map<string, unknown>();
  return {
    data,
    get: async <T>(key: string) => data.get(key) as T | undefined,
    put: async (key, value) => { data.set(key, value); },
    list: async <T>({ prefix }: { prefix: string }) => new Map([...data].filter(([key]) => key.startsWith(prefix)) as [string, T][]),
    delete: async key => data.delete(key),
  };
}
function server(storage = memory()) {
  const inbox = new LookInbox({ storage });
  const env = { INBOX: { idFromName: (name: string) => name, get: () => inbox } };
  const post = (body: unknown, headers: Record<string, string> = {}) => handle(new Request(`https://recrialab.com${INBOX_PATH}`, {
    method: 'POST', headers: { 'content-type': 'application/json', origin: 'https://recrialab.com', ...headers },
    body: typeof body === 'string' ? body : JSON.stringify(body),
  }), env);
  const read = (key?: string) => handle(new Request(`https://recrialab.com${INBOX_PATH}`, key ? { headers: { authorization: `Bearer ${key}` } } : {}), env);
  const remove = (key?: string, body = '{}') => handle(new Request(`https://recrialab.com${INBOX_PATH}`,
    { method: 'DELETE', body, headers: key ? { authorization: `Bearer ${key}` } : {} }), env);
  return { storage, env, inbox, post, read, remove };
}
const sha256 = async (text: string) => [...new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text)))]
  .map(b => b.toString(16).padStart(2, '0')).join('');

test('a sent look is normalised: sorted code, one line per field, nickname required', () => {
  expect(checkSentLook({ look: '024.004', credit: '  Bia \n M. ', group: '2B', name: 'Domingo', note: 'tem\ta minha cara' }))
    .toEqual({ ok: true, look: { look: '004.024', credit: 'Bia M.', group: '2B', name: 'Domingo', note: 'tem a minha cara' } });
  expect(checkSentLook({ look: '024', credit: 'B' })).toEqual({ ok: true, look: { look: '024', credit: 'B', group: '', name: '', note: '' } });
  // A piece that is not in the collection, two tops or two bottoms: not a look the mannequin wears.
  for (const bad of [null, 'x', {}, { look: '', credit: 'B' }, { look: 'abc', credit: 'B' }, { look: '001.002.003', credit: 'B' },
    { look: '999', credit: 'B' }, { look: '000', credit: 'B' }, { look: '004.039', credit: 'B' }, { look: '016.017', credit: 'B' }, { look: '004.005', credit: 'B' },
    { look: '004', credit: '   ' }, { look: '004', credit: 'B', note: 'x'.repeat(INBOX_LIMITS.note + 1) }, { look: '004', credit: 'x'.repeat(INBOX_LIMITS.credit + 1) }]) {
    expect(checkSentLook(bad).ok, JSON.stringify(bad)).toBe(false);
  }
});

test('the server keeps a valid look once and refuses what is not from the form', async () => {
  const { storage, post } = server();
  const look = { look: '004.024', credit: 'Bia', group: '2B', name: 'Domingo', note: 'tem a minha cara' };
  expect((await post(look)).status).toBe(200);
  expect((await post(look)).status).toBe(200);   // a second tap or a retry
  expect((await post({ ...look, credit: 'Leo' })).status).toBe(200);
  const kept = [...storage.data].filter(([key]) => key.startsWith('look:')).map(([, value]) => value as StoredLook);
  expect(kept.map(k => k.credit).sort()).toEqual(['Bia', 'Leo']);
  expect(kept.every(k => !Number.isNaN(Date.parse(k.at)))).toBe(true);
  expect(storage.data.get('count')).toBe(2);
  expect((await post({ look: '004' })).status).toBe(400);
  expect((await post('{not json')).status).toBe(400);
  expect((await post({ ...look, note: 'x'.repeat(5000) })).status).toBe(413);
  expect((await post(look, { origin: 'https://example.com' })).status).toBe(403);
  // The form always sends its origin: a request without one is not the form.
  expect((await handle(new Request(`https://recrialab.com${INBOX_PATH}`, { method: 'POST', body: JSON.stringify({ ...look, credit: 'Ana' }) }), server(storage).env)).status).toBe(403);
  // Size is counted in bytes: 2000 characters of 3 bytes each do not pass as 2000.
  expect((await post({ ...look, note: 'あ'.repeat(2000) })).status).toBe(413);
  expect([...storage.data.keys()].filter(key => key.startsWith('look:')).length).toBe(2);
});

test('the collection the server knows is the catalog: bottoms first, then tops', () => {
  expect(CATALOG.filter(p => p.slot === 'bottom').map(p => p.id)).toEqual(Array.from({ length: LAST_BOTTOM }, (_, i) => String(i + 1).padStart(3, '0')));
  expect(CATALOG.filter(p => p.slot === 'top').map(p => p.id)).toEqual(Array.from({ length: LAST_PIECE - LAST_BOTTOM }, (_, i) => String(LAST_BOTTOM + i + 1).padStart(3, '0')));
});

test('the team takes a test or junk out of the inbox, one look or all, and the count follows', async () => {
  const { storage, inbox, remove } = server();
  const stored = (credit: string, at: string): StoredLook => ({ look: '004', credit, group: '', name: '', note: '', at });
  storage.data.set('look:a', stored('Bia', '2026-11-13T14:01:00.000Z'));
  storage.data.set('look:b', stored('teste', '2026-11-13T14:02:00.000Z'));
  storage.data.set('look:c', stored('Leo', '2026-11-13T14:03:00.000Z'));
  storage.data.set('count', 3);
  expect((await remove()).status).toBe(401);
  expect((await remove(KEY)).status).toBe(401);
  expect(storage.data.size).toBe(4);
  const call = (at?: string[]) => inbox.fetch(new Request('https://inbox/', { method: 'DELETE', body: JSON.stringify({ at }) })).then(r => r.json());
  expect(await call(['2026-11-13T14:02:00.000Z'])).toEqual({ removed: 1, kept: 2 });
  expect([...storage.data.values()].filter(v => typeof v === 'object').map(v => (v as StoredLook).credit).sort()).toEqual(['Bia', 'Leo']);
  expect(storage.data.get('count')).toBe(2);
  expect(await call()).toEqual({ removed: 2, kept: 0 });
  expect(storage.data.get('count')).toBe(0);
});

test('a full inbox refuses new looks instead of growing without end', async () => {
  const { storage, post } = server();
  storage.data.set('count', MAX_STORED);
  expect((await post({ look: '004', credit: 'Bia' })).status).toBe(507);
});

test('only the team key reads the inbox, oldest look first', async () => {
  const { storage, env, read } = server();
  storage.data.set('look:b', { look: '024', credit: 'Leo', group: '', name: '', note: '', at: '2026-11-13T14:05:00.000Z' });
  storage.data.set('look:a', { look: '004', credit: 'Bia', group: '', name: '', note: '', at: '2026-11-13T14:01:00.000Z' });
  expect((await read()).status).toBe(401);
  expect((await read(KEY)).status).toBe(401);
  // The repository holds only the hash of the real key: reading needs the key itself.
  expect(INBOX_KEY_SHA256).toMatch(/^[0-9a-f]{64}$/);
  expect(INBOX_KEY_SHA256).not.toBe(await sha256(KEY));
  const inbox = env.INBOX.get();
  const { looks } = await (await inbox.fetch(new Request('https://inbox/'))).json() as { looks: StoredLook[] };
  expect(looks.map(l => l.credit)).toEqual(['Bia', 'Leo']);
});

test('other paths under /api do not exist and other methods are refused', async () => {
  const { env } = server();
  expect((await handle(new Request('https://recrialab.com/api/other'), env)).status).toBe(404);
  expect((await handle(new Request(`https://recrialab.com${INBOX_PATH}`, { method: 'PUT' }), env)).status).toBe(405);
});

test('a received look becomes an about-data.ts entry, with the workshop day in São Paulo time', () => {
  expect(aboutLookLine({ look: '004.024', credit: "Bia d'A", group: '2B', name: 'Domingo', note: 'tem a minha cara', at: '2026-11-14T01:30:00.000Z' }))
    .toBe("    { look: '004.024', credit: 'Bia d\\'A, 2B', workshop: '2026-11-13', note: 'Domingo: tem a minha cara' },");
});

test('only /api/* runs the Worker: the pages stay static assets, and the inbox needs no resource made by hand', () => {
  const config = JSON.parse(readFileSync(new URL('./wrangler.jsonc', import.meta.url), 'utf8').replace(/^\s*\/\/.*$/gm, ''));
  expect(config.main).toBe('./worker.ts');
  expect(config.assets.run_worker_first).toEqual(['/api/*']);
  expect(config.durable_objects.bindings).toEqual([{ name: 'INBOX', class_name: 'LookInbox' }]);
  expect(config.migrations.flatMap((m: { new_sqlite_classes?: string[] }) => m.new_sqlite_classes ?? [])).toContain('LookInbox');
  expect(Object.keys(config).filter(k => /kv_namespaces|d1_databases|r2_buckets/.test(k))).toEqual([]);
});

test('the Worker entry exports only what the runtime accepts: the handler and the Durable Object class', async () => {
  const entry = await import('./worker');
  expect(Object.keys(entry).sort()).toEqual(['LookInbox', 'default']);
  expect(typeof entry.default.fetch).toBe('function');
});

test('the form and the server share the same limits', () => {
  const html = readFileSync(new URL('./index.html', import.meta.url), 'utf8');
  for (const field of Object.keys(INBOX_LIMITS)) expect(html, field).toContain(`id="send-${field}"`);
  expect(html).toContain('id="send-credit" name="credit" required');
});
