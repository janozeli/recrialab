import { expandLayerRanges } from './garment-layer-data';

export interface BodyMask {
  body_sha256: string;
  garment_sha256: string;
  piece_id: string;
  meshes: { name: string; primitive_index: number; triangle_count: number; hidden_ranges: number[][] }[];
  /** Top of the waistband of the bottom piece by angle around the body (tools/fit/waist.py). */
  waist_line?: number[];
  /** Top of the collar of the top piece by angle around the neck (tools/fit/collar.py). */
  neck_line?: number[];
  /** Hem of the sleeves of the top piece by angle around each arm, right then left (tools/fit/sleeve.py). */
  sleeve_line?: number[];
}

// Same numbers as tools/fit/waist.py: the torso between the waistband line and BAND below it is discarded per pixel.
export const WAIST_STEPS = 72, WAIST_TORSO = 0.17, WAIST_BAND = 0.10;
// Same numbers as tools/fit/collar.py: the neck near the axis between the collar line and the band below it is discarded.
export const NECK_STEPS = 72, NECK_AXIS_Z = -0.008, NECK_RADIUS = 0.075, NECK_BAND = 0.08;
// Same numbers as tools/fit/sleeve.py: the arm near its leaning axis between the sleeve hem line and the band above it is discarded.
export const SLEEVE_STEPS = 72, SLEEVE_ARM_X = 0.17, SLEEVE_RADIUS = 0.06, SLEEVE_BAND = 0.10;
export const SLEEVE_AXIS = { y: 1.15, x: 0.215, z: -0.033, dx: -0.07, dz: -0.127 };

