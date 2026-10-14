"""Minimal, read-mostly glTF 2.0 support for the native life-clip tools (pure Python, no deps).

* GLB or .gltf JSON; buffers embedded (GLB BIN chunk), as data: URIs, or as relative .bin files.
* No meshopt decoder here: EXT_meshopt_compression files are first decoded by the existing
  tools/uncompress_unreal_glb.mjs (the vendored official decoder, web/house/vendor/
  meshopt_decoder.module.js); reading a compressed view raises Compressed.
* Node-graph forward kinematics with translation / rotation / uniform-scale TRS, LINEAR and STEP
  samplers (CUBICSPLINE is refused, never approximated).
* A GLB writer for float32 animation-only outputs.

Values are never guessed: anything unsupported raises.
"""
from __future__ import annotations

import base64
import bisect
import hashlib
import json
import math
import struct
from pathlib import Path

# ------------------------------------------------------------------ quaternion math (x, y, z, w)
IDENTITY = (0.0, 0.0, 0.0, 1.0)


def qmul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by, aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw, aw * bw - ax * bx - ay * by - az * bz)


def qinv(q):
    n = sum(c * c for c in q) or 1.0
    return (-q[0] / n, -q[1] / n, -q[2] / n, q[3] / n)


def qnorm(q):
    n = math.sqrt(sum(c * c for c in q)) or 1.0
    return tuple(c / n for c in q)


def qrot(q, v):
    x, y, z, w = q
    tx, ty, tz = 2 * (y * v[2] - z * v[1]), 2 * (z * v[0] - x * v[2]), 2 * (x * v[1] - y * v[0])
    return (v[0] + w * tx + (y * tz - z * ty), v[1] + w * ty + (z * tx - x * tz), v[2] + w * tz + (x * ty - y * tx))


def qangle_deg(a, b):
    dot = abs(sum(x * y for x, y in zip(qnorm(a), qnorm(b))))
    return math.degrees(2 * math.acos(min(1.0, dot)))


def qaxis(axis, angle):
    n = math.sqrt(sum(c * c for c in axis)) or 1.0
    s = math.sin(angle / 2)
    return (axis[0] / n * s, axis[1] / n * s, axis[2] / n * s, math.cos(angle / 2))


def slerp(a, b, t):
    dot = sum(x * y for x, y in zip(a, b))
    if dot < 0:
        b, dot = tuple(-c for c in b), -dot
    if dot > .9995:
        return qnorm(tuple(x + (y - x) * t for x, y in zip(a, b)))
    theta = math.acos(dot)
    s = math.sin(theta)
    wa, wb = math.sin((1 - t) * theta) / s, math.sin(t * theta) / s
    return tuple(wa * x + wb * y for x, y in zip(a, b))


