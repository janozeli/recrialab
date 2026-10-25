import { test, expect } from 'bun:test';
import { visibleBodyIndices, validateBodyMask } from './body-occlusion';
test('unions overlapping garment coverage without altering the body source', () => {
  const body = new Uint16Array([0,1,2, 2,3,0, 4,5,6, 6,7,4]);
  expect([...visibleBodyIndices(body, [[0,1],[1,2]])]).toEqual([6,7,4]);
  expect([...body]).toEqual([0,1,2, 2,3,0, 4,5,6, 6,7,4]);
  expect([...visibleBodyIndices(body, [[2]])]).toEqual([0,1,2, 2,3,0, 6,7,4]);
  expect(visibleBodyIndices(body, [])).toEqual(body);
});
test('rejects coarse masks even when their indices fit a refined body', () => {
  const mask = {body_sha256:'coarse', meshes:[{name:'Corpo_B',primitive_index:0,triangle_count:2600,hidden_ranges:[[1,1]]}]};
  expect(() => validateBodyMask(mask,'refined','Corpo_B',41600)).toThrow();
  expect(() => validateBodyMask(mask,'coarse','Corpo_B',41600)).toThrow();
  expect(validateBodyMask(mask,'coarse','Corpo_B',2600)).toEqual([1]);
});
test('preserves large vertex indices and rejects a mask from different topology', () => {
  const body = new Uint32Array([65536,65537,65538]);
  expect(visibleBodyIndices(body, [])).toEqual(body);
  expect(() => visibleBodyIndices(body, [[1]])).toThrow();
  expect(() => visibleBodyIndices(body, [[-1]])).toThrow();
});
