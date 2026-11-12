// The PS1 look stays behind its URL parameter: the default stage and the thumbnails keep today's light.
import { test, expect } from 'bun:test';
import { readFileSync } from 'node:fs';
import * as THREE from 'three';
import { PS1, PS1_LOOK, ps1Material } from './ps1';

test('the PS1 look is off unless the page asks for it', () => {
  expect(PS1).toBe(false);
  // fabric.ts renders the selector thumbnails: the look must not leak into it
  expect(readFileSync(new URL('./fabric.ts', import.meta.url), 'utf8')).not.toContain('ps1');
});

test('PS1 material: faceted, matte, lit by its own texture (garment) or colour (body)', () => {
  const map = new THREE.Texture();
  const garment = new THREE.MeshStandardMaterial({ map, normalMap: new THREE.Texture(), roughness: .5 });
  ps1Material(garment);
  expect(garment.flatShading).toBe(true);
  expect(garment.normalMap).toBeNull();
  expect(garment.roughness).toBe(1);
  expect(garment.emissiveMap).toBe(map);
  expect(garment.emissiveIntensity).toBe(PS1_LOOK.selfLight);
  const body = new THREE.MeshStandardMaterial();
  ps1Material(body);
  expect(body.emissiveMap).toBeNull();
  expect(`#${body.emissive.getHexString()}`).toBe(PS1_LOOK.body);
});

test('rim lights are near white: a faceted shell keeps its fabric colour, facets change brightness only', () => {
  for (const hex of PS1_LOOK.rim) {
    // chroma of the light in sRGB (max - min channel): the cyan and amber of the first version had .5 and over
    const [r, g, b] = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) / 255);
    expect(Math.max(r, g, b) - Math.min(r, g, b)).toBeLessThan(.15);
    expect(Math.min(r, g, b)).toBeGreaterThan(.85);
  }
});
