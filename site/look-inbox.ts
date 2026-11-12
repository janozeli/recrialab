/** A look sent from the fitting room to the team: the pieces worn and what the author wrote about it. */
import { encodeLook, parseLook } from './look-code';

export const INBOX_PATH = '/api/looks';
/** Longest text accepted in each field, in characters. The form and the server share these. */
export const INBOX_LIMITS = { credit: 30, group: 12, name: 40, note: 160 } as const;
/**
 * The collection, as the server needs it (catalog-data.ts imports the pictures, which the Worker cannot bundle):
 * bottoms are 001 to LAST_BOTTOM, tops go on to LAST_PIECE. look-inbox.test.ts holds this to the catalog.
 */
export const LAST_BOTTOM = 15;
export const LAST_PIECE = 38;

export interface SentLook {
  /** Look code, as in `?look=` (e.g. `004.024`). */
  look: string;
  /** Nickname or initials of the author, never a full name. */
  credit: string;
  /** School class. */
  group: string;
  /** Name the author gave the look. */
  name: string;
  /** Why the look suits the author. */
  note: string;
}

/** One line of text: no control characters, single spaces, trimmed. */
function line(value: unknown): string {
  return typeof value === 'string' ? value.replace(/[\u0000-\u001f\u007f]+/g, ' ').replace(/\s+/g, ' ').trim() : '';
}

/** The look as it is stored, or the reason it is refused. Runs on the form and again on the server. */
export function checkSentLook(input: unknown): { ok: true; look: SentLook } | { ok: false; error: string } {
  if (!input || typeof input !== 'object') return { ok: false, error: 'not an object' };
  const raw = input as Record<string, unknown>;
  const pieces = parseLook(typeof raw.look === 'string' ? raw.look : '');
  // Pieces of the collection only, and at most one top and one bottom, as the mannequin wears.
  const numbers = pieces.map(Number);
  const bottoms = numbers.filter(n => n <= LAST_BOTTOM).length;
  if (!pieces.length || numbers.some(n => n < 1 || n > LAST_PIECE) || bottoms > 1 || pieces.length - bottoms > 1) return { ok: false, error: 'look' };
  const look: SentLook = { look: encodeLook(pieces), credit: line(raw.credit), group: line(raw.group), name: line(raw.name), note: line(raw.note) };
  if (!look.credit) return { ok: false, error: 'credit' };
  for (const field of ['credit', 'group', 'name', 'note'] as const) {
    if (look[field].length > INBOX_LIMITS[field]) return { ok: false, error: field };
  }
  return { ok: true, look };
}

/** Entry for the `looks` list of about-data.ts, as about-look.ts prints for a saved image. */
export function aboutLookLine(sent: SentLook & { at?: string }): string {
  const quote = (text: string) => `'${text.replace(/\\/g, '\\\\').replace(/'/g, "\\'")}'`;
  const credit = [sent.credit, sent.group].filter(Boolean).join(', ');
  const note = [sent.name, sent.note].filter(Boolean).join(': ');
  // The workshop is the day the look arrived, in the time of the school (São Paulo).
  const workshop = sent.at ? `, workshop: ${quote(new Date(sent.at).toLocaleDateString('sv-SE', { timeZone: 'America/Sao_Paulo' }))}` : '';
  return `    { look: ${quote(sent.look)}, credit: ${quote(credit)}${workshop}, note: ${quote(note)} },`;
}