def vsub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def vadd(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def vscale(a, k):
    return (a[0] * k, a[1] * k, a[2] * k)


def vdot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def vcross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def vlen(a):
    return math.sqrt(vdot(a, a))


def vunit(a):
    n = vlen(a)
    if n < 1e-12:
        raise ValueError('zero-length direction')
    return (a[0] / n, a[1] / n, a[2] / n)


def arc(u, v):
    """Shortest rotation taking unit direction u onto unit direction v."""
    u, v = vunit(u), vunit(v)
    d = vdot(u, v)
    if d < -1 + 1e-9:
        axis = vcross(u, (1.0, 0.0, 0.0))
        if vlen(axis) < 1e-6:
            axis = vcross(u, (0.0, 1.0, 0.0))
        return qaxis(axis, math.pi)
    c = vcross(u, v)
    return qnorm((c[0], c[1], c[2], 1 + d))


def frame_quat(x_axis, y_axis):
    """Rotation whose columns are an orthonormal frame built from x (exact) and y (orthogonalised)."""
    x = vunit(x_axis)
    z = vunit(vcross(x, y_axis))
    y = vcross(z, x)
    m00, m01, m02 = x[0], y[0], z[0]
    m10, m11, m12 = x[1], y[1], z[1]
    m20, m21, m22 = x[2], y[2], z[2]
    tr = m00 + m11 + m22
    if tr > 0:
        s = math.sqrt(tr + 1.0) * 2
        q = ((m21 - m12) / s, (m02 - m20) / s, (m10 - m01) / s, s / 4)
    elif m00 > m11 and m00 > m22:
        s = math.sqrt(1.0 + m00 - m11 - m22) * 2
        q = (s / 4, (m01 + m10) / s, (m02 + m20) / s, (m21 - m12) / s)
    elif m11 > m22:
        s = math.sqrt(1.0 + m11 - m00 - m22) * 2
        q = ((m01 + m10) / s, s / 4, (m12 + m21) / s, (m02 - m20) / s)
    else:
        s = math.sqrt(1.0 + m22 - m00 - m11) * 2
        q = ((m02 + m20) / s, (m12 + m21) / s, s / 4, (m10 - m01) / s)
    return qnorm(q)


# ------------------------------------------------------------------ file model
class Compressed(ValueError):
    """EXT_meshopt_compression data: decoded only by the vendored official decoder (Node), never here."""


def is_compressed(path) -> bool:
    return 'EXT_meshopt_compression' in (Gltf(path).doc.get('extensionsUsed') or [])


class Gltf:
    def __init__(self, path):
        self.path = Path(path)
        raw = self.path.read_bytes()
        self.sha256 = hashlib.sha256(raw).hexdigest()
        glb_bin = None
        if raw[:4] == b'glTF':
            if struct.unpack_from('<I', raw, 4)[0] != 2:
                raise ValueError(f'{path}: not glTF 2')
            doc, offset = None, 12
            while offset < len(raw):
                size, kind = struct.unpack_from('<II', raw, offset)
                chunk = raw[offset + 8:offset + 8 + size]
                if kind == 0x4E4F534A:
                    doc = json.loads(chunk)
                elif kind == 0x004E4942 and glb_bin is None:
                    glb_bin = bytes(chunk)
                offset += 8 + size
            if doc is None:
                raise ValueError(f'{path}: missing JSON chunk')
        else:
            doc = json.loads(raw)
        self.doc = doc
        self.buffers = []
        for i, b in enumerate(doc.get('buffers', [])):
            uri = b.get('uri')
            if uri is None:
                self.buffers.append(glb_bin if (i == 0 and glb_bin is not None) else b'')
            elif uri.startswith('data:'):
                self.buffers.append(base64.b64decode(uri.split(',', 1)[1]))
            else:
                self.buffers.append((self.path.parent / uri).read_bytes())
        self._views = {}
        self.nodes = doc.get('nodes', [])
        self.parent = {}
        for i, n in enumerate(self.nodes):
            for c in n.get('children', []):
                if c in self.parent:
                    raise ValueError('node with two parents')
                self.parent[c] = i
        self.by_name = {}
        for i, n in enumerate(self.nodes):
            if 'name' in n:
                self.by_name.setdefault(n['name'], i)

    def view_bytes(self, index):
        if index not in self._views:
            view = self.doc['bufferViews'][index]
            if view.get('extensions', {}).get('EXT_meshopt_compression'):
                raise Compressed(f'{self.path}: meshopt-compressed; decode it first with the vendored decoder: '
                                 'node tools/uncompress_unreal_glb.mjs IN.glb OUT.glb')
            else:
                start = view.get('byteOffset', 0)
                data = self.buffers[view.get('buffer', 0)]
                if len(data) < start + view['byteLength']:
                    raise ValueError('bufferView outside its buffer (missing data)')
                self._views[index] = data[start:start + view['byteLength']]
        return self._views[index]

    def accessor(self, index):
        a = self.doc['accessors'][index]
        if 'sparse' in a:
            raise ValueError('sparse accessor unsupported')
        width = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}[a['type']]
        fmt, size, norm = {5126: ('f', 4, 0), 5122: ('h', 2, 32767), 5120: ('b', 1, 127),
                           5123: ('H', 2, 65535), 5121: ('B', 1, 255), 5125: ('I', 4, 0)}[a['componentType']]
        if 'bufferView' not in a:
            return [tuple([0.0] * width)] * a['count']
        view = self.doc['bufferViews'][a['bufferView']]
        stride = view.get('byteStride', width * size)
        data = self.view_bytes(a['bufferView'])
        start = a.get('byteOffset', 0)
        out = []
        for i in range(a['count']):
            v = struct.unpack_from('<' + fmt * width, data, start + i * stride)
            if norm and a.get('normalized'):
                v = tuple(max(x / norm, -1.0) for x in v)
            out.append(tuple(float(x) for x in v))
        return out

    def rest(self, i):
        n = self.nodes[i]
        if n.get('matrix'):
            raise ValueError(f'node {n.get("name")} uses a matrix; TRS required')
        return (tuple(n.get('translation', (0.0, 0.0, 0.0))), tuple(n.get('rotation', IDENTITY)),
                tuple(n.get('scale', (1.0, 1.0, 1.0))))

    def animation(self, name=None):
        anims = self.doc.get('animations', [])
        picked = [a for a in anims if name is None or a.get('name') == name]
        if len(picked) != 1:
            raise ValueError(f'{self.path}: expected exactly one animation {name!r}, found '
                             f'{[a.get("name") for a in anims]}')
        return Clip(self, picked[0])


