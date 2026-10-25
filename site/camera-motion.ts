import { MathUtils, Spherical, Vector3, type PerspectiveCamera } from 'three';
import type { OrbitControls } from 'three/addons/controls/OrbitControls.js';

const IDLE_MS = 10_000;
const RETURN_MS = 900;
type Controls = Pick<OrbitControls, 'target' | 'autoRotate' | 'enableDamping' | 'update'>;

export function createCameraMotion(camera: PerspectiveCamera, controls: Controls, reducedMotion: boolean) {
  const homeTarget = controls.target.clone();
  const home = new Spherical().setFromVector3(camera.position.clone().sub(homeTarget));
  const offset = new Vector3();
  const pose = new Spherical();
  let lastInteraction = performance.now();
  let returning: { started: number; theta: number; phi: number; resume: boolean } | null = null;

  function interact(now = performance.now()): void {
    lastInteraction = now;
    returning = null;
    controls.autoRotate = false;
    controls.enableDamping = !reducedMotion;
  }

  function beginReturn(resume: boolean, now: number): void {
    controls.autoRotate = false;
    pose.setFromVector3(offset.copy(camera.position).sub(controls.target));
    // Drops the previous inertia before taking over the camera orientation.
    controls.enableDamping = false;
    controls.update();
    const delta = MathUtils.euclideanModulo(pose.theta - home.theta + Math.PI, Math.PI * 2) - Math.PI;
    returning = { started: now, theta: home.theta + delta, phi: pose.phi, resume };
  }

  function reset(now = performance.now()): void {
    interact(now);
    if (reducedMotion) {
      controls.target.copy(homeTarget);
      camera.position.copy(offset.setFromSpherical(home)).add(homeTarget);
      controls.update();
      return;
    }
    beginReturn(false, now);
  }

  function update(now: number): boolean {
    if (reducedMotion) return false;
    if (!returning && !controls.autoRotate && now - lastInteraction >= IDLE_MS) beginReturn(true, now);
    if (!returning) return false;
    const progress = MathUtils.clamp((now - returning.started) / RETURN_MS, 0, 1);
    const eased = progress * progress * (3 - 2 * progress);
    // Interpolates the angles and keeps the radius: recentring never brings the camera closer.
    pose.set(home.radius, MathUtils.lerp(returning.phi, home.phi, eased), MathUtils.lerp(returning.theta, home.theta, eased));
    controls.target.copy(homeTarget);
    camera.position.copy(offset.setFromSpherical(pose)).add(homeTarget);
    if (progress === 1) {
      controls.autoRotate = returning.resume;
      controls.enableDamping = !returning.resume;
      returning = null;
    }
    return true;
  }

  return {
    interact,
    reset,
    update,
    setReducedMotion(value: boolean): void {
      reducedMotion = value;
      interact();
    },
  };
}
