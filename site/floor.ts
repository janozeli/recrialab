import * as THREE from 'three';

/** The yellow floor under the feet, in the 3D: the page-drawn ellipse stayed put while the camera zoomed and turned
 * (Lucas, 12/11/2026). Same paper yellow, ink outline and offset shadow as the page's zine look. */
export const FLOOR = { rx: .42, rz: .3, outline: .022, shadow: [.035, .035], paper: '#ffea00', ink: '#1f2a5e' } as const;
export type FloorKind = 'elipse' | 'sombra' | 'nada';

export function addFloor(scene: THREE.Scene, kind: FloorKind): THREE.Group {
  const floor = new THREE.Group();
  floor.name = 'floor';
  const disk = (rx: number, rz: number, color: string, y: number, dx = 0, dz = 0, map?: THREE.Texture): THREE.Mesh => {
    const mesh = new THREE.Mesh(new THREE.CircleGeometry(1, 64), new THREE.MeshBasicMaterial({ color, map, transparent: Boolean(map), depthWrite: !map, toneMapped: false }));
    mesh.rotation.x = -Math.PI / 2; mesh.scale.set(rx, rz, 1); mesh.position.set(dx, y, dz);
    mesh.renderOrder = -1;
    return mesh;
  };
  if (kind === 'elipse') {
    const { rx, rz, outline, shadow, paper, ink } = FLOOR;
    floor.add(disk(rx + outline, rz + outline, ink, .0005, shadow[0], shadow[1]));
    floor.add(disk(rx + outline, rz + outline, ink, .001));
    floor.add(disk(rx, rz, paper, .0015));
  } else if (kind === 'sombra') {
    const canvas = document.createElement('canvas'); canvas.width = canvas.height = 64;
    const g = canvas.getContext('2d')!; const grad = g.createRadialGradient(32, 32, 0, 32, 32, 32);
    grad.addColorStop(0, 'rgba(0,0,0,.45)'); grad.addColorStop(1, 'rgba(0,0,0,0)');
    g.fillStyle = grad; g.fillRect(0, 0, 64, 64);
    floor.add(disk(.36, .26, '#ffffff', .001, 0, 0, new THREE.CanvasTexture(canvas)));
  }
  scene.add(floor);
  return floor;
}
