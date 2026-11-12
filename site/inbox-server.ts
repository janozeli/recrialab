/** Receives the looks sent from the fitting room and keeps them for the team. Runs in the Worker (worker.ts). */
import { checkSentLook, INBOX_PATH, type SentLook } from './look-inbox';

/** SHA-256 of the key that reads the inbox. The key itself stays with the team, outside the repository. */
export const INBOX_KEY_SHA256 = '269fb8188c76335566614c455f1e01424b60d03dacb096f9ddcf509c8cad55bc'; // gitleaks:allow (a hash: the key cannot be read back from it)
/** A sent look is a few short fields; anything larger is not from the form. */
const MAX_BODY_BYTES = 4096;
/** Looks kept at most; past this the inbox refuses new ones until the team empties it. */
export const MAX_STORED = 5000;
const ORIGINS = /^https?:\/\/((www\.)?recrialab\.com|localhost(:\d+)?|127\.0\.0\.1(:\d+)?)$/;

export type StoredLook = SentLook & { at: string };

/** The part of Durable Object storage the inbox uses. */
export interface InboxStorage {
  get<T>(key: string): Promise<T | undefined>;
  put<T>(key: string, value: T): Promise<void>;
  list<T>(options: { prefix: string; limit?: number }): Promise<Map<string, T>>;
}
interface InboxStub { fetch(request: Request): Promise<Response> }
interface Env {
  INBOX: { idFromName(name: string): unknown; get(id: unknown): InboxStub };
  ASSETS?: { fetch(request: Request): Promise<Response> };
}

const json = (body: unknown, status = 200): Response => new Response(JSON.stringify(body), {
  status,
  headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' },
});

async function sha256(text: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return [...new Uint8Array(digest)].map(b => b.toString(16).padStart(2, '0')).join('');
}

/** The inbox itself: one Durable Object holds every look sent, so no resource has to be created by hand. */
export class LookInbox {
  private storage: InboxStorage;
  constructor(state: { storage: InboxStorage }) {
    this.storage = state.storage;
  }

  async fetch(request: Request): Promise<Response> {
    if (request.method === 'GET') {
      const looks = [...(await this.storage.list<StoredLook>({ prefix: 'look:', limit: MAX_STORED })).values()];
      return json({ looks: looks.sort((a, b) => a.at.localeCompare(b.at)) });
    }
    const look = await request.json() as SentLook;
    // The same look sent twice (a second tap, a retry on a bad connection) is kept once.
    const key = `look:${await sha256(JSON.stringify([look.look, look.credit, look.group, look.name, look.note]))}`;
    if (await this.storage.get(key)) return json({ ok: true });
    const count = (await this.storage.get<number>('count')) ?? 0;
    if (count >= MAX_STORED) return json({ error: 'full' }, 507);
    await this.storage.put<StoredLook>(key, { ...look, at: new Date().toISOString() });
    await this.storage.put('count', count + 1);
    return json({ ok: true });
  }
}

export async function handle(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  if (url.pathname !== INBOX_PATH) return env.ASSETS && !url.pathname.startsWith('/api/') ? env.ASSETS.fetch(request) : json({ error: 'not found' }, 404);
  const inbox = env.INBOX.get(env.INBOX.idFromName('looks'));
  if (request.method === 'GET') {
    const key = request.headers.get('authorization')?.replace(/^Bearer\s+/i, '') ?? '';
    if (!key || await sha256(key) !== INBOX_KEY_SHA256) return json({ error: 'unauthorized' }, 401);
    return inbox.fetch(new Request('https://inbox/', { method: 'GET' }));
  }
  if (request.method !== 'POST') return json({ error: 'method' }, 405);
  // A form on another site cannot fill the inbox through a visitor's browser.
  const origin = request.headers.get('origin');
  if (origin && !ORIGINS.test(origin)) return json({ error: 'origin' }, 403);
  const body = await request.text();
  if (body.length > MAX_BODY_BYTES) return json({ error: 'too large' }, 413);
  let input: unknown;
  try { input = JSON.parse(body); } catch { return json({ error: 'json' }, 400); }
  const checked = checkSentLook(input);
  if (!checked.ok) return json({ error: checked.error }, 400);
  return inbox.fetch(new Request('https://inbox/', { method: 'POST', body: JSON.stringify(checked.look) }));
}
