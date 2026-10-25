"""Body mask on disk: hidden triangles stored as [start, end] ranges, which keep the masks small in the site's JS."""
import json, numpy as np

SCHEMA = 'recria-body-face-mask-v2'


def ranges(idx):
    idx = np.unique(np.asarray(idx, int))
    if not len(idx): return []
    breaks = np.nonzero(np.diff(idx) != 1)[0]
    return [[int(a), int(b)] for a, b in zip(np.r_[idx[0], idx[breaks + 1]], np.r_[idx[breaks], idx[-1]])]


def hidden_indices(mask):
    """Hidden triangle indices of the first mesh of an already loaded mask."""
    return np.concatenate([np.arange(a, b + 1) for a, b in mask['meshes'][0]['hidden_ranges']] or [np.zeros(0, int)])


def load(path):
    return hidden_indices(json.load(open(path)))


def save(path, mask, hidden):
    mask['schema'] = SCHEMA
    mesh = mask['meshes'][0]
    mesh['hidden_ranges'] = '@@'
    text = json.dumps(mask, indent=2).replace('"@@"', json.dumps(ranges(hidden), separators=(',', ':')))
    open(path, 'w').write(text + '\n')
