import { MathUtils, Spherical, Vector3, type PerspectiveCamera } from 'three';
import type { OrbitControls } from 'three/addons/controls/OrbitControls.js';

const IDLE_MS = 10_000;
const RETURN_MS = 900;
type Controls = Pick<OrbitControls, 'target' | 'autoRotate' | 'enableDamping' | 'update'>;
type View = { theta: number; phi: number; radius: number; target: Vector3 };

export function createCameraMotion(camera: PerspectiveCamera, controls: Controls, reducedMotion: boolean) {
  const homeTarget = controls.target.clone();
  const home = new Spherical().setFromVector3(camera.position.clone().sub(homeTarget));
  const offset = new Vector3();
  const pose = new Spherical();
  let lastInteraction = performance.now();
  let moving: { started: number; from: View; to: View; resume: boolean } | null = null;

  function interact(now = performance.now()): void {
    lastInteraction = now;
    moving = null;
    controls.autoRotate = false;
    controls.enableDamping = !reducedMotion;
  }

  function current(): View {
    pose.setFromVector3(offset.copy(camera.position).sub(controls.target));
    return { theta: pose.theta, phi: pose.phi, radius: pose.radius, target: controls.target.clone() };
  }

  function place(view: View): void {
    controls.target.copy(view.target);
    camera.position.copy(offset.setFromSpherical(pose.set(view.radius, view.phi, view.theta))).add(view.target);
  }

  /** Moves to `to` along the shortest arc; `to.theta` is taken modulo a full turn. */
  function move(to: View, resume: boolean, now: number): void {
    controls.autoRotate = false;
    // Drops the previous inertia before taking over the camera orientation.
    controls.enableDamping = false;
    controls.update();
    const from = current();
    const delta = MathUtils.euclideanModulo(from.theta - to.theta + Math.PI, Math.PI * 2) - Math.PI;
    moving = { started: now, from, to: { ...to, theta: from.theta - delta }, resume };
  }

  /** Front view with the full body: the reset button and the Home key. */
  function reset(now = performance.now()): void {
    interact(now);
    const to = { theta: home.theta, phi: home.phi, radius: home.radius, target: homeTarget.clone() };
    if (reducedMotion) {
      place(to);
      controls.update();
      return;
    }
    move(to, false, now);
  }

  /** Brings the camera to `target` at `radius`, keeping the angle: the zoom button. */
  function frame(target: Vector3, radius: number, now = performance.now()): void {
    interact(now);
    const to = { ...current(), radius, target: target.clone() };
    if (reducedMotion) {
      place(to);
      controls.update();
      return;
    }
    move(to, false, now);
  }

  function update(now: number): boolean {
    if (reducedMotion) return false;
    // After 10 s idle the camera turns back to the front and rotates, keeping the zoom: who zoomed in keeps the detail.
    if (!moving && !controls.autoRotate && now - lastInteraction >= IDLE_MS) {
      const { radius, target } = current();
      move({ theta: home.theta, phi: home.phi, radius, target }, true, now);
    }
    if (!moving) return false;
    const progress = MathUtils.clamp((now - moving.started) / RETURN_MS, 0, 1);
    const eased = progress * progress * (3 - 2 * progress);
    const { from, to } = moving;
    place({
      theta: MathUtils.lerp(from.theta, to.theta, eased),
      phi: MathUtils.lerp(from.phi, to.phi, eased),
      radius: MathUtils.lerp(from.radius, to.radius, eased),
      target: from.target.clone().lerp(to.target, eased),
    });
    if (progress === 1) {
      controls.autoRotate = moving.resume;
      controls.enableDamping = !moving.resume;
      moving = null;
    }
    return true;
  }

  return {
    interact,
    /** Starts the turn to the front and the rotation now, as if the 10 s had passed: the first visit. */
    showcase(now = performance.now()): void {
      lastInteraction = now - IDLE_MS;
    },
    reset,
    frame,
    update,
    /** Distance of the full-body view, the zoom's far limit. */
    homeRadius: home.radius,
    setReducedMotion(value: boolean): void {
      reducedMotion = value;
      interact();
    },
  };
}
