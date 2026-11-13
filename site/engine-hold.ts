// Garments that stay as published instead of the fit engine's version, each with the reason. One per line.
// Adding a garment here puts it back as published at once, with no other change; taking one out needs
// `bun engine-import.ts WORK` so its files come in.
export const ENGINE_HOLD: Record<string, string> = {
};
