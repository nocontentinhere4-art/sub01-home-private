"""Independent GLB interchange check; does not certify contact or visual quality."""
import argparse, hashlib, json, math, struct
from pathlib import Path


def read(path):
    raw = path.read_bytes()
    if raw[:4] != b'glTF' or struct.unpack_from('<II', raw, 4) != (2, len(raw)):
        raise ValueError('Invalid GLB envelope')
    doc = binary = None
    cursor = 12
    while cursor < len(raw):
        length, kind = struct.unpack_from('<II', raw, cursor)
        value = raw[cursor + 8:cursor + 8 + length]
        if kind == 0x4E4F534A:
            doc = json.loads(value)
        elif kind == 0x004E4942:
            binary = value
        cursor += 8 + length
    assert doc is not None and binary is not None and cursor == len(raw)
    return doc, binary


def verify(owner, candidate, in_place=False, rigid_bones=False):
    original, before = read(owner)
    baked, after = read(candidate)
    for key in ('nodes', 'skins', 'meshes', 'images', 'textures', 'materials', 'scenes'):
        assert baked.get(key) == original.get(key), 'Changed owner graph: ' + key
    assert after[:len(before)] == before, 'Changed original compressed geometry/skin/pixels'
    assert baked['bufferViews'][:len(original['bufferViews'])] == original['bufferViews']
    assert baked['accessors'][:len(original['accessors'])] == original['accessors']
    assert len(baked['animations']) == 1
    animation = baked['animations'][0]
    frame_counts = set()
    times = None
    root = None
    names = set()
    max_norm_error = 0
    for channel in animation['channels']:
        name = baked['nodes'][channel['target']['node']]['name']
        names.add(name)
        assert 'Hand' not in name, 'This body source must not override wrist/finger contact tracks'
        sampler = animation['samplers'][channel['sampler']]
        assert sampler['interpolation'] == 'LINEAR'
        def values(index):
            a = baked['accessors'][index]
            v = baked['bufferViews'][a['bufferView']]
            assert a['componentType'] == 5126 and v['buffer'] == 0
            n = {'SCALAR': 1, 'VEC3': 3, 'VEC4': 4}[a['type']]
            stride = v.get('byteStride', n * 4)
            start = v.get('byteOffset', 0) + a.get('byteOffset', 0)
            rows = [struct.unpack_from('<' + 'f' * n, after, start + i * stride) for i in range(a['count'])]
            assert all(math.isfinite(x) for row in rows for x in row)
            return rows
        time = [v[0] for v in values(sampler['input'])]
        value = values(sampler['output'])
        assert len(time) == len(value) and all(b > a for a, b in zip(time, time[1:]))
        frame_counts.add(len(value))
        if times is None:
            times = time
        assert time == times
        if channel['target']['path'] == 'rotation':
            max_norm_error = max(max_norm_error, max(abs(sum(x*x for x in row)-1) for row in value))
        elif name.endswith(':Hips'):
            root = value
        elif rigid_bones and channel['target']['path'] == 'translation':
            rest = original['nodes'][channel['target']['node']].get('translation', [0, 0, 0])
            assert all(max(abs(x-y) for x, y in zip(row, rest)) < 1e-4 for row in value), 'Non-Hips bone translation changes actual owner bone length: ' + name
    assert len(names) == 20 and len(frame_counts) == 1 and max_norm_error < 1e-5 and root
    travel = math.dist(root[0], root[-1]) * .01
    horizontal_drift = max(math.hypot(p[0]-root[0][0], p[2]-root[0][2]) for p in root) * .01
    if in_place:
        assert horizontal_drift < 1e-6, 'In-place candidate still moves skin outside physical capsule'
    else:
        assert travel > .1, 'Expected actual walking trajectory, not a static bind pose'
    return {'schema': 'sub01.cozy-bake-independent.v1', 'frames': frame_counts.pop(),
            'duration_seconds': times[-1], 'body_bones': len(names),
            'root_start_to_end_m': travel, 'horizontal_root_drift_m': horizontal_drift,
            'in_place': in_place, 'max_quaternion_squared_norm_error': max_norm_error,
            'non_hip_bone_local_translations_verified': rigid_bones,
            'original_geometry_skin_images_graphs_unchanged': True,
            'hand_tracks_overridden': False, 'native_visual_accepted': False,
            'candidate_sha256': hashlib.sha256(candidate.read_bytes()).hexdigest()}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('owner', type=Path)
    p.add_argument('candidate', type=Path)
    p.add_argument('--output', type=Path)
    p.add_argument('--in-place', action='store_true')
    p.add_argument('--rigid-bones', action='store_true')
    a = p.parse_args()
    report = verify(a.owner, a.candidate, a.in_place, a.rigid_bones)
    rendered = json.dumps(report, indent=2) + '\n'
    if a.output:
        a.output.write_text(rendered)
    print(rendered, end='')
