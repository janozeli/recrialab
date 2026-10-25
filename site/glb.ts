/** Minimal GLB reader for the tests: JSON, triangles and texture sizes. No dependencies. */
export interface GlbSummary {
  triangles: number;
  textures: { width: number; height: number; mime: string; bytes: number }[];
}

export function readGlb(bytes: Uint8Array): GlbSummary {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  if (view.getUint32(0, true) !== 0x46546c67) throw new Error('not a GLB');
  const jsonLength = view.getUint32(12, true);
  const gltf = JSON.parse(new TextDecoder().decode(bytes.subarray(20, 20 + jsonLength)));
  const binStart = 20 + jsonLength + 8;
  let triangles = 0;
  for (const mesh of gltf.meshes ?? []) for (const prim of mesh.primitives ?? []) {
    if ((prim.mode ?? 4) !== 4) continue;
    const count = prim.indices !== undefined ? gltf.accessors[prim.indices].count : gltf.accessors[prim.attributes.POSITION].count;
    triangles += count / 3;
  }
  const textures = (gltf.images ?? []).map((image: { bufferView?: number; mimeType?: string }) => {
    if (image.bufferView === undefined) throw new Error('texture outside the GLB');
    const bv = gltf.bufferViews[image.bufferView];
    const data = bytes.subarray(binStart + (bv.byteOffset ?? 0), binStart + (bv.byteOffset ?? 0) + bv.byteLength);
    return { ...imageSize(data), mime: image.mimeType ?? '?', bytes: bv.byteLength };
  });
  return { triangles, textures };
}

/** Width/height of a PNG, JPEG or WebP from its header. */
export function imageSize(d: Uint8Array): { width: number; height: number } {
  const v = new DataView(d.buffer, d.byteOffset, d.byteLength);
  if (d[0] === 0x89 && d[1] === 0x50) return { width: v.getUint32(16), height: v.getUint32(20) };
  if (d[0] === 0xff && d[1] === 0xd8) {
    for (let at = 2; at < d.length;) {
      const marker = d[at + 1], length = v.getUint16(at + 2);
      if (marker >= 0xc0 && marker <= 0xcf && ![0xc4, 0xc8, 0xcc].includes(marker))
        return { height: v.getUint16(at + 5), width: v.getUint16(at + 7) };
      at += 2 + length;
    }
  }
  if (String.fromCharCode(...d.subarray(0, 4)) === 'RIFF' && String.fromCharCode(...d.subarray(8, 12)) === 'WEBP') {
    const kind = String.fromCharCode(...d.subarray(12, 16));
    if (kind === 'VP8X') return { width: 1 + (v.getUint32(24, true) & 0xffffff), height: 1 + (v.getUint32(27, true) & 0xffffff) };
    if (kind === 'VP8L') { const b = v.getUint32(21, true); return { width: 1 + (b & 0x3fff), height: 1 + ((b >> 14) & 0x3fff) }; }
    if (kind === 'VP8 ') return { width: v.getUint16(26, true) & 0x3fff, height: v.getUint16(28, true) & 0x3fff };
  }
  throw new Error('unknown image format');
}

/** Positions of every vertex in world space (node translation, rotation and scale). */
export function readPositions(bytes: Uint8Array): Float32Array {
  return readMesh(bytes).positions;
}

