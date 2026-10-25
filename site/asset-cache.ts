/** LRU eviction with a soft byte budget: visible/pending assets must stay alive. */
export function evictionCandidates(
  entries: readonly { key: string; bytes: number }[],
  protectedKeys: ReadonlySet<string>,
  budgetBytes: number,
  maxIdle = 1,
): string[] {
  let total = entries.reduce((sum, entry) => sum + entry.bytes, 0);
  let idle = entries.filter(entry => !protectedKeys.has(entry.key)).length;
  const evict: string[] = [];
  for (const entry of entries) {
    if (protectedKeys.has(entry.key)) continue;
    if (total <= budgetBytes && idle <= maxIdle) break;
    evict.push(entry.key);
    total -= entry.bytes;
    idle--;
  }
  return evict;
}
