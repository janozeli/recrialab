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
