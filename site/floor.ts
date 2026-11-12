import * as THREE from 'three';

/** The yellow floor under the feet, in the 3D: the page-drawn ellipse stayed put while the camera zoomed and turned
 * (Lucas, 12/11/2026, chose it over a soft shadow or no floor). Same paper yellow, ink outline and offset shadow as
 * the page's zine look. */
export const FLOOR = { rx: .42, rz: .3, outline: .022, shadow: [.035, .035], paper: '#ffea00', ink: '#1f2a5e' } as const;

export function addFloor(scene: THREE.Scene): THREE.Group {
  const floor = new THREE.Group();
  floor.name = 'floor';
  const disk = (rx: number, rz: number, color: string, y: number, dx = 0, dz = 0): THREE.Mesh => {
    const mesh = new THREE.Mesh(new THREE.CircleGeometry(1, 64), new THREE.MeshBasicMaterial({ color, toneMapped: false }));
    mesh.rotation.x = -Math.PI / 2; mesh.scale.set(rx, rz, 1); mesh.position.set(dx, y, dz);
    return mesh;
  };
  const { rx, rz, outline, shadow, paper, ink } = FLOOR;
  floor.add(disk(rx + outline, rz + outline, ink, .0005, shadow[0], shadow[1]));
  floor.add(disk(rx + outline, rz + outline, ink, .001));
  floor.add(disk(rx, rz, paper, .0015));
  scene.add(floor);
  return floor;
}
