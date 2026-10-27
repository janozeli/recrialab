import { expect, test } from 'bun:test';
import { readFileSync } from 'node:fs';
import * as THREE from 'three';
import { HEM_BAND, HEM_LIFT, HEM_LIFT_MAX, HEM_STEPS, HEM_TORSO, hemAt, hemFill, hemLine, hemRadius } from './garment-hem';

// Hem clipping (garment-hem.ts): layer_check.py measures the junction with the same line as tools/fit/top_hem.py.
test('hem line uses the same numbers as layer_check.py', () => {
  const py = readFileSync(new URL('../tools/fit/top_hem.py', import.meta.url), 'utf8');
  const [, step, torso] = py.match(/^STEP, TORSO[^=]*= ([\d.]+), ([\d.]+)/m)!;
  expect(360 / Number(step)).toBe(HEM_STEPS);
  expect(Number(torso)).toBe(HEM_TORSO);
  const [, band, lift, max] = py.match(/^BAND, LIFT, LIFT_MAX[^=]*= ([\d.]+), ([\d.]+), ([\d.]+)/m)!;
  expect([Number(band), Number(lift), Number(max)]).toEqual([HEM_BAND, HEM_LIFT, HEM_LIFT_MAX]);
  expect(readFileSync(new URL('../tools/fit/layer_check.py', import.meta.url), 'utf8')).toContain('top_hem.height(hem, p, rad)');
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

test('the cut rises where the hem stands off the bottom, so the gap seen from below shows the bottom', () => {
  // hem at 0.9 m all round, 0.2 m from the axis in front
  const hem = new Float32Array(HEM_STEPS).fill(.9);
  const radius = hemRadius([new Float32Array([0, .9, .2, 0, 1.2, .15])], hem);
  expect(radius[0]).toBeCloseTo(.2);   // the fabric 30 cm above the hem is not the hem
  // a hem folded inwards: its inner layer, 4 cm in, is what the bottom must stay inside of
  expect(hemRadius([new Float32Array([0, .9, .2, 0, .91, .16])], hem)[0]).toBeCloseTo(.16);
  expect(hemAt(hem, 0, .17, radius)).toBeCloseTo(.9 + HEM_LIFT * .03);   // 3 cm inside the hem
  expect(hemAt(hem, 0, .1, radius)).toBeCloseTo(.9 + HEM_LIFT_MAX);      // capped
  expect(hemAt(hem, 0, .21, radius)).toBeCloseTo(.9);                    // outside the hem (poking): no lift
  expect(hemAt(hem, 0, .17)).toBeCloseTo(.9);                            // without the radius: the line
});
