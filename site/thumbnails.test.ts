// Selector thumbnail = the 3D piece that goes on the mannequin: bound to the current GLB, tone and renderer.
import { test, expect } from 'bun:test';
import { existsSync, readFileSync } from 'node:fs';
import { CATALOG } from './catalog-data';
import { LOCK, currentLock, staleThumbnails, thumbPath, type Lock } from './thumbnails';

test('every piece has a thumbnail rendered from the GLB, tone and renderer being shipped', () => {
  const saved: Lock = JSON.parse(readFileSync(LOCK, 'utf8'));
  const stale = staleThumbnails(saved, currentLock());
  // stale: run `bun thumbnails.ts` in site/ (redoes only the stale ones) and commit the thumbnails and the lock
  expect(stale).toEqual([]);
  expect(Object.keys(saved.pieces).sort()).toEqual(CATALOG.map(p => p.id).sort());
});

test('the selector shows the rendered thumbnail; the shop photo stays on the About page', () => {
  for (const piece of CATALOG) {
    expect(piece.thumb).toContain(`thumbnails/${piece.id}`);
    expect(piece.photo).toContain(`photos/${piece.id}`);
    expect(existsSync(thumbPath(piece.id))).toBe(true);
  }
});
