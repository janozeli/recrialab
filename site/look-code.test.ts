import { test, expect } from 'bun:test';
import { addPngText, encodeLook, parseLook, readPngText } from './look-code';

test('look code is order-independent and ignores junk', () => {
  expect(encodeLook(['024', '004'])).toBe('004.024');
  expect(parseLook('024.004')).toEqual(['004', '024']);
  expect(parseLook('004,abc,004,9999')).toEqual(['004']);
  expect(parseLook(null)).toEqual([]);
});

test('PNG keeps the look in a valid tEXt chunk', () => {
  // Minimal 1×1 PNG.
  const png = Uint8Array.from(atob('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='), c => c.charCodeAt(0));
  const out = addPngText(png, 'recrialab-look', '{"look":"004.024"}');
  expect(readPngText(out)['recrialab-look']).toBe('{"look":"004.024"}');
  expect(out.length).toBe(png.length + 12 + 'recrialab-look'.length + 1 + 18);
});
