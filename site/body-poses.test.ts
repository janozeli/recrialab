import { test, expect } from 'bun:test';
import { readFileSync, readdirSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { BODY_POSES, bodyPoseForBottom } from './body-poses';
import * as THREE from 'three';
import { validateBodyMask, bodyClip, WAIST_STEPS, WAIST_TORSO, WAIST_BAND, NECK_STEPS, NECK_AXIS_Z, NECK_RADIUS, NECK_BAND,
  SLEEVE_STEPS, SLEEVE_ARM_X, SLEEVE_RADIUS, SLEEVE_BAND, SLEEVE_AXIS, SLEEVE_POKE } from './body-occlusion';
import { BODY_MASKS, BODY_C_MASKS } from './body-masks';

const asset = (name) => new URL(`./assets/${name}`, import.meta.url);
const hash = (name) => createHash('sha256').update(readFileSync(asset(name))).digest('hex');

test('the five pose C pants select C; removal and every other catalog item restore B', () => {
  const cPants = new Set(['006', '011', '012', '013', '014']);
  for (let n = 1; n <= 38; n++) {
    const id = String(n).padStart(3, '0');
    expect(bodyPoseForBottom(id)).toBe(cPants.has(id) ? 'C' : 'B');
  }
  expect(bodyPoseForBottom(null)).toBe('B');
  expect(bodyPoseForBottom()).toBe('B');
  expect(bodyPoseForBottom('unknown')).toBe('B');
});

test('all deployed C masks bind to the actual C body and garment, and reject B', () => {
  expect(hash('body/pose-b.glb')).toBe(BODY_POSES.B.hash);
  expect(hash('body/pose-c.glb')).toBe(BODY_POSES.C.hash);
  expect(Object.keys(BODY_C_MASKS)).toHaveLength(28);
  for (const [id, mask] of Object.entries(BODY_C_MASKS)) {
    expect(hash(`garments/${id}.glb`)).toBe(mask.garment_sha256);
    for (const mesh of mask.meshes) {
      expect(validateBodyMask(mask, BODY_POSES.C.hash, mesh.name, 41600).length).toBeGreaterThan(0);
      expect(() => validateBodyMask(mask, BODY_POSES.B.hash, mesh.name, 41600)).toThrow();
    }
  }
});


test('all active B masks bind to shipped garment bytes and restore valid body triangles', () => {
  const ids = Object.keys(BODY_MASKS);
  expect(ids.length).toBeGreaterThan(0);
  expect(hash('body/pose-b.glb')).toBe(BODY_POSES.B.hash);
  for (const id of ids) {
    const mask = BODY_MASKS[id];
    expect(hash(`garments/${id}.glb`)).toBe(mask.garment_sha256);
    for (const mesh of mask.meshes) {
      const hidden = validateBodyMask(mask, BODY_POSES.B.hash, mesh.name, 41600);
      expect(new Set(hidden).size).toBe(hidden.length);
      expect(() => validateBodyMask(mask, BODY_POSES.C.hash, mesh.name, 41600)).toThrow();
    }
  }
});

// Torso clip at the waistband line (tools/fit/waist.py): the shader and the generator use the same numbers, and each
// line has one angle per step, at waist height.
test('waist lines match the shader clip and sit at the waist', () => {
  const py = readFileSync(new URL('../tools/fit/waist.py', import.meta.url), 'utf8');
  const [, step, torso, band] = py.match(/^STEP, TORSO, BAND[^=]*= ([\d.]+), ([\d.]+), ([\d.]+)/m);
  expect(360 / Number(step)).toBe(WAIST_STEPS);
  expect(Number(torso)).toBe(WAIST_TORSO);
  expect(Number(band)).toBe(WAIST_BAND);
  const lines = Object.entries({ ...BODY_MASKS, ...BODY_C_MASKS }).filter(([, m]) => m.waist_line);
  // the pieces with a clip are the ones waist.py lists: losing the line of one brings back the jagged edge
  const ids = py.match(/or \[([^\]]*)\]/)[1].match(/\d{3}/g);
  expect(lines.map(([id]) => id).sort()).toEqual(ids.sort());
  for (const [, mask] of lines) {
    expect(mask.waist_line).toHaveLength(WAIST_STEPS);
    for (const y of mask.waist_line) expect(y > 0.85 && y < 1.1).toBe(true);
  }
});

