// Known fit issues (tools/known-issues.yaml): a check may excuse a piece, or tools/visual-qa/defects.json may list a
// defect, only while an issue listed there owns it and names the piece.
import { readFileSync } from 'node:fs';

/** An open known issue and the pieces it names. */
export type KnownIssue = { id: string; pieces: string[] };

export const knownIssues = (): KnownIssue[] =>
  (Bun.YAML.parse(readFileSync(new URL('../tools/known-issues.yaml', import.meta.url), 'utf8')) as { id: string; pieces: string[] }[])
    .map(({ id, pieces }) => ({ id, pieces }));