/** The whole mesh in world space: positions, UV (0 where the primitive has none) and triangles with global indices. */
export function readMesh(bytes: Uint8Array): { positions: Float32Array; uvs: Float32Array; indices: Uint32Array; materials: Int32Array } {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const jsonLength = view.getUint32(12, true);
  const gltf = JSON.parse(new TextDecoder().decode(bytes.subarray(20, 20 + jsonLength)));
  const binStart = 20 + jsonLength + 8;
  const out: number[] = [], uvs: number[] = [], tris: number[] = [], materials: number[] = [];
  // 3x4 matrix by rows: [r00 r01 r02 tx, r10 r11 r12 ty, r20 r21 r22 tz]
  const local = (node: { translation?: number[]; rotation?: number[]; scale?: number[]; matrix?: number[] }): number[] => {
    if (node.matrix) { const m = node.matrix; return [m[0], m[4], m[8], m[12], m[1], m[5], m[9], m[13], m[2], m[6], m[10], m[14]]; }
    const [x, y, z, w] = node.rotation ?? [0, 0, 0, 1];
    const [sx, sy, sz] = node.scale ?? [1, 1, 1];
    const [tx, ty, tz] = node.translation ?? [0, 0, 0];
    return [
      (1 - 2 * (y * y + z * z)) * sx, 2 * (x * y - z * w) * sy, 2 * (x * z + y * w) * sz, tx,
      2 * (x * y + z * w) * sx, (1 - 2 * (x * x + z * z)) * sy, 2 * (y * z - x * w) * sz, ty,
      2 * (x * z - y * w) * sx, 2 * (y * z + x * w) * sy, (1 - 2 * (x * x + y * y)) * sz, tz,
    ];
  };
  const mul = (a: number[], b: number[]) => {
    const r: number[] = [];
    for (let i = 0; i < 3; i++) for (let j = 0; j < 4; j++)
      r.push(a[i * 4] * b[j] + a[i * 4 + 1] * b[4 + j] + a[i * 4 + 2] * b[8 + j] + (j === 3 ? a[i * 4 + 3] : 0));
    return r;
  };
  const visit = (index: number, parent: number[]) => {
    const node = gltf.nodes[index];
    const m = mul(parent, local(node));
    if (node.mesh !== undefined) for (const prim of gltf.meshes[node.mesh].primitives) {
      const acc = gltf.accessors[prim.attributes.POSITION];
      if (acc.componentType !== 5126) throw new Error('POSITION is not float32');
      const bv = gltf.bufferViews[acc.bufferView];
      const stride = bv.byteStride ?? 12, base = binStart + (bv.byteOffset ?? 0) + (acc.byteOffset ?? 0);
      const first = out.length / 3;
      for (let i = 0; i < acc.count; i++) {
        const x = view.getFloat32(base + i * stride, true), y = view.getFloat32(base + i * stride + 4, true), z = view.getFloat32(base + i * stride + 8, true);
        for (let k = 0; k < 3; k++) out.push(m[k * 4] * x + m[k * 4 + 1] * y + m[k * 4 + 2] * z + m[k * 4 + 3]);
      }
      const uv = prim.attributes.TEXCOORD_0 !== undefined ? gltf.accessors[prim.attributes.TEXCOORD_0] : null;
      if (uv && uv.componentType !== 5126) throw new Error('TEXCOORD_0 is not float32');
      const uvView = uv && gltf.bufferViews[uv.bufferView];
      const uvBase = uv ? binStart + (uvView.byteOffset ?? 0) + (uv.byteOffset ?? 0) : 0, uvStride = uvView?.byteStride ?? 8;
      for (let i = 0; i < acc.count; i++)
        uvs.push(uv ? view.getFloat32(uvBase + i * uvStride, true) : 0, uv ? view.getFloat32(uvBase + i * uvStride + 4, true) : 0);
      if ((prim.mode ?? 4) !== 4) throw new Error('primitive is not a triangle list');
      const before = tris.length;
      if (prim.indices === undefined) for (let i = 0; i < acc.count; i++) tris.push(first + i);
      else {
        const ia = gltf.accessors[prim.indices], iv = gltf.bufferViews[ia.bufferView];
        const ibase = binStart + (iv.byteOffset ?? 0) + (ia.byteOffset ?? 0);
        const size = ({ 5121: 1, 5123: 2, 5125: 4 } as Record<number, number>)[ia.componentType];
        if (!size) throw new Error('index of unknown type');
        for (let i = 0; i < ia.count; i++)
          tris.push(first + (size === 1 ? view.getUint8(ibase + i) : size === 2 ? view.getUint16(ibase + 2 * i, true) : view.getUint32(ibase + 4 * i, true)));
      }
      for (let t = before; t < tris.length; t += 3) materials.push(prim.material ?? -1);
    }
    for (const child of node.children ?? []) visit(child, m);
  };
  for (const root of gltf.scenes[gltf.scene ?? 0].nodes) visit(root, [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0]);
  return { positions: Float32Array.from(out), uvs: Float32Array.from(uvs), indices: Uint32Array.from(tris), materials: Int32Array.from(materials) };
}