// Neck clip at the collar line (tools/fit/collar.py): same numbers in the shader and the generator, and the pieces
// with a line are the ones collar.py lists, with the line at neck height.
test('neck lines match the shader clip and sit at the neck', () => {
  const py = readFileSync(new URL('../tools/fit/collar.py', import.meta.url), 'utf8');
  const [, step, axis, radius, band] = py.match(/^STEP, AXIS_Z, RADIUS, BAND[^=]*= ([\d.]+), (-?[\d.]+), ([\d.]+), ([\d.]+)/m);
  expect(360 / Number(step)).toBe(NECK_STEPS);
  expect(Number(axis)).toBe(NECK_AXIS_Z);
  expect(Number(radius)).toBe(NECK_RADIUS);
  expect(Number(band)).toBe(NECK_BAND);
  const ids = py.match(/^IDS = \[([^\]]*)\]/m)[1].match(/\d{3}/g).sort();
  for (const registry of [BODY_MASKS, BODY_C_MASKS]) {
    const lines = Object.entries(registry).filter(([, m]) => m.neck_line);
    expect(lines.map(([id]) => id).sort()).toEqual(ids);
    for (const [, mask] of lines) {
      expect(mask.neck_line).toHaveLength(NECK_STEPS);
      for (const y of mask.neck_line) expect(y > 1.4 && y < 1.66).toBe(true);
    }
  }
});

// Arm clip at the sleeve hem (tools/fit/sleeve.py): same numbers in the shader and the generator, and the pieces with
// a line are the ones sleeve.py lists, with the line between the wrist and the armpit on both arms.
test('sleeve lines match the shader clip and sit between the wrist and the armpit', () => {
  const py = readFileSync(new URL('../tools/fit/sleeve.py', import.meta.url), 'utf8');
  const [, step, armX, radius, band] = py.match(/^STEP, ARM_X, RADIUS, BAND[^=]*= ([\d.]+), ([\d.]+), ([\d.]+), ([\d.]+)/m);
  expect(360 / Number(step)).toBe(SLEEVE_STEPS);
  expect(Number(armX)).toBe(SLEEVE_ARM_X);
  expect(Number(radius)).toBe(SLEEVE_RADIUS);
  expect(Number(band)).toBe(SLEEVE_BAND);
  expect(Number(py.match(/^POKE = ([\d.]+)/m)[1])).toBe(SLEEVE_POKE);
  const axis = py.match(/^AXIS_Y, AXIS_X, AXIS_Z, AXIS_DX, AXIS_DZ = (-?[\d.]+), (-?[\d.]+), (-?[\d.]+), (-?[\d.]+), (-?[\d.]+)/m).slice(1).map(Number);
  expect(axis).toEqual([SLEEVE_AXIS.y, SLEEVE_AXIS.x, SLEEVE_AXIS.z, SLEEVE_AXIS.dx, SLEEVE_AXIS.dz]);
  const ids = py.match(/^IDS = \[([^\]]*)\]/m)[1].match(/\d{3}/g).sort();
  expect(ids).toContain('022');
  // pieces with a wider band, and their band, as WIDE in sleeve.py lists them
  const wide = Object.fromEntries([...py.match(/^WIDE = \{([^}]*)\}/m)[1].matchAll(/'(\d{3})': ([\d.]+)/g)].map(m => [m[1], Number(m[2])]));
  expect(Object.keys(wide).every(id => ids.includes(id))).toBe(true);
  for (const registry of [BODY_MASKS, BODY_C_MASKS]) {
    const lines = Object.entries(registry).filter(([, m]) => m.sleeve_line);
    expect(lines.map(([id]) => id).sort()).toEqual(ids);
    for (const [id, mask] of lines) {
      expect(mask.sleeve_band ?? SLEEVE_BAND, id).toBe(wide[id] ?? SLEEVE_BAND);
      expect(mask.sleeve_line).toHaveLength(2 * SLEEVE_STEPS);
      for (const y of mask.sleeve_line) expect(y > 0.9 && y < 1.46).toBe(true);
    }
  }
});

