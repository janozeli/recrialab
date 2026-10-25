import { expect, test } from 'bun:test';
import { readFileSync } from 'node:fs';
import { CATALOG } from './catalog-data';

// Piece names read like a thrift store tag, and the screen carries no obvious instructions. Screen text is Portuguese,
// so the patterns below are Portuguese words.
const KINDS = ['Bermuda', 'Blusa', 'Calça', 'Camisa', 'Camiseta', 'Casaco', 'Jaqueta', 'Minissaia', 'Polo', 'Regata', 'Saia', 'Short'];

test('piece names are short like a thrift store tag, start with the kind of piece and do not repeat', () => {
  const bad = CATALOG.filter(p => p.name.length > 26 || !KINDS.includes(p.name.split(' ')[0]));
  expect(bad.map(p => `${p.id} ${p.name}`)).toEqual([]);
  expect(new Set(CATALOG.map(p => p.name.toLowerCase())).size).toBe(CATALOG.length);
});

// An instruction for what the interface already shows (tap, drag, choose, write down) does not go on screen.
// The screen-reader-only text (stage-label.ts) is left out: there the instruction is needed.
const OBVIOUS = /\bnenhum[a]? .{0,40}\b(é|são) mostrad|\bnão (é|são) mostrad/i;
const ORDERS = /\b(toque|toc[ae]|arraste|escolha|anote|preencha|clique|deslize|tente|aguarde)\b/i;
for (const file of ['./index.html', './sobre.html', './dressup.ts', './about.ts', './about-data.ts']) {
  test(`no obvious instruction in ${file}`, () => {
    const source = readFileSync(new URL(file, import.meta.url), 'utf8');
    // Visible text: tag content in HTML, strings in TS (comments do not count).
    const texts = file.endsWith('.html')
      ? [...source.replace(/<script[\s\S]*?<\/script>|<svg[\s\S]*?<\/svg>/g, '').matchAll(/>([^<>]+)</g)].map(m => m[1].trim())
      : [...source.replace(/^\s*\/\/.*$|\/\*[\s\S]*?\*\//gm, '').matchAll(/(['"`])((?:(?!\1)[^\\\n]|\\.)*)\1/g)].map(m => m[2]);
    expect(texts.filter(t => /[a-zà-ú]{3}/i.test(t) && ORDERS.test(t))).toEqual([]);
    // Nor a notice of the obvious (such as a footer saying that no face is shown).
    expect(texts.filter(t => OBVIOUS.test(t))).toEqual([]);
  });
}
