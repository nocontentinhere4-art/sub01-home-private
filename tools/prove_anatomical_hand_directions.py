"""Independent serialized 4x4 FK measurement of captured phalange directions.

Uses only Python's standard library, not the retargeter's quaternion/frame code.
Does not prove skin deformation or object contacts.
"""
import bisect
import hashlib
import json
import math
import struct
import sys
from pathlib import Path


def load(path):
    raw = Path(path).read_bytes()
    assert raw[:4] == b'glTF' and struct.unpack_from('<II', raw, 4) == (2, len(raw))
    offset = 12
    doc = binary = None
    while offset < len(raw):
        size, kind = struct.unpack_from('<II', raw, offset)
        chunk = raw[offset + 8:offset + 8 + size]
        if kind == 0x4e4f534a:
            doc = json.loads(chunk)
        elif kind == 0x004e4942:
            binary = chunk
        offset += 8 + size
    assert offset == len(raw) and doc and binary
    return doc, binary, hashlib.sha256(raw).hexdigest()


def accessor(doc, binary, index):
    a = doc['accessors'][index]
    v = doc['bufferViews'][a['bufferView']]
    assert a['componentType'] == 5126 and not a.get('sparse') and not v.get('extensions')
    width = {'SCALAR': 1, 'VEC3': 3, 'VEC4': 4}[a['type']]
    offset = v.get('byteOffset', 0) + a.get('byteOffset', 0)
    return [struct.unpack_from('<' + 'f' * width, binary,
                               offset + i * v.get('byteStride', 4 * width)) for i in range(a['count'])]


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def subtract(a, b):
    return [x - y for x, y in zip(a, b)]


def unit(v):
    norm = math.sqrt(dot(v, v))
    assert norm > 1e-10
    return [x / norm for x in v]


def slerp(a, b, alpha):
    a, b = unit(a), unit(b)
    d = dot(a, b)
    if d < 0:
        b, d = [-x for x in b], -d
    if d > .9995:
        return unit([x + alpha * (y - x) for x, y in zip(a, b)])
    angle = math.acos(min(1, d))
    return [(x * math.sin((1 - alpha) * angle) + y * math.sin(alpha * angle)) / math.sin(angle)
            for x, y in zip(a, b)]


def matrix(rotation, translation, scale):
    x, y, z, w = unit(rotation)
    r = [[1 - 2 * (y*y + z*z), 2 * (x*y - z*w), 2 * (x*z + y*w)],
         [2 * (x*y + z*w), 1 - 2 * (x*x + z*z), 2 * (y*z - x*w)],
         [2 * (x*z - y*w), 2 * (y*z + x*w), 1 - 2 * (x*x + y*y)]]
    return [[r[i][j] * scale[j] for j in range(3)] + [translation[i]] for i in range(3)] + [[0, 0, 0, 1]]


