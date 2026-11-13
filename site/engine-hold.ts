// Garments that stay as published instead of the fit engine's version, each with the reason. One per line.
// Adding a garment here puts it back as published at once, with no other change; taking one out needs
// `bun engine-import.ts WORK` so its files come in.
export const ENGINE_HOLD: Record<string, string> = {
  '005': 'inner side of both legs comes out black on the engine garment',
  '009': 'white patch on the front of the skirt, where the print found no cloth',
  '010': 'skirt hem in points and patches on the back; tube still open in tools/fit',
  '016': 'print tear at the sleeves, 6.1 against 0.0 published (limit 4.0)',
  '020': 'sleeves come out as white points; body through the cloth 8.2 against 0.1 (limit 2.0)',
  '030': 'light patches over the front and back; print tear 8.0 against 0.1 (limit 4.0)',
  '033': 'hole across the upper back, under the hood',
  '034': 'loose hood in pieces on the back; still open in tools/fit',
};
