// Draws one garment the way the stage does (fabric.ts), alone and from the front, for the selector thumbnail.
// Driven by thumbnails.ts in headless Chromium; never shipped.
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { addGarmentLights, matteFabric } from './fabric';

const THUMB_PX = 320;
/** Margin around the piece, as a fraction of the side. */
const MARGIN = .06;
const SUPERSAMPLE = 2;

const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(1);
renderer.setSize(THUMB_PX * SUPERSAMPLE, THUMB_PX * SUPERSAMPLE);
renderer.setClearColor(0x000000, 0);
renderer.outputColorSpace = THREE.SRGBColorSpace;
const scene = new THREE.Scene();
addGarmentLights(scene, renderer);
// Same field of view as the stage: the thumbnail perspective is that of the mannequin seen from the front.
const camera = new THREE.PerspectiveCamera(30, 1, 0.1, 30);
const loader = new GLTFLoader();
const out = document.createElement('canvas');
out.width = out.height = THUMB_PX;

async function renderThumbnail(id: string, url: string): Promise<string> {
  const { scene: model } = await loader.loadAsync(url);
  matteFabric(model, id);
  scene.add(model);
  const box = new THREE.Box3().setFromObject(model);
  const center = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3());
  // Distance at which the largest side of the front fits the frame, counted from the front face of the piece.
  const half = Math.max(size.x, size.y) / 2 / (1 - 2 * MARGIN);
  const distance = half / Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)) + size.z / 2;
  camera.position.set(center.x, center.y, center.z + distance);
  camera.lookAt(center);
  camera.near = distance / 10;
  camera.far = distance * 10;
  camera.updateProjectionMatrix();
  renderer.render(scene, camera);
  scene.remove(model);
  model.traverse(node => {
    if (!(node instanceof THREE.Mesh)) return;
    node.geometry.dispose();
    for (const material of [node.material].flat()) {
      for (const value of Object.values(material)) if (value instanceof THREE.Texture) value.dispose();
      material.dispose();
    }
  });
  const ctx = out.getContext('2d')!;
  ctx.clearRect(0, 0, THUMB_PX, THUMB_PX);
  ctx.imageSmoothingQuality = 'high';
  ctx.drawImage(renderer.domElement, 0, 0, THUMB_PX, THUMB_PX);
  return out.toDataURL('image/webp', .86);
}

Object.assign(window, { renderThumbnail });
