/** Wardrobe filters: few, by kind of piece, one at a time (in place of a search box). Labels are screen text. */
export const FILTERS = {
  top: [
    { label: 'Time', ids: ['016', '017', '018', '019', '020', '022', '024', '025', '026', '029', '030'] },
    { label: 'Polo', ids: ['021', '023', '032'] },
    { label: 'Manga longa', ids: ['027', '028'] },
    { label: 'Jaqueta', ids: ['033', '034', '035', '036', '037', '038'] },
  ],
  bottom: [
    { label: 'Calça', ids: ['002', '004', '005', '006', '011', '012', '013', '014'] },
    { label: 'Bermuda e short', ids: ['001', '003', '008', '015'] },
    { label: 'Saia', ids: ['007', '009', '010'] },
    { label: 'Jeans', ids: ['001', '002', '003', '004', '005', '006', '008'] },
  ],
} as const;

/**
 * Display order of the wardrobe: pieces grouped like the filter chips (first group first), then the rest,
 * each group by catalog number.
 */
export function wardrobeOrder(slot: keyof typeof FILTERS, ids: readonly string[]): string[] {
  const group = (id: string): number => {
    const index = FILTERS[slot].findIndex(f => (f.ids as readonly string[]).includes(id));
    return index < 0 ? FILTERS[slot].length : index;
  };
  return [...ids].sort((a, b) => group(a) - group(b) || a.localeCompare(b));
}
