// Which version of the garments a look is drawn with: the fit engine's (low-poly shells on the low-poly mannequin)
// or the published one (dense garments on the dense body, with masks and layer tables). The two do not mix: an
// engine shell is a skin of the low-poly body and a published garment is fitted to the dense one. So a look is drawn
// the engine way only when every garment in it has an engine version that is not on hold.
import { ENGINE_PARTS } from './engine-garments';
import { ENGINE_HOLD } from './engine-hold';

/** Whether the fitting room opens with the engine's garments. Off until the look of the whole is approved. */
export const ENGINE_DEFAULT = false;
/** `?engine` turns the engine's garments on and `?classico` shows the whole fitting room as published, whatever the default. */
export function engineOn(search: string, byDefault: boolean = ENGINE_DEFAULT): boolean {
  const params = new URLSearchParams(search);
  return params.has('engine') || (byDefault && !params.has('classico'));
}
export const ENGINE_ON = typeof location !== 'undefined' && engineOn(location.search);

/** True when the look (the ids worn, possibly none) is drawn with the engine's garments and body. */
export function engineLook(ids: readonly string[], on: boolean = ENGINE_ON, hold: Record<string, string> = ENGINE_HOLD): boolean {
  return on && ids.every(id => id in ENGINE_PARTS && !(id in hold));
}
