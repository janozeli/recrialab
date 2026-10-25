/** Identity of a look: the pieces worn, without personal data. */
export const LOOK_VERSION = 1;
const ID = /^\d{3}$/;

/** Sorted ids without repeats; empty when there is no valid piece. */
export function normalizeLook(ids: Iterable<string>): string[] {
  return [...new Set([...ids].filter(id => ID.test(id)))].sort();
}

/** Value of the `?look=` parameter (e.g. `004.024`). */
export function encodeLook(ids: Iterable<string>): string {
  return normalizeLook(ids).join('.');
}

export function parseLook(value: string | null | undefined): string[] {
  return value ? normalizeLook(value.split(/[.,\s]+/)) : [];
}

const CRC_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    table[n] = c >>> 0;
  }
  return table;
})();

function crc32(bytes: Uint8Array): number {
  let c = 0xffffffff;
  for (const b of bytes) c = CRC_TABLE[(c ^ b) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

/** Inserts a tEXt chunk right after IHDR, so the PNG carries which pieces were worn. */
export function addPngText(png: Uint8Array, keyword: string, text: string): Uint8Array<ArrayBuffer> {
  const signature = [137, 80, 78, 71, 13, 10, 26, 10];
  if (!signature.every((b, i) => png[i] === b)) throw new Error('not a PNG');
  const ihdrEnd = 8 + 12 + new DataView(png.buffer, png.byteOffset).getUint32(8);
  const data = new TextEncoder().encode(`${keyword}\0${text}`);
  const chunk = new Uint8Array(12 + data.length);
  const view = new DataView(chunk.buffer);
  view.setUint32(0, data.length);
  chunk.set(new TextEncoder().encode('tEXt'), 4);
  chunk.set(data, 8);
  view.setUint32(8 + data.length, crc32(chunk.subarray(4, 8 + data.length)));
  const out = new Uint8Array(png.length + chunk.length);
  out.set(png.subarray(0, ihdrEnd));
  out.set(chunk, ihdrEnd);
  out.set(png.subarray(ihdrEnd), ihdrEnd + chunk.length);
  return out;
}

/** Reads the tEXt chunks of a PNG (used by the tests and for curation). */
export function readPngText(png: Uint8Array): Record<string, string> {
  const out: Record<string, string> = {};
  const view = new DataView(png.buffer, png.byteOffset, png.byteLength);
  for (let at = 8; at + 12 <= png.length;) {
    const length = view.getUint32(at);
    const type = new TextDecoder().decode(png.subarray(at + 4, at + 8));
    if (type === 'tEXt') {
      const body = new TextDecoder().decode(png.subarray(at + 8, at + 8 + length));
      const split = body.indexOf('\0');
      out[body.slice(0, split)] = body.slice(split + 1);
    }
    at += 12 + length;
  }
  return out;
}