def multiply(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


class Clip:
    def __init__(self, doc, binary, animation_index):
        self.doc = doc
        self.names = {n.get('name', '').replace('mixamorig:', ''): i for i, n in enumerate(doc['nodes'])}
        self.parents = {c: i for i, n in enumerate(doc['nodes']) for c in n.get('children', [])}
        self.tracks = {}
        animation = doc['animations'][animation_index]
        for channel in animation['channels']:
            sampler = animation['samplers'][channel['sampler']]
            interpolation = sampler.get('interpolation', 'LINEAR')
            assert interpolation in ['LINEAR', 'STEP']
            t = [v[0] for v in accessor(doc, binary, sampler['input'])]
            assert all(t[i] > t[i-1] for i in range(1, len(t)))
            self.tracks[channel['target']['node'], channel['target']['path']] = (
                t, accessor(doc, binary, sampler['output']), interpolation)

    def positions(self, time):
        locals_ = [{k: n.get(k, default) for k, default in
                    [('rotation', [0, 0, 0, 1]), ('translation', [0, 0, 0]), ('scale', [1, 1, 1])]}
                   for n in self.doc['nodes']]
        for (index, kind), (times, values, interpolation) in self.tracks.items():
            hi = bisect.bisect_left(times, time)
            if hi == 0:
                value = values[0]
            elif hi >= len(times):
                value = values[-1]
            elif times[hi] == time:
                value = values[hi]
            else:
                lo = hi - 1
                alpha = (time - times[lo]) / (times[hi] - times[lo])
                value = values[lo] if interpolation == 'STEP' else slerp(values[lo], values[hi], alpha) if kind == 'rotation' else [
                    x + alpha * (y-x) for x, y in zip(values[lo], values[hi])]
            locals_[index][kind] = value
        world = {}

        def get(i):
            if i not in world:
                n = locals_[i]
                m = matrix(n['rotation'], n['translation'], n['scale'])
                world[i] = multiply(get(self.parents[i]), m) if i in self.parents else m
            return world[i]
        return {name: [get(i)[j][3] for j in range(3)] for name, i in self.names.items()}


def palm_axes(positions, side):
    index, pinky, wrist = [positions[side + n] for n in ['HandIndex1', 'HandPinky1', 'Hand']]
    x = unit(subtract(index, pinky))
    forward = [(a + b) / 2 - c for a, b, c in zip(index, pinky, wrist)]
    y = unit([v - dot(forward, x) * a for v, a in zip(forward, x)])
    z = [x[1]*y[2]-x[2]*y[1], x[2]*y[0]-x[0]*y[2], x[0]*y[1]-x[1]*y[0]]
    return x, y, z


def prove(source, original, candidate, output, mode=None):
    assert mode in (None, '--preserve-target-body')
    sd, sb, source_hash = load(source)
    od, ob, original_hash = load(original)
    cd, cb, candidate_hash = load(candidate)
    assert cb[:len(ob)] == ob
    for field in ['nodes', 'skins', 'meshes', 'materials', 'images', 'textures']:
        assert cd.get(field) == od.get(field), field
    assert cd['animations'][:-1] == od.get('animations', [])
    a, b = Clip(sd, sb, 0), Clip(cd, cb, -1)
    if mode:
        body = od['animations'][0]
        combined = cd['animations'][-1]
        assert combined['samplers'][:len(body['samplers'])] == body['samplers']
        assert combined['channels'][:len(body['channels'])] == body['channels']
        assert len(combined['channels']) == len(body['channels']) + 30
    else:
        assert len(b.tracks) == 32 and all(path == 'rotation' for _, path in b.tracks)
    times = sorted({t for ts, _, _ in b.tracks.values() for t in ts})
    # Every segment uses the same two poses at a given captured time.
    poses = {time: (a.positions(time), b.positions(time)) for time in times}
    rows = []
    for side in ['Left', 'Right']:
        for finger in ['Thumb', 'Index', 'Middle', 'Ring', 'Pinky']:
            for segment in range(1, 4):
                name = side + 'Hand' + finger + str(segment)
                child = side + 'Hand' + finger + str(segment + 1)
                errors = []
                for time in times:
                    sp, tp = poses[time]
                    sdir, tdir = unit(subtract(sp[child], sp[name])), unit(subtract(tp[child], tp[name]))
                    sv = [dot(axis, sdir) for axis in palm_axes(sp, side)]
                    tv = [dot(axis, tdir) for axis in palm_axes(tp, side)]
                    errors.append(math.acos(max(-1, min(1, dot(unit(sv), unit(tv))))))
                assert max(errors) < 2e-6, name
                rows.append({'name': name, 'max_serialized_direction_error_radians': max(errors)})
    report = {'schema': 'sub01.independent-serialized-anatomical-direction.v1',
              'source_sha256': source_hash, 'original_sha256': original_hash, 'candidate_sha256': candidate_hash,
              'frames': len(times), 'measured_segments': rows, 'both_sides': True,
              'original_binary_graph_skin_weights_materials_exact': True,
              'original_body_channels_and_samplers_preserved': bool(mode),
              'oracle': 'Independent standard-library 4x4 matrix FK; actual posed segment directions compared in actual posed knuckle-defined palm frames',
              'max_error_degrees': math.degrees(max(r['max_serialized_direction_error_radians'] for r in rows)),
              'native_accepted': False, 'skin_deformation_or_contact_accepted': False}
    Path(output).write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'passed': True, 'segments': len(rows), 'frames': len(times),
                      'max_serialized_direction_error_degrees': report['max_error_degrees']}))


if __name__ == '__main__':
    prove(*sys.argv[1:])
