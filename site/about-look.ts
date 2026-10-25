/**
 * Reads images saved by the fitting room and prints `looks` entries for about-data.ts.
 * Usage: `bun about-look.ts images/*.png`
 */
import { readFileSync } from 'node:fs';
import { basename } from 'node:path';
import { readPngText } from './look-code';
import { lookFromPng } from './about-model';

for (const path of process.argv.slice(2)) {
  const look = lookFromPng(readPngText(new Uint8Array(readFileSync(path))));
  console.log(look
    ? `    { look: '${look}', credit: '', note: '${basename(path)}' },`
    : `    // ${basename(path)}: no ReCriaLab look`);
}