class Clip:
    def __init__(self, gltf: Gltf, anim: dict):
        self.name = anim.get('name')
        self.tracks = {}
        for c in anim['channels']:
            s = anim['samplers'][c['sampler']]
            interp = s.get('interpolation', 'LINEAR')
            if interp not in ('LINEAR', 'STEP'):
                raise ValueError(f'interpolation {interp} unsupported')
            times = [t[0] for t in gltf.accessor(s['input'])]
            values = gltf.accessor(s['output'])
            if c['target'].get('path') == 'weights' or 'node' not in c['target']:
                continue
            self.tracks[(c['target']['node'], c['target']['path'])] = (times, values, interp)
        if not self.tracks:
            raise ValueError('animation has no node tracks')
        self.start = min(t[0][0] for t in self.tracks.values())
        self.end = max(t[0][-1] for t in self.tracks.values())

    def key_times(self):
        return sorted({t for tr in self.tracks.values() for t in tr[0]})

    def sample(self, node, path, t, default):
        tr = self.tracks.get((node, path))
        if not tr:
            return tuple(default)
        times, values, interp = tr
        if t <= times[0]:
            return tuple(values[0])
        if t >= times[-1]:
            return tuple(values[-1])
        i = bisect.bisect_right(times, t) - 1
        if interp == 'STEP' or times[i + 1] == times[i]:
            return tuple(values[i])
        w = (t - times[i]) / (times[i + 1] - times[i])
        if path == 'rotation':
            return slerp(values[i], values[i + 1], w)
        return tuple(a + (b - a) * w for a, b in zip(values[i], values[i + 1]))


# Exported clips carry float noise on scale keys (char_v5 idle: 3e-6 on the thighs). Up to this
# relative anisotropy a scale is taken as its mean; beyond it FK refuses (no shear is modelled).
SCALE_ANISOTROPY_TOLERANCE = 1e-4


class RestPose:
    @staticmethod
    def sample(node, path, t, default):
        return tuple(default)


def world_pose(gltf: Gltf, sampler, t, nodes=None):
    """World (translation, rotation, uniform scale) of every node (or the given ones and their ancestors)."""
    cache = {}

    def visit(i):
        if i in cache:
            return cache[i]
        rt, rq, rs = gltf.rest(i)
        lt = sampler.sample(i, 'translation', t, rt)
        lq = qnorm(sampler.sample(i, 'rotation', t, rq))
        ls = sampler.sample(i, 'scale', t, rs)
        if max(ls) - min(ls) > SCALE_ANISOTROPY_TOLERANCE * max(1.0, abs(max(ls))):
            raise ValueError(f'non-uniform scale on node {gltf.nodes[i].get("name")}')
        ls = (sum(ls) / 3,)
        if i in gltf.parent:
            pt, pq, ps = visit(gltf.parent[i])
            r = qrot(pq, lt)
            cache[i] = ((pt[0] + ps * r[0], pt[1] + ps * r[1], pt[2] + ps * r[2]), qnorm(qmul(pq, lq)), ps * ls[0])
        else:
            cache[i] = (tuple(lt), lq, ls[0])
        return cache[i]

    for i in (range(len(gltf.nodes)) if nodes is None else nodes):
        visit(i)
    return cache


# ------------------------------------------------------------------ writer
def write_glb(path, doc: dict, binary: bytes):
    js = json.dumps(doc, separators=(',', ':')).encode()
    js += b' ' * ((-len(js)) % 4)
    binary = binary + b'\x00' * ((-len(binary)) % 4)
    total = 12 + 8 + len(js) + 8 + len(binary)
    out = struct.pack('<4sII', b'glTF', 2, total) + struct.pack('<II', len(js), 0x4E4F534A) + js \
        + struct.pack('<II', len(binary), 0x004E4942) + binary
    Path(path).write_bytes(out)
    return hashlib.sha256(out).hexdigest()


class BinWriter:
    """Accumulates float32 accessors for write_glb."""

    def __init__(self):
        self.data = bytearray()
        self.views = []
        self.accessors = []

    def add(self, rows, kind, minmax=False):
        width = {'SCALAR': 1, 'VEC3': 3, 'VEC4': 4}[kind]
        offset = len(self.data)
        for r in rows:
            r = (r,) if width == 1 and not isinstance(r, (tuple, list)) else r
            self.data += struct.pack('<' + 'f' * width, *r)
        self.views.append({'buffer': 0, 'byteOffset': offset, 'byteLength': len(self.data) - offset})
        acc = {'bufferView': len(self.views) - 1, 'componentType': 5126, 'count': len(rows), 'type': kind}
        if minmax:
            flat = [((r,) if width == 1 and not isinstance(r, (tuple, list)) else tuple(r)) for r in rows]
            f32 = [tuple(struct.unpack('<' + 'f' * width, struct.pack('<' + 'f' * width, *r))) for r in flat]
            acc['min'] = [min(r[k] for r in f32) for k in range(width)]
            acc['max'] = [max(r[k] for r in f32) for k in range(width)]
        self.accessors.append(acc)
        return len(self.accessors) - 1