/** Discards, in the body shader, the torso under the waistband, the neck under the collar and the arm in the sleeve: the edge follows the garment line instead of whole triangles. */
export function bodyClip(material: { onBeforeCompile: (shader: { uniforms: Record<string, { value: unknown }>; vertexShader: string; fragmentShader: string }) => void; customProgramCacheKey?: () => string }) {
  const uniforms = { uWaist: { value: new Float32Array(WAIST_STEPS) }, uWaistOn: { value: 0 },
    uNeck: { value: new Float32Array(NECK_STEPS) }, uNeckOn: { value: 0 },
    uSleeve: { value: new Float32Array(2 * SLEEVE_STEPS) }, uSleeveOn: { value: 0 } };
  material.onBeforeCompile = shader => {
    Object.assign(shader.uniforms, uniforms);
    shader.vertexShader = shader.vertexShader
      .replace('#include <common>', '#include <common>\nvarying vec3 vWaistBody;')
      .replace('#include <begin_vertex>', '#include <begin_vertex>\nvWaistBody = transformed;');
    shader.fragmentShader = shader.fragmentShader
      .replace('#include <common>', `#include <common>
varying vec3 vWaistBody;
uniform float uWaist[${WAIST_STEPS}];
uniform float uWaistOn;
uniform float uNeck[${NECK_STEPS}];
uniform float uNeckOn;
uniform float uSleeve[${2 * SLEEVE_STEPS}];
uniform float uSleeveOn;`)
      .replace('#include <clipping_planes_fragment>', `#include <clipping_planes_fragment>
if (uWaistOn > 0.5 && abs(vWaistBody.x) < ${WAIST_TORSO.toFixed(3)}) {
  float t = mod(degrees(atan(vWaistBody.x, vWaistBody.z)) + 360.0, 360.0) / ${(360 / WAIST_STEPS).toFixed(1)};
  int i = int(floor(t)) % ${WAIST_STEPS};
  float y = mix(uWaist[i], uWaist[(i + 1) % ${WAIST_STEPS}], fract(t));
  if (vWaistBody.y < y && vWaistBody.y > y - ${WAIST_BAND.toFixed(3)}) discard;
}
vec2 neckP = vec2(vWaistBody.x, vWaistBody.z - (${NECK_AXIS_Z.toFixed(3)}));
if (uNeckOn > 0.5 && length(neckP) < ${NECK_RADIUS.toFixed(3)}) {
  float t = mod(degrees(atan(neckP.x, neckP.y)) + 360.0, 360.0) / ${(360 / NECK_STEPS).toFixed(1)};
  int i = int(floor(t)) % ${NECK_STEPS};
  float y = mix(uNeck[i], uNeck[(i + 1) % ${NECK_STEPS}], fract(t));
  if (vWaistBody.y < y && vWaistBody.y > y - ${NECK_BAND.toFixed(3)}) discard;
}
float sleeveH = vWaistBody.y - ${SLEEVE_AXIS.y.toFixed(3)};
vec2 sleeveP = vec2(abs(vWaistBody.x) - (${SLEEVE_AXIS.x.toFixed(3)} + (${SLEEVE_AXIS.dx.toFixed(3)}) * sleeveH),
  vWaistBody.z - (${SLEEVE_AXIS.z.toFixed(3)} + (${SLEEVE_AXIS.dz.toFixed(3)}) * sleeveH));
if (uSleeveOn > 0.5 && abs(vWaistBody.x) > ${SLEEVE_ARM_X.toFixed(3)} && length(sleeveP) < ${SLEEVE_RADIUS.toFixed(3)}) {
  float t = mod(degrees(atan(sleeveP.x, sleeveP.y)) + 360.0, 360.0) / ${(360 / SLEEVE_STEPS).toFixed(1)};
  int o = vWaistBody.x > 0.0 ? 0 : ${SLEEVE_STEPS};
  int i = int(floor(t)) % ${SLEEVE_STEPS};
  float y = mix(uSleeve[o + i], uSleeve[o + (i + 1) % ${SLEEVE_STEPS}], fract(t));
  if (vWaistBody.y > y && vWaistBody.y < y + ${SLEEVE_BAND.toFixed(3)}) discard;
}`);
  };
  material.customProgramCacheKey = () => 'body-clip';
  return (waist: readonly number[] | undefined, neck: readonly number[] | undefined, sleeve?: readonly number[]) => {
    if (waist && waist.length !== WAIST_STEPS) throw new Error('Waist line does not match the body clip');
    if (neck && neck.length !== NECK_STEPS) throw new Error('Neck line does not match the body clip');
    if (sleeve && sleeve.length !== 2 * SLEEVE_STEPS) throw new Error('Sleeve line does not match the body clip');
    uniforms.uWaistOn.value = waist ? 1 : 0;
    if (waist) uniforms.uWaist.value.set(waist);
    uniforms.uNeckOn.value = neck ? 1 : 0;
    if (neck) uniforms.uNeck.value.set(neck);
    uniforms.uSleeveOn.value = sleeve ? 1 : 0;
    if (sleeve) uniforms.uSleeve.value.set(sleeve);
  };
}

export function validateBodyMask(mask: BodyMask, bodyHash: string, name: string, triangleCount: number): number[] {
  const mesh = mask.meshes.find(m => m.name === name && m.primitive_index === 0);
  if (mask.body_sha256 !== bodyHash || !mesh || mesh.triangle_count !== triangleCount) {
    throw new Error('Body mask belongs to another body revision');
  }
  // Ranges [start, end]: the plain index list weighed 3.5 MB in the JS (tools/fit/mask_io.py).
  return expandLayerRanges(mesh.hidden_ranges, triangleCount);
}

/** Hide covered body triangles at render time; never alter the garment or source body. */
export function visibleBodyIndices(original: Uint16Array | Uint32Array, masks: readonly (readonly number[])[]): Uint16Array | Uint32Array {
  const hidden = new Set(masks.flat());
  const count = original.length / 3;
  if (!Number.isInteger(count) || [...hidden].some(i => !Number.isInteger(i) || i < 0 || i >= count)) {
    throw new Error('Body mask does not match the source topology');
  }
  const result = original instanceof Uint32Array ? new Uint32Array(original.length - hidden.size * 3) : new Uint16Array(original.length - hidden.size * 3);
  let offset = 0;
  for (let triangle = 0; triangle < count; triangle++) {
    if (!hidden.has(triangle)) {
      result.set(original.subarray(triangle * 3, triangle * 3 + 3), offset);
      offset += 3;
    }
  }
  return result;
}
