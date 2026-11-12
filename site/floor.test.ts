import { expect, test } from 'bun:test';
import { readFileSync } from 'node:fs';
import * as THREE from 'three';
import { addFloor, FLOOR } from './floor';

test('the floor is in the 3D scene, under the feet, with the page colours', () => {
  const scene = new THREE.Scene();
  const floor = addFloor(scene);
  expect(scene.children).toContain(floor);
  const box = new THREE.Box3().setFromObject(floor);
  expect(box.max.y).toBeLessThan(.005);
  expect(box.max.x).toBeGreaterThan(FLOOR.rx);
  const css = readFileSync(new URL('./base.css', import.meta.url), 'utf8');
  expect(css).toContain(`--paper: ${FLOOR.paper}`);
  expect(css).toContain(`--ink: ${FLOOR.ink}`);
});

test('no page-drawn floor left: it stayed put while the camera zoomed', () => {
  expect(readFileSync(new URL('./index.html', import.meta.url), 'utf8')).not.toContain('class="floor"');
  expect(readFileSync(new URL('./base.css', import.meta.url), 'utf8')).not.toMatch(/\.floor\b/);
});
