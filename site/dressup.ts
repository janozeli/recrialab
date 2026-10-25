// The fitting room and the wardrobe share one selection and a single WebGL canvas.
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { loadGarmentLayers, garmentLayers, expandLayerRanges } from './garment-layer-data';
import { hemLine, hemFill } from './garment-hem';
import { CATALOG } from './catalog-data';
import { evictionCandidates } from './asset-cache';
import { createCameraMotion } from './camera-motion';
import { exportLookImage } from './look-export';
import { addPngText, encodeLook, LOOK_VERSION, parseLook, readPngText } from './look-code';
import { BODY_POSES, bodyPoseForBottom, type BodyPose } from './body-poses';
import { visibleBodyIndices, validateBodyMask, bodyClip, type BodyMask } from './body-occlusion';
import { BODY_MASKS, BODY_C_MASKS } from './body-masks';
import { stageLabel } from './stage-label';
import { addGarmentLights, matteFabric } from './fabric';
import { FILTERS, wardrobeOrder } from './catalog-tags';

import garment001 from './assets/garments/001.glb';
import garment002 from './assets/garments/002.glb';
import garment003 from './assets/garments/003.glb';
import garment004 from './assets/garments/004.glb';
import garment005 from './assets/garments/005.glb';
import garment006 from './assets/garments/006.glb';
import garment007 from './assets/garments/007.glb';
import garment008 from './assets/garments/008.glb';
import garment009 from './assets/garments/009.glb';
import garment010 from './assets/garments/010.glb';
import garment011 from './assets/garments/011.glb';
import garment012 from './assets/garments/012.glb';
import garment013 from './assets/garments/013.glb';
import garment014 from './assets/garments/014.glb';
import garment015 from './assets/garments/015.glb';
import garment016 from './assets/garments/016.glb';
import garment017 from './assets/garments/017.glb';
import garment018 from './assets/garments/018.glb';
import garment019 from './assets/garments/019.glb';
import garment020 from './assets/garments/020.glb';
import garment021 from './assets/garments/021.glb';
import garment022 from './assets/garments/022.glb';
import garment023 from './assets/garments/023.glb';
import garment024 from './assets/garments/024.glb';
import garment025 from './assets/garments/025.glb';
import garment026 from './assets/garments/026.glb';
import garment027 from './assets/garments/027.glb';
import garment028 from './assets/garments/028.glb';
import garment029 from './assets/garments/029.glb';
import garment030 from './assets/garments/030.glb';
import garment031 from './assets/garments/031.glb';
import garment032 from './assets/garments/032.glb';
import garment033 from './assets/garments/033.glb';
import garment034 from './assets/garments/034.glb';
import garment035 from './assets/garments/035.glb';
import garment036 from './assets/garments/036.glb';
import garment037 from './assets/garments/037.glb';
import garment038 from './assets/garments/038.glb';

type Slot = 'top' | 'bottom';

/** A catalog piece with its 3D model, in the body's own metres, origin and orientation. */
interface Piece {
  id: string;
  /** Always the catalog name: the same in the wardrobe, the about page and the screen reader. */
  name: string;
  slot: Slot;
  url: string;
  thumb: string;
}

const GARMENT_URLS: Record<string, string> = {
  '001': garment001,
  '002': garment002,
  '003': garment003,
  '004': garment004,
  '005': garment005,
  '006': garment006,
  '007': garment007,
  '008': garment008,
  '009': garment009,
  '010': garment010,
  '011': garment011,
  '012': garment012,
  '013': garment013,
  '014': garment014,
  '015': garment015,
  '016': garment016,
  '017': garment017,
  '018': garment018,
  '019': garment019,
  '020': garment020,
  '021': garment021,
  '022': garment022,
  '023': garment023,
  '024': garment024,
  '025': garment025,
  '026': garment026,
  '027': garment027,
  '028': garment028,
  '029': garment029,
  '030': garment030,
  '031': garment031,
  '032': garment032,
  '033': garment033,
  '034': garment034,
  '035': garment035,
  '036': garment036,
  '037': garment037,
  '038': garment038,
};
const PIECES: Piece[] = CATALOG.map(p => ({ ...p, url: GARMENT_URLS[p.id] }));
/** Opened without `?look=`: the mannequin is never shown naked; the address stays clean until the first change. */
const DEFAULT_LOOK = ['004', '024'];
/** Full-body view: the figure (feet at 0 m, head at 1.8 m) fills about 88% of the canvas height, a little room for the
 * floor under the feet. It was 74% with the camera at 4.4 m aimed at 1.0 m. */
