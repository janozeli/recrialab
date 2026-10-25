import { test, expect } from 'bun:test';
import { evictionCandidates } from './asset-cache';
const entries = [{ key: 'old', bytes: 20 }, { key: 'visible', bytes: 40 }, { key: 'recent', bytes: 20 }];
test('evicts oldest inactive asset to meet byte budget', () => {
  expect(evictionCandidates(entries, new Set(['visible']), 60)).toEqual(['old']);
});
test('never disposes visible or pending models even above budget', () => {
  expect(evictionCandidates(entries, new Set(['visible', 'recent']), 10)).toEqual(['old']);
});
test('keeps one recently used inactive model when budget allows', () => {
  expect(evictionCandidates(entries, new Set(['visible']), 100)).toEqual(['old']);
});
test('no eviction when only protected and one cheap idle model remain', () => {
  expect(evictionCandidates(entries.slice(1), new Set(['visible']), 100)).toEqual([]);
});
test('empty cache and all protected are safe', () => {
  expect(evictionCandidates([], new Set(), 0)).toEqual([]);
  expect(evictionCandidates(entries, new Set(entries.map(e => e.key)), 0)).toEqual([]);
});
