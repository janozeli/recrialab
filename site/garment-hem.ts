import * as THREE from 'three';

// Top over bottom: the layer table hides every triangle of the bottom piece that lies under the top. A triangle
// crossing the hem of the top would vanish whole, and the trousers would end in a jagged edge just below the hem
// (visual QA, junction). Here the part of a hidden triangle below the hem comes back, cut along the hem line: the edge
// follows the hem instead of the triangle edge.
// Same numbers as tools/fit/top_hem.py (layer_check.py measures with them).
export const HEM_STEPS = 72, HEM_TORSO = 0.18;

/** Hem of the top by angle around the body (0° = front, atan2(x, z)): the lowest height of the torso fabric
 * (|x| < HEM_TORSO, leaving out the sleeve at the side) in each slice; an empty slice (open front) interpolates. */
export function hemLine(positions: ArrayLike<number>[]): Float32Array {
  const hem = new Float32Array(HEM_STEPS).fill(Infinity);
  for (const p of positions) for (let i = 0; i < p.length; i += 3) {
    const x = p[i], y = p[i + 1], z = p[i + 2];
    if (Math.abs(x) >= HEM_TORSO) continue;
    const k = Math.floor(((Math.atan2(x, z) * 180 / Math.PI + 360) % 360) / (360 / HEM_STEPS)) % HEM_STEPS;
    if (y < hem[k]) hem[k] = y;
  }
  const ok = [...hem.keys()].filter(k => Number.isFinite(hem[k]));
  if (!ok.length) return hem.fill(-Infinity);   // no torso: nothing comes back
  const out = hem.slice();
  for (let k = 0; k < HEM_STEPS; k++) {
    if (Number.isFinite(hem[k])) continue;
    const prev = [...ok].reverse().find(j => j < k) ?? ok[ok.length - 1], next = ok.find(j => j > k) ?? ok[0];
    const span = (next - prev + HEM_STEPS) % HEM_STEPS || HEM_STEPS, t = ((k - prev + HEM_STEPS) % HEM_STEPS) / span;
    out[k] = hem[prev] * (1 - t) + hem[next] * t;
  }
  return out;
}

/** Hem height at the point (x, z), interpolated between slices. */
export function hemAt(hem: Float32Array, x: number, z: number): number {
  const t = ((Math.atan2(x, z) * 180 / Math.PI + 360) % 360) / (360 / HEM_STEPS);
  const i = Math.floor(t) % HEM_STEPS, f = t - Math.floor(t);
  return hem[i] * (1 - f) + hem[(i + 1) % HEM_STEPS] * f;
}

/** The part of the hidden triangles below the hem, with every attribute interpolated at the cut. `toWorld` takes
 * the local position to world space (the space of the hem). Returns non-indexed attributes in local space. */
export function hemFill(geometry: THREE.BufferGeometry, original: ArrayLike<number>, hidden: readonly number[],
  hem: Float32Array, toWorld: THREE.Matrix4): THREE.BufferGeometry | null {
  if (!hem.some(Number.isFinite)) return null;   // no hem (a top without torso): the table decides
  const names = Object.keys(geometry.attributes);
  const attrs = names.map(n => geometry.getAttribute(n) as THREE.BufferAttribute | THREE.InterleavedBufferAttribute);
  const out = attrs.map(() => [] as number[]);
  const pos = geometry.getAttribute('position'), v = new THREE.Vector3();
  // one computation per vertex (a vertex is shared by several hidden triangles)
  const cortes = new Map<number, P>();
  type P = { s: number; a: number[][] };
  const point = (i: number): P => {
    let p = cortes.get(i);
    if (!p) {
      v.fromBufferAttribute(pos, i).applyMatrix4(toWorld);
      p = { s: hemAt(hem, v.x, v.z) - v.y, a: attrs.map(at => Array.from({ length: at.itemSize }, (_, c) => at.getComponent(i, c))) };
      cortes.set(i, p);
    }
    return p;
  };
  const mistura = (p: P, q: P): P => {
    const t = p.s / (p.s - q.s);
    return { s: 0, a: p.a.map((x, k) => x.map((c, j) => c + (q.a[k][j] - c) * t)) };
  };
  for (const tri of hidden) {
    const a = original[tri * 3], b = original[tri * 3 + 1], c = original[tri * 3 + 2];
    const ps = [a, b, c].map(point);
    if (ps.every(p => p.s < 0)) continue;
    const poly: P[] = [];
    for (let j = 0; j < 3; j++) {
      const p = ps[j], q = ps[(j + 1) % 3];
      if (p.s >= 0) poly.push(p);
      if ((p.s >= 0) !== (q.s >= 0)) poly.push(mistura(p, q));
    }
    for (let j = 1; j + 1 < poly.length; j++) for (const p of [poly[0], poly[j], poly[j + 1]]) p.a.forEach((x, k) => out[k].push(...x));
  }
  if (!out[0].length) return null;
  const g = new THREE.BufferGeometry();
  names.forEach((n, k) => g.setAttribute(n, new THREE.Float32BufferAttribute(out[k], attrs[k].itemSize)));
  return g;
}
