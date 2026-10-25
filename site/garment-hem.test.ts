import { expect, test } from 'bun:test';
import { readFileSync } from 'node:fs';
import * as THREE from 'three';
import { HEM_STEPS, HEM_TORSO, hemAt, hemFill, hemLine } from './garment-hem';

// Hem clipping (garment-hem.ts): layer_check.py measures the junction with the same line as tools/fit/top_hem.py.
test('hem line uses the same numbers as layer_check.py', () => {
  const py = readFileSync(new URL('../tools/fit/top_hem.py', import.meta.url), 'utf8');
  const [, step, torso] = py.match(/^STEP, TORSO[^=]*= ([\d.]+), ([\d.]+)/m)!;
  expect(360 / Number(step)).toBe(HEM_STEPS);
  expect(Number(torso)).toBe(HEM_TORSO);
  expect(readFileSync(new URL('../tools/fit/layer_check.py', import.meta.url), 'utf8')).toContain('top_hem.height');
});

test('hem line follows the lowest torso fabric and fills open slices', () => {
  // hem at 0.9 m in front and 0.8 m at the back; a lower sleeve (|x| ≥ HEM_TORSO) does not count
  const hem = hemLine([new Float32Array([0, .9, .15, 0, .8, -.15, .3, .1, 0])]);
  expect(hem[0]).toBeCloseTo(.9);
  expect(hem[HEM_STEPS / 2]).toBeCloseTo(.8);
  expect(hemAt(hem, .15, 0)).toBeCloseTo(.85, 2);   // side: between front and back
  expect(hemAt(hem, -.15, 0)).toBeCloseTo(.85, 2);
});

test('hidden triangle comes back clipped at the hem', () => {
  const hem = new Float32Array(HEM_STEPS).fill(.9);
  const g = new THREE.BufferGeometry();
  // a front triangle crossing the hem (y from 0.8 to 1.0) and another wholly above it
  g.setAttribute('position', new THREE.Float32BufferAttribute([-.05, .8, .15, .05, .8, .15, 0, 1, .15, -.05, 1, .15, .05, 1, .15, 0, 1.1, .15], 3));
  g.setAttribute('uv', new THREE.Float32BufferAttribute([0, 0, 1, 0, .5, 1, 0, 0, 1, 0, .5, 1], 2));
  const fill = hemFill(g, [0, 1, 2, 3, 4, 5], [0, 1], hem, new THREE.Matrix4())!;
  const p = fill.getAttribute('position'), uv = fill.getAttribute('uv');
  expect(p.count).toBe(6);   // one quad: the lower part of the first, nothing of the second
  for (let i = 0; i < p.count; i++) {
    expect(p.getY(i)).toBeLessThanOrEqual(.9 + 1e-6);
    if (Math.abs(p.getY(i) - .9) < 1e-6) expect(uv.getY(i)).toBeCloseTo(.5);   // attribute interpolated at the cut
  }
  expect(hemFill(g, [0, 1, 2, 3, 4, 5], [1], hem, new THREE.Matrix4())).toBeNull();
  // a top without torso (sleeves only): the layer stays as the table says, nothing comes back
  expect(hemFill(g, [0, 1, 2, 3, 4, 5], [0, 1], hemLine([new Float32Array([.3, .1, 0])]), new THREE.Matrix4())).toBeNull();
});
