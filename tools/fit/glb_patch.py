"""Reads and writes GLB files (JSON + BIN chunks) and vec3 attributes; used by garment.py."""
import json, struct, numpy as np


def read(path):
    data = open(path, 'rb').read()
    n = struct.unpack_from('<I', data, 12)[0]
    js = json.loads(data[20:20 + n])
    off = 20 + n
    bl = struct.unpack_from('<I', data, off)[0]
    bin_ = bytearray(data[off + 8: off + 8 + bl])
    return js, bin_


def write(path, js, bin_):
    j = json.dumps(js, separators=(',', ':')).encode()
    j += b' ' * (-len(j) % 4)
    b = bytes(bin_) + b'\0' * (-len(bin_) % 4)
    total = 12 + 8 + len(j) + 8 + len(b)
    with open(path, 'wb') as f:
        f.write(struct.pack('<III', 0x46546C67, 2, total))
        f.write(struct.pack('<II', len(j), 0x4E4F534A)); f.write(j)
        f.write(struct.pack('<II', len(b), 0x004E4942)); f.write(b)


def accessor_view(js, bin_, ai):
    a = js['accessors'][ai]; bv = js['bufferViews'][a['bufferView']]
    start = bv.get('byteOffset', 0) + a.get('byteOffset', 0)
    stride = bv.get('byteStride', 12)
    return a, start, stride


def set_vec3(js, bin_, ai, arr):
    a, start, stride = accessor_view(js, bin_, ai)
    assert a['count'] == len(arr) and a['componentType'] == 5126
    for i, v in enumerate(arr.astype('<f4')):
        bin_[start + i * stride: start + i * stride + 12] = v.tobytes()
    return a


def get_vec3(js, bin_, ai):
    a, start, stride = accessor_view(js, bin_, ai)
    return np.array([struct.unpack_from('<3f', bin_, start + i * stride) for i in range(a['count'])])
