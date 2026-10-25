// Fly of short 008: how much of the lining shows from the front. Used by fit.test.ts.
import { readMesh } from './glb';

const FLY_LINING_UV = [[0.131, 0.170, 0.543, 0.578], [0.493, 0.543, 0.829, 0.892]];
export const MAX_FLY_LINING_CM2 = 1;

/** Area (cm²) of the fly lining seen from the front: rays parallel to −z on a 2 mm grid over the fly. */
export function flyLiningVisibleCm2(bytes: Uint8Array): number {
  const { positions: p, uvs, indices, materials } = readMesh(bytes);
  const step = 0.002, x0 = -0.06, x1 = 0.06, y0 = 0.86, y1 = 1.02;
  const tris: number[] = [];
  for (let t = 0; t < indices.length; t += 3) {
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    for (let k = 0; k < 3; k++) { const i = indices[t + k]; minX = Math.min(minX, p[3 * i]); maxX = Math.max(maxX, p[3 * i]); minY = Math.min(minY, p[3 * i + 1]); maxY = Math.max(maxY, p[3 * i + 1]); }
    if (maxX >= x0 && minX <= x1 && maxY >= y0 && minY <= y1) tris.push(t);
  }
  let lining = 0;
  for (let y = y0; y <= y1; y += step) for (let x = x0; x <= x1; x += step) {
    let bestZ = -Infinity, bestU = 0, bestV = 0, bestMaterial = -1;
    for (const t of tris) {
      const [a, b, c] = [indices[t], indices[t + 1], indices[t + 2]];
      const d = (p[3 * b + 1] - p[3 * c + 1]) * (p[3 * a] - p[3 * c]) + (p[3 * c] - p[3 * b]) * (p[3 * a + 1] - p[3 * c + 1]);
      if (Math.abs(d) < 1e-12) continue;
      const l1 = ((p[3 * b + 1] - p[3 * c + 1]) * (x - p[3 * c]) + (p[3 * c] - p[3 * b]) * (y - p[3 * c + 1])) / d;
      const l2 = ((p[3 * c + 1] - p[3 * a + 1]) * (x - p[3 * c]) + (p[3 * a] - p[3 * c]) * (y - p[3 * c + 1])) / d;
      const l3 = 1 - l1 - l2;
      if (l1 < 0 || l2 < 0 || l3 < 0) continue;
      const z = l1 * p[3 * a + 2] + l2 * p[3 * b + 2] + l3 * p[3 * c + 2];
      if (z > bestZ) { bestZ = z; bestMaterial = materials[t / 3]; bestU = l1 * uvs[2 * a] + l2 * uvs[2 * b] + l3 * uvs[2 * c]; bestV = l1 * uvs[2 * a + 1] + l2 * uvs[2 * b + 1] + l3 * uvs[2 * c + 1]; }
    }
    // the UV rectangles apply to the piece texture (material 0), not to the back photo
    if (bestZ > 0 && bestMaterial === 0 && FLY_LINING_UV.some(([u0, u1, v0, v1]) => bestU >= u0 && bestU <= u1 && bestV >= v0 && bestV <= v1)) lining++;
  }
  return lining * step * step * 1e4;
}
