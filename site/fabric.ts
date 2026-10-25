// Material and light of the garments, shared by the stage (dressup.ts) and the selector thumbnails
// (thumbnail-render.ts): a thumbnail drawn with other light would not look like the piece on the mannequin.
import * as THREE from 'three';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { TONE } from './garment-tones';

/** One roughness for every garment: matte fabric, without the plastic shine of the generated maps. */
export const FABRIC_ROUGHNESS = 0.9;
export const FABRIC_EXPOSURE = 0.55;

/** Fabric is matte: the generated roughness/metalness maps gave a plastic shine. */
export function matteFabric(model: THREE.Object3D, id: string): void {
  model.traverse((node) => {
    if (!(node instanceof THREE.Mesh)) return;
    for (const material of [node.material].flat()) {
      if (!(material instanceof THREE.MeshStandardMaterial)) continue;
      material.roughnessMap = null;
      material.metalnessMap = null;
      material.roughness = FABRIC_ROUGHNESS;
      material.metalness = 0;
      // front brightness close to the thrift store photo: the 3D generator painted some textures darker, others lighter
      material.color.multiplyScalar(TONE[id] ?? 1);
    }
  });
}

/** Light for the garments; returns the key light, which turns with the camera. */
export function addGarmentLights(scene: THREE.Scene, renderer: THREE.WebGLRenderer): THREE.DirectionalLight {
  scene.add(new THREE.HemisphereLight('#ffffff', '#556', .6));
  const key = new THREE.DirectionalLight('#ffffff', 2);
  key.position.set(2, 4, 3);
  scene.add(key);
  // PBR maps need indirect lighting; do not change textures or hide mesh defects.
  const environment = new RoomEnvironment();
  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(environment, .04).texture;
  environment.dispose();
  pmrem.dispose();
  // Neutral (not ACES) and low exposure: the colour of the piece on the site stays close to the texture (the
  // thrift store photo). With ACES at 1 the orange of 015 turned peach and the red of 035 turned salmon.
  renderer.toneMapping = THREE.NeutralToneMapping;
  renderer.toneMappingExposure = FABRIC_EXPOSURE;
  return key;
}
