// Body triangles hidden under each piece, per pose: piece id → mask. Written by tools/fit/install.py, which
// validates the geometry first; each mask is bound to the hash of the body and of the garment GLB (body-poses.test.ts).
import type { BodyMask } from './body-occlusion';
import maskB001 from './assets/masks/pose-b/001.json';
import maskB002 from './assets/masks/pose-b/002.json';
import maskB003 from './assets/masks/pose-b/003.json';
import maskB004 from './assets/masks/pose-b/004.json';
import maskB005 from './assets/masks/pose-b/005.json';
import maskB007 from './assets/masks/pose-b/007.json';
import maskB008 from './assets/masks/pose-b/008.json';
import maskB009 from './assets/masks/pose-b/009.json';
import maskB010 from './assets/masks/pose-b/010.json';
import maskB015 from './assets/masks/pose-b/015.json';
import maskB016 from './assets/masks/pose-b/016.json';
import maskB017 from './assets/masks/pose-b/017.json';
import maskB018 from './assets/masks/pose-b/018.json';
import maskB019 from './assets/masks/pose-b/019.json';
import maskB020 from './assets/masks/pose-b/020.json';
import maskB021 from './assets/masks/pose-b/021.json';
import maskB022 from './assets/masks/pose-b/022.json';
import maskB023 from './assets/masks/pose-b/023.json';
import maskB024 from './assets/masks/pose-b/024.json';
import maskB025 from './assets/masks/pose-b/025.json';
import maskB026 from './assets/masks/pose-b/026.json';
import maskB027 from './assets/masks/pose-b/027.json';
import maskB028 from './assets/masks/pose-b/028.json';
import maskB029 from './assets/masks/pose-b/029.json';
import maskB030 from './assets/masks/pose-b/030.json';
import maskB031 from './assets/masks/pose-b/031.json';
import maskB032 from './assets/masks/pose-b/032.json';
import maskB033 from './assets/masks/pose-b/033.json';
import maskB034 from './assets/masks/pose-b/034.json';
import maskB035 from './assets/masks/pose-b/035.json';
import maskB036 from './assets/masks/pose-b/036.json';
import maskB037 from './assets/masks/pose-b/037.json';
import maskB038 from './assets/masks/pose-b/038.json';
import maskC006 from './assets/masks/pose-c/006.json';
import maskC011 from './assets/masks/pose-c/011.json';
import maskC012 from './assets/masks/pose-c/012.json';
import maskC013 from './assets/masks/pose-c/013.json';
import maskC014 from './assets/masks/pose-c/014.json';
import maskC016 from './assets/masks/pose-c/016.json';
import maskC017 from './assets/masks/pose-c/017.json';
import maskC018 from './assets/masks/pose-c/018.json';
import maskC019 from './assets/masks/pose-c/019.json';
import maskC020 from './assets/masks/pose-c/020.json';
import maskC021 from './assets/masks/pose-c/021.json';
import maskC022 from './assets/masks/pose-c/022.json';
import maskC023 from './assets/masks/pose-c/023.json';
import maskC024 from './assets/masks/pose-c/024.json';
import maskC025 from './assets/masks/pose-c/025.json';
import maskC026 from './assets/masks/pose-c/026.json';
import maskC027 from './assets/masks/pose-c/027.json';
import maskC028 from './assets/masks/pose-c/028.json';
import maskC029 from './assets/masks/pose-c/029.json';
import maskC030 from './assets/masks/pose-c/030.json';
import maskC031 from './assets/masks/pose-c/031.json';
import maskC032 from './assets/masks/pose-c/032.json';
import maskC033 from './assets/masks/pose-c/033.json';
import maskC034 from './assets/masks/pose-c/034.json';
import maskC035 from './assets/masks/pose-c/035.json';
import maskC036 from './assets/masks/pose-c/036.json';
import maskC037 from './assets/masks/pose-c/037.json';
import maskC038 from './assets/masks/pose-c/038.json';

/** Pose B, the default. */
export const BODY_MASKS: Record<string, BodyMask> = {
  '001': maskB001,
  '002': maskB002,
  '003': maskB003,
  '004': maskB004,
  '005': maskB005,
  '007': maskB007,
  '008': maskB008,
  '009': maskB009,
  '010': maskB010,
  '015': maskB015,
  '016': maskB016,
  '017': maskB017,
  '018': maskB018,
  '019': maskB019,
  '020': maskB020,
  '021': maskB021,
  '022': maskB022,
  '023': maskB023,
  '024': maskB024,
  '025': maskB025,
  '026': maskB026,
  '027': maskB027,
  '028': maskB028,
  '029': maskB029,
  '030': maskB030,
  '031': maskB031,
  '032': maskB032,
  '033': maskB033,
  '034': maskB034,
  '035': maskB035,
  '036': maskB036,
  '037': maskB037,
  '038': maskB038,
};

/** Pose C (legs apart, for wide pants): recomputed bottom masks and vertex-verified migrations of the top masks. */
export const BODY_C_MASKS: Record<string, BodyMask> = {
  '006': maskC006,
  '011': maskC011,
  '012': maskC012,
  '013': maskC013,
  '014': maskC014,
  '016': maskC016,
  '017': maskC017,
  '018': maskC018,
  '019': maskC019,
  '020': maskC020,
  '021': maskC021,
  '022': maskC022,
  '023': maskC023,
  '024': maskC024,
  '025': maskC025,
  '026': maskC026,
  '027': maskC027,
  '028': maskC028,
  '029': maskC029,
  '030': maskC030,
  '031': maskC031,
  '032': maskC032,
  '033': maskC033,
  '034': maskC034,
  '035': maskC035,
  '036': maskC036,
  '037': maskC037,
  '038': maskC038,
};
