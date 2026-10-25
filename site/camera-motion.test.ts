import { expect, test } from 'bun:test';
import { PerspectiveCamera, Spherical, Vector3 } from 'three';
import { createCameraMotion } from './camera-motion';

function setup(reduced = false) {
  const camera = new PerspectiveCamera();
  camera.position.set(0, 1.15, 4.4);
  const controls = { target: new Vector3(0, 1, 0), autoRotate: false, enableDamping: !reduced, update() {} };
  const home = camera.position.clone();
  const radius = camera.position.distanceTo(controls.target);
  const motion = createCameraMotion(camera, controls, reduced);
  motion.interact(0);
  function turn(theta, phi = Math.PI / 2) {
    camera.position.setFromSpherical(new Spherical(radius, phi, theta)).add(controls.target);
  }
  return { camera, controls, home, radius, motion, turn };
}

test('waits 10 s, returns along the shortest arc without zoom and only then rotates', () => {
  const { camera, controls, home, radius, motion, turn } = setup();
  turn(3 * Math.PI / 2, 1.2);
  const before = camera.position.clone();
  expect(motion.update(9_999)).toBe(false);
  expect(camera.position.equals(before)).toBe(true);
  expect(motion.update(10_000)).toBe(true);
  expect(controls.autoRotate).toBe(false);
  for (const now of [10_100, 10_450, 10_899]) {
    motion.update(now);
    expect(camera.position.distanceTo(controls.target)).toBeCloseTo(radius, 10);
    expect(camera.position.x).toBeLessThan(0);
    expect(controls.autoRotate).toBe(false);
  }
  motion.update(10_900);
  expect(camera.position.distanceTo(home)).toBeLessThan(1e-10);
  expect(controls.autoRotate).toBe(true);
});

test('interacting during the return stops it and starts a full new wait', () => {
  const { camera, controls, motion, turn } = setup();
  turn(1.8);
  motion.update(10_000);
  motion.update(10_300);
  motion.interact(10_300);
  const interrupted = camera.position.clone();
  expect(motion.update(20_299)).toBe(false);
  expect(camera.position.equals(interrupted)).toBe(true);
  expect(controls.autoRotate).toBe(false);
  expect(motion.update(20_300)).toBe(true);
});

test('a touch stops the rotation and a manual reset returns to the front without resuming at once', () => {
  const { camera, controls, home, motion, turn } = setup();
  motion.update(10_000);
  motion.update(10_900);
  motion.interact(11_000);
  expect(controls.autoRotate).toBe(false);
  turn(1);
  motion.reset(12_000);
  motion.update(12_900);
  expect(camera.position.distanceTo(home)).toBeLessThan(1e-10);
  expect(controls.autoRotate).toBe(false);
  expect(motion.update(21_999)).toBe(false);
  expect(motion.update(22_000)).toBe(true);
});

test('reduced motion prevents the automatic return and rotation, but allows an immediate reset', () => {
  const { camera, controls, home, motion, turn } = setup(true);
  turn(1);
  expect(motion.update(60_000)).toBe(false);
  expect(controls.autoRotate).toBe(false);
  motion.reset(60_001);
  expect(camera.position.distanceTo(home)).toBeLessThan(1e-10);
  expect(controls.enableDamping).toBe(false);
});

test('turning on reduced motion stops both a return and a rotation in progress', () => {
  for (const duringReturn of [true, false]) {
    const { camera, controls, motion, turn } = setup();
    turn(2);
    motion.update(10_000);
    motion.update(duringReturn ? 10_400 : 10_900);
    motion.setReducedMotion(true);
    const stopped = camera.position.clone();
    expect(motion.update(60_000)).toBe(false);
    expect(camera.position.equals(stopped)).toBe(true);
    expect(controls.autoRotate).toBe(false);
    expect(controls.enableDamping).toBe(false);
  }
});
