import { CATALOG } from './catalog-data';
import { encodeLook, parseLook } from './look-code';

type Piece = (typeof CATALOG)[number];
const BY_ID = new Map<string, Piece>(CATALOG.map(p => [p.id, p]));

/** Pieces of the look in wearing order (top first); unknown ids are left out. */
export function lookPieces(code: string): Piece[] {
  return parseLook(code)
    .map(id => BY_ID.get(id))
    .filter((p): p is Piece => !!p)
    .sort((a, b) => (a.slot === 'top' ? 0 : 1) - (b.slot === 'top' ? 0 : 1));
}

/** Same label as the exported PNG (`LOOK 004 + 024`). */
export const lookLabel = (code: string) => `LOOK ${parseLook(code).join(' + ')}`;

/** Link that reopens the look in the fitting room. */
export const lookHref = (code: string) => `/?look=${encodeLook(parseLook(code))}`;

/** Look code stored in the `recrialab-look` tEXt chunk, or empty. */
export function lookFromPng(text: Record<string, string>): string {
  try {
    return encodeLook(parseLook(JSON.parse(text['recrialab-look'] ?? 'null')?.look));
  } catch {
    return '';
  }
}

/** `2026-11-01` → `1 nov 2026`, independent of the device time zone. */
export function shortDate(iso: string): string {
  const [y, m, d] = iso.split('-').map(Number);
  const months = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'];
  return `${d} ${months[m - 1]} ${y}`;
}
