// PS1/PS2 look of the stage, behind `?ps1` while the art direction is being decided. Kept apart from fabric.ts,
// which the selector thumbnails are rendered with: the default stage and the thumbnails stay as they are.
import * as THREE from 'three';

/**
 * The look: faceted shading, matte cloth that
 * carries its own light (the texture shows even in shade, as in games of that era), flat ambient light, coloured
 * rim lights that follow the camera and film grain over the stage. Full resolution: no pixelation and no aliasing.
 * Values calibrated on the 38 garments so the colour stays near today's (median ΔE 3.9; study of 10/11/2026).
 */
export const PS1 = typeof location !== 'undefined' && new URLSearchParams(location.search).has('ps1');
export const PS1_LOOK = {
  ambient: 1.9, sky: '#ffffff', ground: '#8a8fb5',
  key: '#fff3e0', keyIntensity: 2.2,
  rim: ['#7fd4ff', '#ffd27f'] as const, rimIntensity: 4,
  selfLight: .45, exposure: .9, body: '#d6d6de',
} as const;

/** Faceted, self-lit material of the PS1 look; garments light their own texture, the body its own colour. */
export function ps1Material(material: THREE.MeshStandardMaterial): void {
  material.normalMap = null;
  material.roughness = 1;
  material.metalness = 0;
  material.flatShading = true;
  if (material.map) {
    material.emissive.set('#ffffff');
    material.emissiveMap = material.map;
  } else {
    material.color.set(PS1_LOOK.body);
    material.emissive.set(PS1_LOOK.body);
  }
  material.emissiveIntensity = PS1_LOOK.selfLight;
  material.needsUpdate = true;
}

/** Light of the PS1 look, in place of addGarmentLights: no environment reflection, strong flat ambient. */
export function addPs1Lights(scene: THREE.Scene, renderer: THREE.WebGLRenderer): THREE.DirectionalLight {
  scene.add(new THREE.HemisphereLight(PS1_LOOK.sky, PS1_LOOK.ground, PS1_LOOK.ambient));
  const key = new THREE.DirectionalLight(PS1_LOOK.key, PS1_LOOK.keyIntensity);
  key.position.set(2, 4, 3);
  scene.add(key);
  renderer.toneMapping = THREE.NeutralToneMapping;
  renderer.toneMappingExposure = PS1_LOOK.exposure;
  return key;
}

/** Rim lights of the PS1 look, held by the camera: the coloured outline stays on both sides as the mannequin turns. */
export function addRimLights(scene: THREE.Scene, camera: THREE.Camera): void {
  scene.add(camera);
  for (const [color, x] of [[PS1_LOOK.rim[0], -3.2], [PS1_LOOK.rim[1], 3.2]] as const) {
    const light = new THREE.DirectionalLight(color, PS1_LOOK.rimIntensity);
    light.position.set(x, 1.6, -8.5);
    camera.add(light);
  }
}
