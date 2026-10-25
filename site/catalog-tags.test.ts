import { expect, test } from 'bun:test';
import { CATALOG } from './catalog-data';
import { FILTERS, wardrobeOrder } from './catalog-tags';

// An explicit order keeps the wardrobe grouped like the filters, whatever order the catalog lists the pieces in.
for (const slot of ['top', 'bottom'] as const) {
  test(`the ${slot} wardrobe follows the filter order, each group by number`, () => {
    const ids = CATALOG.filter(p => p.slot === slot).map(p => p.id);
    const order = wardrobeOrder(slot, ids.toReversed());
    expect(order.toSorted()).toEqual(ids.toSorted());
    // Each filter (the first one the piece belongs to) forms a single block, in the order of the buttons.
    const group = order.map(id => FILTERS[slot].findIndex(f => (f.ids as readonly string[]).includes(id)))
      .map(i => (i < 0 ? FILTERS[slot].length : i));
    expect(group).toEqual(group.toSorted((a, b) => a - b));
  });
}

test('every filter has a wardrobe piece', () => {
  for (const slot of ['top', 'bottom'] as const)
    for (const f of FILTERS[slot]) expect(f.ids.every(id => CATALOG.some(p => p.id === id && p.slot === slot))).toBe(true);
});