const HOME_TARGET = new THREE.Vector3(0, .87, 0);
const HOME_CAMERA = new THREE.Vector3(0, 1.0, 3.88);
/** Close view of each group of pieces, for the zoom button. */
const CLOSE_UP: Record<Slot, { y: number; radius: number }> = { top: { y: 1.25, radius: 2.4 }, bottom: { y: .55, radius: 2.7 } };
const MIN_RADIUS = 1.4;
const icon = (name: string): string => `<svg class="icon" aria-hidden="true"><use href="#i-${name}" /></svg>`;

export function initDressUp(): void {
  const $ = <T extends HTMLElement>(sel: string): T => {
    const el = document.querySelector<T>(sel);
    if (!el) throw new Error(`missing required element: ${sel}`);
    return el;
  };
  const stage = $('#stage');
  let bodyState: 'loading' | 'ready' | 'error' = 'loading';

  const wardrobe = $('#wardrobe');
  const grid = $('#clothes-grid');
  const toast = $('#toast');
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
  // Side by side (desktop and landscape phone). Same query as base.css.
  const wide = matchMedia('(min-width: 900px), (orientation: landscape) and (max-height: 560px)');
  const exportButton = $<HTMLButtonElement>('#export-look');
  const exportDialog = $<HTMLDialogElement>('#look-export-dialog');
  const lookPreview = $<HTMLImageElement>('#look-preview');
  const saveLook = $<HTMLAnchorElement>('#save-look');
  const shareLook = $<HTMLButtonElement>('#share-look');
  const lookCode = $('#look-code');
  const lookNames = $('#look-names');
  let exportFile: File | null = null;
  const params = new URLSearchParams(location.search);
  const linkedLook = parseLook(params.get('look'));
  const initialLook = linkedLook.length ? linkedLook : DEFAULT_LOOK;
  let exportUrl: string | null = null;
  const wornIds = (): string[] => [...worn.values()].map(entry => entry.piece.id);
  let syncedLook = encodeLook(linkedLook.length ? linkedLook : initialLook);
  /** Keeps `?look=` in the address bar: the link reopens the same look. */
  function syncLookUrl(): void {
    if (bodyState !== 'ready' || restoring || !lookRestored) return;
    const look = encodeLook(wornIds());
    if (look === syncedLook) return;
    syncedLook = look;
    const url = new URL(location.href);
    if (look) url.searchParams.set('look', look); else url.searchParams.delete('look');
    history.replaceState(null, '', url);
  }
  let restoring = false;
  // The address follows the look only after the opening look is on: the default look keeps a bare address.
  let lookRestored = false;
  /** Wears exactly these pieces and takes the others off. */
  async function applyLook(ids: string[]): Promise<boolean> {
    const pieces = ids.map(id => PIECES.find(piece => piece.id === id)).filter(piece => piece !== undefined);
    if (!pieces.length) return false;
    restoring = true;
    try {
      for (const slot of [...worn.keys()]) if (!pieces.some(piece => piece.slot === slot)) remove(slot);
      await Promise.all(pieces.filter(piece => worn.get(piece.slot)?.piece.id !== piece.id).map(piece => toggle(piece)));
    } finally { restoring = false; }
    syncLookUrl();
    return true;
  }
  const restoreInitialLook = () => applyLook(initialLook);
  const importFile = $<HTMLInputElement>('#import-file');
  $('#import-look').addEventListener('click', () => importFile.click());
  importFile.addEventListener('change', async () => {
    const file = importFile.files?.[0];
    importFile.value = '';
    if (!file || bodyState !== 'ready') return;
    try {
      const meta = JSON.parse(readPngText(new Uint8Array(await file.arrayBuffer()))['recrialab-look'] ?? 'null');
      if (!(await applyLook(parseLook(meta?.look)))) throw new Error('no look');
      announce('Look aberto.');
    } catch {
      say('Essa imagem não tem um look do ReCriaLab.');
    }
  });
  $('#export-close').addEventListener('click', () => exportDialog.close());
  shareLook.addEventListener('click', () => {
    if (exportFile) navigator.share({ files: [exportFile], title: lookNames.textContent || 'ReCriaLab' }).catch(() => {});
  });
  exportDialog.addEventListener('close', () => {
    const url = exportUrl;
    exportUrl = null;
    exportFile = null;
    lookPreview.removeAttribute('src');
    saveLook.removeAttribute('href');
    if (url) setTimeout(() => URL.revokeObjectURL(url), 60_000);
    interacted();
  });
  const stageStatus = $('#stage-status');

  // --- 3D stage --------------------------------------------------------------
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(30, 1, 0.1, 30);
  camera.position.copy(HOME_CAMERA);

  // on a dense screen antialiasing costs a lot and adds little: the pixel ratio already smooths
  const renderer = new THREE.WebGLRenderer({ antialias: devicePixelRatio < 2, alpha: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.domElement.setAttribute('aria-label', stageLabel([]));
  renderer.domElement.setAttribute('role', 'img');
  renderer.domElement.tabIndex = 0;
  stage.append(renderer.domElement);

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = !reducedMotion.matches;
  controls.enablePan = false;
  // Zoom by pinch and wheel, between the full body and a close look at the print.
  controls.enableZoom = true;
  controls.minDistance = MIN_RADIUS;
  // From above, the camera saw into the collars and the inside of the clothes (made from photos taken at chest
  // height). The orbit stays between ~22° above and ~22° below the chest line.
  controls.minPolarAngle = Math.PI * 0.38;
  controls.maxPolarAngle = Math.PI * 0.62;
  controls.target.copy(HOME_TARGET);
  controls.autoRotateSpeed = 1;
  const cameraMotion = createCameraMotion(camera, controls, reducedMotion.matches);
  controls.maxDistance = cameraMotion.homeRadius;
  const activePointers = new Set<number>();

  const key = addGarmentLights(scene, renderer);
  // The light turns with the camera: front and back of the piece get the same light.
  // A fixed light would leave the back dark, looking like another fabric.
  const keyHome = key.position.clone();
  const yAxis = new THREE.Vector3(0, 1, 0);
  function followCamera(): void {
    const yaw = Math.atan2(camera.position.x - controls.target.x, camera.position.z - controls.target.z);
    key.position.copy(keyHome).applyAxisAngle(yAxis, yaw);
    scene.environmentRotation.set(0, yaw, 0);
  }

  // Mannequin: the two body poses (B and C), loaded at the end of initDressUp.
  const mannequin = new THREE.Group();
  scene.add(mannequin);

  // Drawing 60 times a second while the scene stands still wastes battery. The
  // loop only renders when the camera moves (`controls.update()` returns true
  // while dragging, during inertia and auto-rotation) or when the scene changes,
  // and then someone asks for it with `requestRender()`.
  let needsRender = true;
  const requestRender = (): void => {
    needsRender = true;
  };

  /** Screen box of the dressed figure in the stage, read by layout.mjs: the toolbar must never cover it. */
  const figureBox = new THREE.Box3(), corner = new THREE.Vector3();
  function markFigure(): void {
    figureBox.setFromObject(mannequin);
    for (const { object } of worn.values()) figureBox.expandByObject(object);
    if (figureBox.isEmpty()) return;
    const canvas = renderer.domElement, w = canvas.clientWidth, h = canvas.clientHeight, top = canvas.offsetTop;
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (let k = 0; k < 8; k++) {
      corner.set(k & 1 ? figureBox.max.x : figureBox.min.x, k & 2 ? figureBox.max.y : figureBox.min.y, k & 4 ? figureBox.max.z : figureBox.min.z).project(camera);
      const x = (corner.x + 1) / 2 * w, y = top + (1 - corner.y) / 2 * h;
      x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y);
    }
    stage.dataset.figure = [x0, y0, x1, y1].map(Math.round).join(' ');
  }
  function resize(): void {
    const w = stage.clientWidth;
    const top = 8;
    const h = stage.clientHeight - top - 16;
    if (!w || h <= 0) return;
    renderer.domElement.style.top = `${top}px`;
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    renderer.setSize(w, h);
    requestRender();
    if (bodyState === 'ready') markFigure();
  }
  const observer = new ResizeObserver(() => requestAnimationFrame(resize));
  observer.observe(stage);
  resize();

  let lastFrame = performance.now();
  renderer.setAnimationLoop((now) => {
    const delta = Math.min((now - lastFrame) / 1000, .05);
    lastFrame = now;
    if (document.hidden || exportDialog.open) return;
    if (activePointers.size) cameraMotion.interact(now);
    const recentred = cameraMotion.update(now);
    const cameraMoved = controls.update(delta);
    if (!recentred && !cameraMoved && !needsRender) return;
    needsRender = false;
    followCamera();
    syncZoomButton();
    renderer.render(scene, camera);
  });

  // Any interaction restarts the 10 s; holding a touch keeps the motion from resuming.
  const interacted = (): void => cameraMotion.interact();
  document.addEventListener('pointerdown', (event) => {
    activePointers.add(event.pointerId);
    interacted();
  }, { capture: true, passive: true });
  for (const name of ['pointerup', 'pointercancel'] as const) {
    document.addEventListener(name, (event) => {
      activePointers.delete(event.pointerId);
      interacted();
    }, { capture: true, passive: true });
  }
  for (const name of ['click', 'keydown', 'wheel', 'input', 'scroll'] as const) {
    document.addEventListener(name, interacted, { capture: true, passive: true });
  }
  window.addEventListener('blur', () => { activePointers.clear(); interacted(); });
  controls.addEventListener('start', interacted);
  controls.addEventListener('end', interacted);
  reducedMotion.addEventListener('change', () => cameraMotion.setReducedMotion(reducedMotion.matches));
  function front(): void {
    cameraMotion.reset();
    requestRender();
  }
  // Zoom button: the close view of the open tab's group (Em cima, Embaixo) and back to the full body.
  const zoomButton = $<HTMLButtonElement>('#zoom-stage');
  const zoomedIn = (): boolean => camera.position.distanceTo(controls.target) < cameraMotion.homeRadius * .85;
  let zoomShown = false;
  function syncZoomButton(): void {
    const zoomed = zoomedIn();
    if (zoomed === zoomShown) return;
    zoomShown = zoomed;
    // The floor is drawn by the page, not the 3D: it would float under a close view.
    stage.classList.toggle('zoomed', zoomed);
    zoomButton.setAttribute('aria-pressed', String(zoomed));
    zoomButton.setAttribute('aria-label', zoomed ? 'Ver o corpo inteiro' : 'Aproximar da peça');
    zoomButton.title = zoomButton.getAttribute('aria-label')!;
    zoomButton.querySelector('use')!.setAttribute('href', zoomed ? '#i-zoom-out' : '#i-zoom');
  }
  function toggleZoom(): void {
    if (zoomedIn()) {
      cameraMotion.frame(HOME_TARGET, cameraMotion.homeRadius);
      announce('Corpo inteiro.');
    } else {
      const close = CLOSE_UP[activeSlot];
      cameraMotion.frame(new THREE.Vector3(0, close.y, 0), close.radius);
      announce(activeSlot === 'top' ? 'Perto da peça de cima.' : 'Perto da peça de baixo.');
    }
    requestRender();
  }
  function zoomBy(factor: number): void {
    const radius = THREE.MathUtils.clamp(camera.position.distanceTo(controls.target) * factor, MIN_RADIUS, cameraMotion.homeRadius);
    cameraMotion.frame(controls.target, radius);
    requestRender();
  }
  // Enlarged stage: the stage takes the whole window inside the page. The phone's back, Esc and the same button leave.
  const app = stage.closest<HTMLElement>('.app')!;
  const expandButton = $<HTMLButtonElement>('#expand-stage');
  function setExpanded(expanded: boolean): void {
    app.classList.toggle('stage-expanded', expanded);
    expandButton.setAttribute('aria-pressed', String(expanded));
    expandButton.setAttribute('aria-label', expanded ? 'Voltar ao tamanho normal' : 'Ampliar o manequim');
    expandButton.title = expandButton.getAttribute('aria-label')!;
    expandButton.querySelector('use')!.setAttribute('href', expanded ? '#i-shrink' : '#i-expand');
  }
  function toggleExpanded(): void {
    if (app.classList.contains('stage-expanded')) {
      if (history.state?.stageExpanded) history.back(); else setExpanded(false);
    } else {
      history.pushState({ stageExpanded: true }, '');
      setExpanded(true);
    }
  }
  window.addEventListener('popstate', () => setExpanded(Boolean(history.state?.stageExpanded)));
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && app.classList.contains('stage-expanded') && !exportDialog.open) toggleExpanded();
  });
  renderer.domElement.addEventListener('keydown', (event) => {
    if (['+', '=', '-', '0'].includes(event.key)) {
      event.preventDefault();
      if (event.key === '0') return front();
      return zoomBy(event.key === '-' ? 1.25 : .8);
    }
    if (!['ArrowLeft', 'ArrowRight', 'Home'].includes(event.key)) return;
    event.preventDefault();
    if (event.key === 'Home') return front();
    cameraMotion.interact();
    const offset = camera.position.clone().sub(controls.target);
    offset.applyAxisAngle(new THREE.Vector3(0, 1, 0), event.key === 'ArrowLeft' ? -.2 : .2);
    camera.position.copy(controls.target).add(offset);
    controls.update();
    requestRender();
  });

  // --- wear / take off ------------------------------------------------------
  const worn = new Map<Slot, { piece: Piece; object: THREE.Object3D }>();
  const bodyGeometry: { pose: BodyPose; mesh: THREE.Mesh; original: Uint16Array | Uint32Array; setClip: (waist: readonly number[] | undefined, neck: readonly number[] | undefined) => void }[] = [];
  // Visual QA (tools/verify-site/visual-qa.mjs) photographs the stage from any point of the orbit; localhost only.
  if (['localhost', '127.0.0.1'].includes(location.hostname) && params.has('qa')) {
    Object.assign(window, { __qa: { THREE, scene, camera, controls, renderer, worn, mannequin, followCamera, bodyGeometry } });
  }
  const bodyRoots = new Map<BodyPose, THREE.Object3D>();
  function updateGarmentLayering(): void {
    const bottom = worn.get('bottom');
    if (!bottom) return;
    const top = worn.get('top'), table = garmentLayers(bottom.piece.id);
    if (!table) throw new Error('Missing layer data');
    const maskOf = (id: string) => BODY_MASKS[id] ?? BODY_C_MASKS[id];
    if (maskOf(bottom.piece.id).garment_sha256 !== table.bottomHash
      || (top && maskOf(top.piece.id).garment_sha256 !== table.topHashes[top.piece.id])) throw new Error('Layer revision mismatch');
    let ordinal = 0;
    // hem of the top by angle (garment-hem.ts): the part of a hidden triangle below it comes back, cut along the line
    const topPositions: Float32Array[] = [];
    if (top) {
      top.object.updateMatrixWorld(true);
      top.object.traverse(node => {
        if (!(node instanceof THREE.Mesh) || node.userData.hemFill) return;
        const p = node.geometry.getAttribute('position'), v = new THREE.Vector3(), w = new Float32Array(p.count * 3);
        for (let k = 0; k < p.count; k++) {
          v.fromBufferAttribute(p, k).applyMatrix4(node.matrixWorld);
          w[k * 3] = v.x; w[k * 3 + 1] = v.y; w[k * 3 + 2] = v.z;
        }
        topPositions.push(w);
      });
    }
    const hem = top ? hemLine(topPositions) : null;
    bottom.object.updateMatrixWorld(true);
    const nodes: THREE.Mesh[] = [];
    bottom.object.traverse(node => { if (node instanceof THREE.Mesh && !node.userData.hemFill) nodes.push(node); });
    for (const node of nodes) {
      for (const child of [...node.children]) if (child.userData.hemFill) { node.remove(child); (child as THREE.Mesh).geometry.dispose(); }
      const i = ordinal++, meta = table.meshes[i];
      let original = node.userData.layerOriginal as Uint16Array | Uint32Array | undefined;
      if (!original) {
        const indices = node.geometry.index?.array;
        if (!(indices instanceof Uint16Array || indices instanceof Uint32Array) || !meta || indices.length !== meta.triangles * 3
          || node.geometry.getAttribute('position').count !== meta.vertices) throw new Error('Layer primitive mismatch');
        node.geometry = node.geometry.clone();
        node.userData.ownsLayerGeometry = true;
        original = indices.slice();
        node.userData.layerOriginal = original;
      }
      const hidden = top ? expandLayerRanges(table.pairs[top.piece.id]?.[i] ?? [], meta.triangles) : [];
      const visible = visibleBodyIndices(original, [hidden]);
      (node.geometry.index!.array as Uint16Array | Uint32Array).set(visible);
      node.geometry.index!.needsUpdate = true;
      node.geometry.setDrawRange(0, visible.length);
      const fill = hem && hidden.length ? hemFill(node.geometry, original, hidden, hem, node.matrixWorld) : null;
      if (fill) {
        const mesh = new THREE.Mesh(fill, node.material);
        mesh.userData.hemFill = true;
        mesh.castShadow = node.castShadow;
        mesh.receiveShadow = node.receiveShadow;
        node.add(mesh);
      }
    }
    if (ordinal !== table.meshes.length) throw new Error('Layer mesh count mismatch');
  }
  function updateBodyCoverage(): void {
    updateGarmentLayering();
    const pose = bodyPoseForBottom(worn.get('bottom')?.piece.id);
    for (const [key, body] of bodyRoots) body.visible = key === pose;
    const registry: Record<string, BodyMask> = pose === 'C' ? BODY_C_MASKS : BODY_MASKS;
    const activeMasks = [...worn.values()].flatMap(({piece}) => registry[piece.id] ? [registry[piece.id]] : []);
    const bottom = worn.get('bottom')?.piece.id;
    const top = worn.get('top')?.piece.id;
    for (const { pose: meshPose, mesh, original, setClip } of bodyGeometry) {
      if (meshPose !== pose) continue;
      setClip(bottom ? registry[bottom]?.waist_line : undefined, top ? registry[top]?.neck_line : undefined);
      const masks = activeMasks.map(mask => validateBodyMask(mask, BODY_POSES[pose].hash, mesh.name, original.length / 3));
      const visible = visibleBodyIndices(original, masks);
      // Reuse the allocated index buffer instead of allocating a GPU buffer at every selection.
      const index = mesh.geometry.index!;
      (index.array as Uint16Array | Uint32Array).set(visible);
      index.needsUpdate = true;
      mesh.geometry.setDrawRange(0, visible.length);
    }
  }
  let exporting = false;
  exportButton.addEventListener('click', async () => {
    if (exporting || !worn.size || pending.size || bodyState !== 'ready') return;
    exporting = true;
    update();
    try {
      const style = getComputedStyle(document.documentElement);
      const look = encodeLook(wornIds());
      const image = await exportLookImage(renderer, scene, camera, $<HTMLImageElement>('.logo'), {
        paper: style.getPropertyValue('--paper').trim(),
        pink: style.getPropertyValue('--pink').trim(),
        ink: style.getPropertyValue('--ink').trim(),
      }, `LOOK ${look.replace('.', ' + ')}`);
      const bytes = addPngText(new Uint8Array(await image.arrayBuffer()), 'recrialab-look',
        JSON.stringify({ v: LOOK_VERSION, look, url: `${location.origin}/?look=${look}` }));
      const png = new Blob([bytes], { type: 'image/png' });
      exportUrl = URL.createObjectURL(png);
      lookPreview.src = exportUrl;
      saveLook.href = exportUrl;
      saveLook.download = `recria-look-${look.replace('.', '-')}.png`;
      // The code is already stamped on the image; the title says what is worn, with the wardrobe names.
      lookNames.textContent = [...worn.values()].sort((a, b) => a.piece.slot === 'top' ? -1 : b.piece.slot === 'top' ? 1 : 0)
        .map(entry => entry.piece.name).join(' + ');
      lookCode.textContent = `LOOK ${look.replace('.', ' + ')}`;
      // On a phone, sharing leads to the gallery (iOS: "Salvar imagem") or straight to WhatsApp.
      exportFile = new File([png], saveLook.download, { type: 'image/png' });
      shareLook.hidden = !navigator.canShare?.({ files: [exportFile] });
      // When sharing is available (phone), it is the main button: it leads to the gallery or to WhatsApp.
      saveLook.classList.toggle('action-primary', shareLook.hidden);
      exportDialog.showModal();
    } catch {
      say('Não foi possível salvar a imagem.');
    } finally {
      exporting = false;
      update();
    }
  });
  const glbCache = new Map<string, Promise<THREE.Group>>();
  const gltfLoader = new GLTFLoader();
  async function loadVerified(url: string, expectedHash?: string) {
    if (!expectedHash) return gltfLoader.loadAsync(url);
    const response = await fetch(url);
    if (!response.ok) throw new Error('Model download failed');
    const data = await response.arrayBuffer();
    const hash = [...new Uint8Array(await crypto.subtle.digest('SHA-256', data))].map(n => n.toString(16).padStart(2, '0')).join('');
    if (hash !== expectedHash) throw new Error('Model revision does not match its body mask');
    return gltfLoader.parseAsync(data, '');
  }
  const readyCache = new Map<string, { model: THREE.Group; bytes: number }>();
  function resources(model: THREE.Group) {
    const geometries = new Set<THREE.BufferGeometry>();
    const materials = new Set<THREE.Material>();
    const textures = new Set<THREE.Texture>();
    model.traverse(node => {
      if (!(node instanceof THREE.Mesh)) return;
      geometries.add(node.geometry);
      for (const material of Array.isArray(node.material) ? node.material : [node.material]) {
        materials.add(material);
        for (const value of Object.values(material)) if (value instanceof THREE.Texture) textures.add(value);
      }
    });
    return { geometries, materials, textures };
  }
  function textureEstimate(model: THREE.Group): number {
    let bytes = 0;
    for (const texture of resources(model).textures) {
      const image = texture.image as { width?: number; height?: number } | undefined;
      bytes += (image?.width ?? 0) * (image?.height ?? 0) * 4 * (texture.generateMipmaps ? 4 / 3 : 1);
    }
    return bytes; // RGBA8 estimate, not a GPU memory measurement.
  }
  function pruneCache(): void {
    const protectedKeys = new Set<string>();
    for (const { piece } of worn.values()) protectedKeys.add(piece.url);
    for (const request of pending.values()) {
      const piece = PIECES.find(p => p.id === request.pieceId);
      if (piece) protectedKeys.add(piece.url);
    }
    const evicted = evictionCandidates([...readyCache].map(([key, value]) => ({ key, bytes: value.bytes })), protectedKeys, 64 * 1024 ** 2);
    for (const key of evicted) {
      const entry = readyCache.get(key)!;
      const owned = resources(entry.model);
      for (const geometry of owned.geometries) geometry.dispose();
      for (const material of owned.materials) material.dispose();
      const images = new Set<ImageBitmap>();
      for (const texture of owned.textures) {
        if (typeof ImageBitmap !== 'undefined' && texture.image instanceof ImageBitmap) images.add(texture.image);
        texture.dispose();
      }
      for (const image of images) image.close();
      readyCache.delete(key);
      glbCache.delete(key);
    }
  }

  async function buildObject(piece: Piece): Promise<THREE.Object3D> {
    if (!glbCache.has(piece.url)) {
      glbCache.set(
        piece.url,
        loadVerified(piece.url, (BODY_MASKS[piece.id] ?? BODY_C_MASKS[piece.id])?.garment_sha256).then(({scene: model}) => {
          matteFabric(model, piece.id);
          return model;
        }).catch(error => { glbCache.delete(piece.url); throw error; }),
      );
    }
    const template = await glbCache.get(piece.url)!;
    const entry = readyCache.get(piece.url) ?? { model: template, bytes: textureEstimate(template) };
    readyCache.delete(piece.url);
    readyCache.set(piece.url, entry);
    // Shared metres/origin/orientation: preserve glTF transforms, normals and material sides.
    return template.clone();
  }

  // Keeps the previous piece while loading; the last choice wins.
  let requestId = 0;
  const pending = new Map<Slot, { id: number; pieceId: string }>();
  function detach(slot: Slot): void {
    const entry = worn.get(slot);
    if (!entry) return;
    scene.remove(entry.object);
    entry.object.traverse(node => {
      for (const child of [...node.children]) if (child.userData.hemFill) { node.remove(child); (child as THREE.Mesh).geometry.dispose(); }
      if (node instanceof THREE.Mesh && node.userData.ownsLayerGeometry) {
        node.geometry.dispose();
        delete node.userData.ownsLayerGeometry;
        delete node.userData.layerOriginal;
      }
    });
    worn.delete(slot);
    updateBodyCoverage();
    requestRender();
  }
  function remove(slot: Slot): void {
    const name = worn.get(slot)?.piece.name;
    pending.delete(slot);
    detach(slot);
    pruneCache();
    update();
    if (name) announce(`${name} saiu do look.`);
  }
  async function toggle(piece: Piece): Promise<void> {
    if (bodyState !== 'ready') return;
    if (pending.get(piece.slot)?.pieceId === piece.id || worn.get(piece.slot)?.piece.id === piece.id) {
      return remove(piece.slot);
    }
    const id = ++requestId;
    pending.set(piece.slot, { id, pieceId: piece.id });
    update();
    try {
      const [object] = await Promise.all([buildObject(piece),piece.slot==='bottom'?loadGarmentLayers(piece.id):Promise.resolve()]);
      if (pending.get(piece.slot)?.id !== id) return;
      detach(piece.slot);
      scene.add(object);
      worn.set(piece.slot, { piece, object });
      updateBodyCoverage();
      requestRender();
      announce(`${piece.name} no look.`);
    } catch {
      if (pending.get(piece.slot)?.id === id) say(`Não foi possível carregar: ${piece.name}.`);
    } finally {
      if (pending.get(piece.slot)?.id === id) {
        pending.delete(piece.slot);
        update();
      }
      pruneCache();
    }
  }

  const pieceButton = (piece: Piece): string => `
    <button class="card" data-piece="${piece.id}" data-slot="${piece.slot}" aria-pressed="false" aria-label="${piece.name}">
      <span class="thumb"><img src="${piece.thumb}" alt="" draggable="false" loading="lazy"><span class="selection-mark">${icon('check')}</span></span>
      <span class="name">${piece.name}</span>
    </button>`;

  let activeSlot: Slot = 'top';
  let filter: string | null = null;
  for (const slot of ['top', 'bottom'] as const) {
    $(`[data-count="${slot}"]`).textContent = String(PIECES.filter(piece => piece.slot === slot).length);
  }

  function update(): void {
    syncLookUrl();
    if (bodyState === 'ready') markFigure();
    renderer.domElement.setAttribute('aria-label', stageLabel([...worn.values()].map(entry => entry.piece.name)));
    exportButton.disabled = exporting || !worn.size || pending.size > 0 || bodyState !== 'ready';
    exportButton.setAttribute('aria-busy', String(exporting));
    exportButton.title = !worn.size ? 'Nada vestido ainda' : pending.size ? 'Carregando a peça' : 'Salvar o look como imagem';
    for (const card of grid.querySelectorAll<HTMLElement>('[data-piece]')) {
      const slot = card.dataset.slot as Slot;
      const selected = worn.get(slot)?.piece.id === card.dataset.piece;
      const loading = pending.get(slot)?.pieceId === card.dataset.piece;
      if (card instanceof HTMLButtonElement) card.disabled = bodyState !== 'ready';
      card.classList.toggle('worn', selected);
      card.classList.toggle('loading', loading);
      card.setAttribute('aria-pressed', String(selected));
      card.setAttribute('aria-busy', String(loading));
    }
  }
  const filters = $('#filters');
  function renderPieces(): void {
    const ids: readonly string[] | undefined = FILTERS[activeSlot].find(f => f.label === filter)?.ids;
    const order = wardrobeOrder(activeSlot, PIECES.map(piece => piece.id));
    const pieces = PIECES.filter(piece => piece.slot === activeSlot && (!ids || ids.includes(piece.id)))
      .sort((a, b) => order.indexOf(a.id) - order.indexOf(b.id));
    for (const button of document.querySelectorAll<HTMLElement>('#chips [data-slot]')) {
      const active = button.dataset.slot === activeSlot;
      button.classList.toggle('active', active);
      button.setAttribute('aria-pressed', String(active));
    }
    filters.innerHTML = FILTERS[activeSlot].map(f =>
      `<button class="filter" data-filter="${f.label}" aria-pressed="${f.label === filter}">${f.label}</button>`).join('');
    grid.innerHTML = pieces.map(pieceButton).join('');
    grid.scrollTo({ left: 0, top: 0 });
    $('#results-count').textContent = `${pieces.length} peça${pieces.length === 1 ? '' : 's'}`;
    update();
  }

  // Confirmation ("… no look.") for screen readers only: the marked card and the mannequin already show it.
  const announcement = $('#announcement');
  function announce(message: string): void {
    announcement.textContent = message;
  }
  // The toast over the stage is only for a passing error; the middle of the stage, for a mannequin that did not load.
  let toastTimer = 0;
  function say(message: string): void {
    toast.textContent = message;
    toast.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove('show'), 3200);
  }

  document.addEventListener('click', (event) => {
    const target = event.target;
    if (!(target instanceof Element)) return;
    const chip = target.closest<HTMLElement>('#chips [data-slot]');
    if (chip) {
      activeSlot = chip.dataset.slot as Slot;
      filter = null;
      return renderPieces();
    }
    const tag = target.closest<HTMLElement>('#filters [data-filter]');
    if (tag) {
      // One filter at a time; choosing the active one shows all pieces again.
      filter = filter === tag.dataset.filter ? null : tag.dataset.filter!;
      return renderPieces();
    }
    const card = target.closest<HTMLElement>('[data-piece]');
    const piece = card && PIECES.find((p) => p.id === card.dataset.piece);
    if (piece) return void toggle(piece);
    if (target.closest('[data-reset]')) return front();
    if (target.closest('#zoom-stage')) return toggleZoom();
    if (target.closest('#expand-stage')) return toggleExpanded();
  });
  wide.addEventListener('change', update);
  // A document in the background does not need to keep rendering the rotation.
  document.addEventListener('visibilitychange', () => { activePointers.clear(); interacted(); });
  renderPieces();
  stage.setAttribute('aria-busy', 'true');
  stageStatus.textContent = 'Carregando manequim…';
  void Promise.all((['B', 'C'] as const).map(async pose => {
    const { scene: body } = await loadVerified(BODY_POSES[pose].url, BODY_POSES[pose].hash);
    const registry = pose === 'B' ? BODY_MASKS : BODY_C_MASKS;
    body.traverse(node => {
      if (!(node instanceof THREE.Mesh)) return;
      const indices = node.geometry.index?.array;
      if (!(indices instanceof Uint16Array || indices instanceof Uint32Array)) throw new Error('Unexpected body topology');
      for (const mask of Object.values(registry)) validateBodyMask(mask, BODY_POSES[pose].hash, node.name, indices.length / 3);
      node.geometry = node.geometry.clone();
      if (!(node.material instanceof THREE.MeshStandardMaterial)) throw new Error('Unexpected body material');
      node.material = node.material.clone();
      bodyGeometry.push({pose, mesh: node, original: indices.slice(), setClip: bodyClip(node.material)});
    });
    body.visible = pose === 'B';
    bodyRoots.set(pose, body);
    mannequin.add(body);
  })).then(() => {
    updateBodyCoverage();
    bodyState = 'ready';
    stageStatus.textContent = '';
    requestRender();
    update();
    void restoreInitialLook().finally(() => { lookRestored = true; }).then(() => {
      // First visit: the mannequin turns once on its own, showing that it turns, with no words on screen.
      let visited = true;
      try {
        visited = localStorage.getItem('recrialab-visited') === '1';
        localStorage.setItem('recrialab-visited', '1');
      } catch { /* storage blocked: no showcase */ }
      if (!visited) cameraMotion.showcase();
    });
  }).catch((error) => {
    bodyState = 'error';
    stageStatus.textContent = 'Não foi possível carregar o manequim. Recarregue a página.';
    console.error('[body] failed to load', error);
    update();
  }).finally(() => stage.setAttribute('aria-busy', 'false'));
}
