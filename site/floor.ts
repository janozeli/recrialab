import * as THREE from 'three';

/** The yellow floor under the feet, in the 3D scene so it follows the camera when it zooms and turns (a page-drawn
 * ellipse stayed put). Same paper yellow, ink outline and offset shadow as the page's zine look; the saved image gets
 * it from the same scene. Drawn first and without depth writes, in order, so it never fights for depth on a phone. */
export const FLOOR = { rx: .42, rz: .3, outline: .022, shadow: [.035, .035], paper: '#ffea00', ink: '#1f2a5e' } as const;

export function addFloor(scene: THREE.Scene): THREE.Group {
  const floor = new THREE.Group();
  floor.name = 'floor';
  let order = -10;
  const disk = (rx: number, rz: number, color: string, y: number, dx = 0, dz = 0): THREE.Mesh => {
    const mesh = new THREE.Mesh(new THREE.CircleGeometry(1, 64), new THREE.MeshBasicMaterial({ color, toneMapped: false, depthWrite: false }));
    mesh.rotation.x = -Math.PI / 2; mesh.scale.set(rx, rz, 1); mesh.position.set(dx, y, dz);
    mesh.renderOrder = order++;
    return mesh;
  };
  const { rx, rz, outline, shadow, paper, ink } = FLOOR;
  floor.add(disk(rx + outline, rz + outline, ink, .0005, shadow[0], shadow[1]));
  floor.add(disk(rx + outline, rz + outline, ink, .001));
  floor.add(disk(rx, rz, paper, .0015));
  scene.add(floor);
  return floor;
}
