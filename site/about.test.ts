import { test, expect } from 'bun:test';
import { CATALOG } from './catalog-data';
import { ABOUT, TEAM_AREAS } from './about-data';
import { addPngText } from './look-code';
import { shortDate, lookFromPng, lookHref, lookLabel, lookPieces } from './about-model';
import { readPngText } from './look-code';

test('curated looks use only catalog pieces, one top and one bottom', () => {
  for (const { look } of ABOUT.looks) {
    const pieces = lookPieces(look);
    expect(pieces.map(p => p.id).sort().join('.')).toBe(look);
    expect(pieces.map(p => p.slot)).toEqual(['top', 'bottom']);
  }
});

test('workshops cited by looks exist', () => {
  const dates = new Set(ABOUT.workshops.map(o => o.date));
  for (const { workshop } of ABOUT.looks) if (workshop) expect(dates.has(workshop)).toBe(true);
  for (const { date } of ABOUT.workshops) expect(date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
});

test('label and link match the PNG exported by the fitting room', () => {
  expect(lookLabel('024.004')).toBe('LOOK 004 + 024');
  expect(lookHref('024.004')).toBe('/?look=004.024');
  expect(lookPieces('024.004.999').map(p => p.id)).toEqual(['024', '004']);
  expect(CATALOG.length).toBeGreaterThan(0);
});

test('reads the look from a PNG saved by the fitting room', () => {
  const png = Uint8Array.from(atob('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='), c => c.charCodeAt(0));
  const saved = addPngText(png, 'recrialab-look', JSON.stringify({ v: 1, look: '004.024', url: 'x' }));
  expect(lookFromPng(readPngText(saved))).toBe('004.024');
  expect(lookFromPng(readPngText(png))).toBe('');
  expect(lookFromPng({ 'recrialab-look': 'garbage' })).toBe('');
});

test('short date does not depend on the time zone', () => {
  expect(shortDate('2026-11-01')).toBe('1 nov 2026');
});

test('record links are https profiles', () => {
  const links = ABOUT.workshops.flatMap(o => o.links ?? []);
  expect(links.length).toBeGreaterThan(0);
  for (const { href, label } of links) {
    expect(href).toMatch(/^https:\/\/www\.instagram\.com\/[\w.]+\/$/);
    expect(href).toContain(label.slice(1));
  }
});

test('every team area has people and every person is in a listed area', () => {
  for (const area of TEAM_AREAS) expect(ABOUT.team.some(p => p.area === area)).toBe(true);
  for (const p of ABOUT.team) expect(TEAM_AREAS).toContain(p.area);
});
