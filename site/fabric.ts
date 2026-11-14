// Material and light of the garments, shared by the stage (dressup.ts) and the selector thumbnails
// (thumbnail-render.ts): a thumbnail drawn with other light would not look like the piece on the mannequin.
import * as THREE from 'three';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { HUE, SATURATION, TONE } from './garment-tones';

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
      recolour(material, SATURATION[id] ?? 1, HUE[id] ?? 0);
    }
  });
}

const LUMA = [.2126, .7152, .0722];
/**
 * Colour matrix of the texture, lit and self-lit alike: hue turned by `hue` degrees around the grey axis, then the
 * saturation mixed towards the luminance by `saturation`. The 3D generator painted some textures more saturated or
 * off in hue against the photo (032 purple where the photo is maroon), and the gain that brings a dark garment to the
 * photo's brightness raises its chroma with it. Hue 0 and saturation 1 leave the shader as it is.
 */
export function colourMatrix(saturation: number, hue: number): number[] {
  const t = hue * Math.PI / 180, c = Math.cos(t), s = Math.sin(t), k = 1 / 3, q = Math.sqrt(k);
  // rotation around the (1, 1, 1) axis (Rodrigues), row-major
  const r = [
    c + (1 - c) * k, (1 - c) * k - q * s, (1 - c) * k + q * s,
    (1 - c) * k + q * s, c + (1 - c) * k, (1 - c) * k - q * s,
    (1 - c) * k - q * s, (1 - c) * k + q * s, c + (1 - c) * k,
  ];
  // saturation: out = luma + saturation * (in - luma), row-major
  const m = [0, 1, 2].flatMap(row => [0, 1, 2].map(col => (1 - saturation) * LUMA[col] + (row === col ? saturation : 0)));
  return [0, 1, 2].flatMap(row => [0, 1, 2].map(col => [0, 1, 2].reduce((sum, x) => sum + m[row * 3 + x] * r[x * 3 + col], 0)));
}

function recolour(material: THREE.MeshStandardMaterial, saturation: number, hue: number): void {
  if (Math.abs(saturation - 1) < .005 && Math.abs(hue) < .5) return;
  const m = colourMatrix(saturation, hue);
  // GLSL mat3 takes columns
  const glsl = `mat3(${[0, 1, 2].flatMap(col => [0, 1, 2].map(row => m[row * 3 + col].toFixed(4))).join(', ')})`;
  const apply = (v: string) => `${v} = ${glsl} * ${v};`;
  material.onBeforeCompile = shader => {
    shader.fragmentShader = shader.fragmentShader
      .replace('#include <map_fragment>', `#include <map_fragment>\n${apply('diffuseColor.rgb')}`)
      .replace('#include <emissivemap_fragment>', `#include <emissivemap_fragment>\n${apply('totalEmissiveRadiance')}`);
  };
  material.customProgramCacheKey = () => `recolour ${glsl}`;
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
