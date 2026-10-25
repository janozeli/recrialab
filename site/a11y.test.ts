import { test, expect } from 'bun:test';
import { readFileSync } from 'node:fs';
import { stageLabel } from './stage-label';

/** WCAG 2.1 contrast between two #rrggbb colours. */
function contrast(a, b) {
  const lum = hex => {
    const [r, g, b] = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) / 255)
      .map(c => c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  };
  const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

const tokens = file => Object.fromEntries(
  [...readFileSync(new URL(file, import.meta.url), 'utf8').matchAll(/--([\w-]+):\s*(#[0-9a-f]{6})\b/gi)].map(m => [m[1], m[2]]));

// Text/background pairs used on the pages (WCAG AA): normal text needs 4.5:1.
// Ink on pink only appears in large bold labels (Barlow buttons ≥ 19px), which need 3:1.
const PAIRS = [
  ['ink', 'paper', 4.5], ['ink', 'panel', 4.5], ['paper', 'ink', 4.5], ['#ffffff', 'ink', 4.5],
  ['muted', 'paper', 4.5], ['muted', 'panel', 4.5], ['muted', '#fffdf0', 4.5], ['ink', 'pink', 3],
];

for (const file of ['./base.css', './about.css']) {
  test(`AA contrast in the colours of ${file}`, () => {
    const t = tokens(file);
    for (const [fg, bg, minimum] of PAIRS) {
      const colour = c => c.startsWith('#') ? c : t[c];
      if (!colour(fg) || !colour(bg)) continue;
      expect({ pair: `${fg} on ${bg}`, ok: contrast(colour(fg), colour(bg)) >= minimum }).toEqual({ pair: `${fg} on ${bg}`, ok: true });
    }
  });
}

test('pink on yellow fails: never use it for text', () => {
  expect(contrast('#ff2d95', '#ffea00')).toBeLessThan(3);
});

test('the screen reader hears what the mannequin wears', () => {
  expect(stageLabel([])).toBe('Manequim 3D sem roupa escolhida. Arraste ou use as setas do teclado para girar.');
  expect(stageLabel(['Polo vinho', 'Calça jeans'])).toContain('vestindo Polo vinho e Calça jeans');
});