test('the mask generator never reads the accepted-defects list (a removed acceptance must not silently change a mask)', () => {
  const dir = new URL('../tools/fit/', import.meta.url);
  for (const f of readdirSync(dir).filter(f => f.endsWith('.py'))) {
    expect(readFileSync(new URL(f, dir), 'utf8').includes('defects.json'), f).toBe(false);
  }
});

// The arm in the sleeve band goes only with cloth in front of it or up to SLEEVE_POKE behind it (the clothes' depth,
// drawn before the body): a clip with no cloth behind opened a slit to the background beside the torso (022, front).
test('the sleeve clip discards the arm only where the clothes depth is close behind it', () => {
  const mesh = new THREE.Mesh(new THREE.BufferGeometry(), new THREE.MeshStandardMaterial());
  bodyClip(mesh, mesh.material);
  const shader = { uniforms: {}, vertexShader: '#include <common>\n#include <begin_vertex>',
    fragmentShader: '#include <common>\n#include <clipping_planes_fragment>' };
  mesh.material.onBeforeCompile(shader, null);
  const sleeve = shader.fragmentShader.slice(shader.fragmentShader.indexOf('sleeveH'));
  const band = sleeve.slice(sleeve.indexOf('y + uSleeveBand'));
  expect(band.indexOf(`if (uClothReady > 0.5 && cloth < 1.0 && behind < ${SLEEVE_POKE.toFixed(3)}) discard`)).toBeGreaterThan(0);
  expect(band.split('discard').length - 1).toBe(1);
  expect(shader.uniforms).toHaveProperty('uCloth');
  expect(shader.uniforms.uSleeveBand.value).toBe(SLEEVE_BAND);
  expect(mesh.onBeforeRender).not.toBe(THREE.Object3D.prototype.onBeforeRender);
});

// A piece whose sleeve lies far from the arm (016) gets a wider band in its mask; the site has to hand it to the shader,
// or the arm shows over the sleeve from below: with the band forced back to 10 cm, 001.016 and 007.016 showed thousands
// of arm pixels over the sleeve. The worn top's band reaches the uniform, and the next top without one resets it.
test('the site clips the arm with the band of the worn top', () => {
  expect(readFileSync(new URL('./dressup.ts', import.meta.url), 'utf8')).toContain('registry[top]?.sleeve_line : undefined, top ? registry[top]?.sleeve_band : undefined)');
  const mesh = new THREE.Mesh(new THREE.BufferGeometry(), new THREE.MeshStandardMaterial());
  const setClip = bodyClip(mesh, mesh.material);
  const shader = { uniforms: {}, vertexShader: '#include <common>\n#include <begin_vertex>',
    fragmentShader: '#include <common>\n#include <clipping_planes_fragment>' };
  mesh.material.onBeforeCompile(shader, null);
  let wide = 0;
  for (const registry of [BODY_MASKS, BODY_C_MASKS]) {
    for (const [id, mask] of Object.entries(registry)) {
      if (!mask.sleeve_line) continue;
      setClip(undefined, mask.neck_line, mask.sleeve_line, mask.sleeve_band);
      expect(shader.uniforms.uSleeveBand.value, id).toBe(mask.sleeve_band ?? SLEEVE_BAND);
      if (mask.sleeve_band) wide++;
    }
  }
  expect(wide).toBeGreaterThan(0);
});
