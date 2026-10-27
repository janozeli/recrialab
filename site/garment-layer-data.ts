// Layer tables (assets/layers/NNN.json, one per bottom): which triangles of the bottom each top hides. Written by
// tools/fit/layer_tables.py; fetched on demand, since each table is only needed while that bottom is worn.
import p001 from './assets/layers/001.json' with { type: 'file' };
import p002 from './assets/layers/002.json' with { type: 'file' };
import p003 from './assets/layers/003.json' with { type: 'file' };
import p004 from './assets/layers/004.json' with { type: 'file' };
import p005 from './assets/layers/005.json' with { type: 'file' };
import p006 from './assets/layers/006.json' with { type: 'file' };
import p007 from './assets/layers/007.json' with { type: 'file' };
import p008 from './assets/layers/008.json' with { type: 'file' };
import p009 from './assets/layers/009.json' with { type: 'file' };
import p010 from './assets/layers/010.json' with { type: 'file' };
import p011 from './assets/layers/011.json' with { type: 'file' };
import p012 from './assets/layers/012.json' with { type: 'file' };
import p013 from './assets/layers/013.json' with { type: 'file' };
import p014 from './assets/layers/014.json' with { type: 'file' };
import p015 from './assets/layers/015.json' with { type: 'file' };

export interface LayerTable {
  bottomHash: string;
  generatorHash: string;
  topHashes: Record<string, string>;
  meshes: { vertices: number; triangles: number }[];
  pairs: Record<string, number[][][]>;
}

// with type 'file', the import is the URL of the published JSON
const urls: Record<string, string> = {
  '001': p001 as unknown as string,
  '002': p002 as unknown as string,
  '003': p003 as unknown as string,
  '004': p004 as unknown as string,
  '005': p005 as unknown as string,
  '006': p006 as unknown as string,
  '007': p007 as unknown as string,
  '008': p008 as unknown as string,
  '009': p009 as unknown as string,
  '010': p010 as unknown as string,
  '011': p011 as unknown as string,
  '012': p012 as unknown as string,
  '013': p013 as unknown as string,
  '014': p014 as unknown as string,
  '015': p015 as unknown as string,
};
const cache = new Map<string, LayerTable>();
const pending = new Map<string, Promise<LayerTable>>();

export async function loadGarmentLayers(id: string): Promise<LayerTable> {
  if (cache.has(id)) return cache.get(id)!;
  if (!pending.has(id)) pending.set(id, fetch(urls[id])
    .then(r => { if (!r.ok) throw new Error('Layer data unavailable'); return r.json(); })
    .then(data => { cache.set(id, data); return data; })
    .finally(() => pending.delete(id)));
  return pending.get(id)!;
}

export function garmentLayers(id: string): LayerTable | undefined {
  return cache.get(id);
}

/** Triangle indices of [start, end] ranges, checked to be ordered, disjoint and inside the mesh. */
export function expandLayerRanges(ranges: number[][], triangles: number): number[] {
  const hidden: number[] = [];
  let previous = -1;
  for (const [start, end] of ranges) {
    if (!Number.isInteger(start) || !Number.isInteger(end) || start <= previous || end < start || end >= triangles)
      throw new Error('Invalid layer ranges');
    for (let n = start; n <= end; n++) hidden.push(n);
    previous = end;
  }
  return hidden;
}
