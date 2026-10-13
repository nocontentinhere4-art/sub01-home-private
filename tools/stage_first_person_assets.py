"""Inspect and stage existing real rig/clip sources without running any renderer.

Private server bundle only; preserves source bytes. Never synthesizes finger
tracks, claims procedural desk clips are captures, or publishes raw Mixamo FBX.
Usage: python3 tools/stage_first_person_assets.py --output out/first-person-assets
"""
import argparse
import hashlib
import json
import math
import re
import shutil
import struct
import tarfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FINGER = re.compile(r'finger|thumb|hand(?:index|middle|ring|pinky)', re.I)
FBX_TICKS = 46186158000


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def glb(path):
    data = path.read_bytes()
    if data[:4] != b'glTF':
        raise ValueError('Not a GLB')
    length = struct.unpack_from('<I', data, 12)[0]
    document = json.loads(data[20:20+length])
    binary = data[28+length:]
    return document, binary


def accessor(document, binary, index):
    a = document['accessors'][index]
    if 'sparse' in a:
        raise ValueError('Sparse animation accessor requires an explicit decoder')
    view = document['bufferViews'][a['bufferView']]
    if view.get('buffer', 0) != 0 or 'EXT_meshopt_compression' in view.get('extensions', {}):
        raise ValueError('Compressed accessor requires meshopt decoder; raw byte interpretation is forbidden')
    components = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}[a['type']]
    kind, size = {5126: ('f', 4), 5125: ('I', 4), 5123: ('H', 2), 5121: ('B', 1)}[a['componentType']]
    stride = view.get('byteStride', components * size)
    start = view.get('byteOffset', 0) + a.get('byteOffset', 0)
    return [struct.unpack_from('<' + kind * components, binary, start + index * stride)
            for index in range(a['count'])]


def inspect_glb(path):
    d, binary = glb(path)
    nodes = d.get('nodes', [])
    parents = {child: index for index, node in enumerate(nodes) for child in node.get('children', [])}
    joints = sorted(set(index for skin in d.get('skins', []) for index in skin['joints']))
    skeleton = [{'name': nodes[index].get('name', str(index)),
                 'parent': nodes[parents[index]].get('name') if index in parents else None,
                 'translation': nodes[index].get('translation', [0, 0, 0]),
                 'rotation': nodes[index].get('rotation', [0, 0, 0, 1]),
                 'scale': nodes[index].get('scale', [1, 1, 1]),
                 'matrix': nodes[index].get('matrix')}
                for index in joints]
    clips = []
    all_targets = set()
    for animation in d.get('animations', []):
        tracks = []
        minimum, maximum = math.inf, -math.inf
        for channel in animation['channels']:
            sampler = animation['samplers'][channel['sampler']]
            target = channel['target']
            name = nodes[target['node']].get('name', str(target['node']))
            compressed = False
            try:
                times = accessor(d, binary, sampler['input'])
                values = accessor(d, binary, sampler['output'])
                start, end = times[0][0], times[-1][0]
                first = values[0]
                variation = max(max(abs(v[index] - first[index]) for index in range(len(first))) for v in values)
                keys = len(times)
            except ValueError as error:
                if 'meshopt decoder' not in str(error):
                    raise
                compressed = True
                input_meta = d['accessors'][sampler['input']]
                start = input_meta.get('min', [None])[0]
                end = input_meta.get('max', [None])[0]
                variation = None
                keys = input_meta['count']
            if start is not None and end is not None:
                minimum, maximum = min(minimum, start), max(maximum, end)
            is_finger = bool(FINGER.search(name))
            tracks.append({'node': name, 'path': target['path'], 'keys': keys,
                           'start_s': start, 'end_s': end,
                           'interpolation': sampler.get('interpolation', 'LINEAR'),
                           'finger': is_finger, 'max_component_delta': variation,
                           'animated': variation > 1e-5 if variation is not None else None,
                           'compressed_values_not_decoded': compressed})
            all_targets.add(name)
        clips.append({'name': animation.get('name', '(unnamed)'),
                      'duration_s': maximum - minimum if math.isfinite(minimum) and math.isfinite(maximum) else None, 'tracks': tracks,
                      'finger_tracks': sum(t['finger'] for t in tracks),
                      'moving_finger_tracks': sum(t['finger'] and t['animated'] is True for t in tracks)})
    skin_meshes = [node.get('name') for node in nodes if 'skin' in node and 'mesh' in node]
    return {'format': 'GLB', 'generator': d.get('asset', {}).get('generator'),
            'mesh_count': len(d.get('meshes', [])), 'skin_count': len(d.get('skins', [])),
            'skin_meshes': skin_meshes, 'joints': skeleton,
            'joint_names': [j['name'] for j in skeleton],
            'finger_joints': sum(bool(FINGER.search(j['name'])) for j in skeleton),
            'animation_target_names': sorted(all_targets), 'clips': clips,
            'root_nodes': [nodes[index] for index in d['scenes'][d.get('scene', 0)]['nodes']]}


def inspect_fbx(path):
    """Read binary FBX metadata/animation curves; skip all large geometry arrays."""
    data = path.read_bytes()
    if not data.startswith(b'Kaydara FBX Binary'):
        return {'format': 'FBX', 'unsupported': 'ASCII FBX needs server importer inspection'}
    version = struct.unpack_from('<I', data, 23)[0]
    wide = version >= 7500
    header_size = 25 if wide else 13
    header_format = '<QQQB' if wide else '<IIIB'

    def record(offset):
        end, count, properties_length, name_length = struct.unpack_from(header_format, data, offset)
        if not end:
            return None, offset + header_size
        start = offset + header_size
        name = data[start:start+name_length].decode('utf8', 'replace')
        position = start + name_length
        properties = []
        for _ in range(count):
            kind = chr(data[position]); position += 1
            scalar = {'Y': ('h', 2), 'C': ('?', 1), 'I': ('i', 4), 'F': ('f', 4), 'D': ('d', 8), 'L': ('q', 8)}
            if kind in scalar:
                fmt, size = scalar[kind]
                value = struct.unpack_from('<' + fmt, data, position)[0]
                position += size
            elif kind in ('S', 'R'):
                size = struct.unpack_from('<I', data, position)[0]; position += 4
                value = data[position:position+size]
                if kind == 'S':
                    value = value.decode('utf8', 'replace')
                position += size
            elif kind in 'fdlibc':
                count_array, encoding, compressed_size = struct.unpack_from('<III', data, position)
                position += 12
                raw = data[position:position+compressed_size]; position += compressed_size
                if name in ('KeyTime', 'KeyValueFloat'):
                    raw = zlib.decompress(raw) if encoding else raw
                    fmt = {'f': 'f', 'd': 'd', 'l': 'q', 'i': 'i', 'b': '?', 'c': 'b'}[kind]
                    value = list(struct.unpack('<' + fmt * count_array, raw))
                else:
                    value = {'array_count': count_array, 'type': kind}
            else:
                raise ValueError('Unsupported binary FBX property ' + kind)
            properties.append(value)
        children = []
        while position < end - header_size:
            child, position = record(position)
            if child:
                children.append(child)
        return {'name': name, 'properties': properties, 'children': children}, end

    records = []
    position = 27
    while position + header_size <= len(data):
        item, position = record(position)
        if not item:
            break
        records.append(item)
    objects = next(item['children'] for item in records if item['name'] == 'Objects')
    connections = next(item['children'] for item in records if item['name'] == 'Connections')
    by_id = {item['properties'][0]: item for item in objects if item['properties']}
    outgoing = {}
    for item in connections:
        prop = item['properties']
        if len(prop) >= 3:
            outgoing.setdefault(prop[1], []).append((prop[2], prop[3] if len(prop) > 3 else None))
    def clean(value):
        return str(value).split('\x00')[0].split('::')[-1]
    models = [item for item in objects if item['name'] == 'Model']
    bones = [item for item in models if item['properties'][-1] in ('LimbNode', 'Root')]
    curves = []
    for item in objects:
        if item['name'] != 'AnimationCurve':
            continue
        children = {child['name']: child['properties'][0] for child in item['children'] if child['properties']}
        times, values = children.get('KeyTime', []), children.get('KeyValueFloat', [])
        if not times or not values:
            continue
        for curve_node, axis in outgoing.get(item['properties'][0], []):
            for model_id, property_name in outgoing.get(curve_node, []):
                model = by_id.get(model_id)
                if not model or model['name'] != 'Model':
                    continue
                target = clean(model['properties'][1])
                curves.append({'node': target, 'path': property_name, 'axis': axis,
                               'keys': len(times), 'start_s': times[0] / FBX_TICKS,
                               'end_s': times[-1] / FBX_TICKS,
                               'finger': bool(FINGER.search(target)),
                               'range': max(values) - min(values),
                               'first_value': values[0], 'last_value': values[-1],
                               'animated': max(values) - min(values) > 1e-4})
    stacks = [clean(item['properties'][1]) for item in objects if item['name'] == 'AnimationStack']
    return {'format': 'FBX', 'version': version, 'mesh_count': sum(item['name'] == 'Geometry' and item['properties'][-1] == 'Mesh' for item in objects),
            'skin_count': sum(item['name'] == 'Deformer' and item['properties'][-1] == 'Skin' for item in objects),
            'joint_names': [clean(item['properties'][1]) for item in bones],
            'finger_joints': sum(bool(FINGER.search(clean(item['properties'][1]))) for item in bones),
            'clips': [{'name': ','.join(stacks), 'duration_s': max(t['end_s'] for t in curves) - min(t['start_s'] for t in curves),
                       'tracks': curves, 'finger_tracks': sum(t['finger'] for t in curves),
                       'moving_finger_tracks': sum(t['finger'] and t['animated'] for t in curves)}] if curves else [],
            'transforms': [item for item in models if item in bones]}


def stage(output, downloads):
    candidates = [
        ('owner_skin', ROOT/'web/room/char_mixamo.glb', 'Existing MakeHuman owner skin on derived Mixamo-standard skeleton; anatomy requires review, not a new Remy model.'),
        ('owner_makehuman_skin', ROOT/'web/room/char_v5.glb', 'Existing owner MakeHuman skin, native v5 rig.'),
        ('authored_typing', ROOT/'web/room/mh_mx/room_mx_typing.glb', 'Mixamo Typing capture converted without the v5 retarget; compatible bone names must be verified.'),
        ('authored_typing_v5', ROOT/'web/room/mh_v5/room_mx_typing.glb', 'Mixamo Typing capture retargeted and fitted onto MakeHuman v5.'),
        ('rejected_old_typing', ROOT/'web/room/boy_m_type.glb', 'Animation-only original 23-track clip; not a rigged hands mesh.'),
        ('rejected_static_hand_phone', ROOT/'web/room/hand_phone.glb', 'Static unskinned prop; not usable articulated hands.'),
        ('rejected_procedural_mouse', ROOT/'web/room/mh_v5/desk_mouse_ik.glb', 'Documentation identifies old mouse as hand-built, not an authored capture.'),
        ('rejected_procedural_phone', ROOT/'web/room/mh_v5/room_phone_scroll.glb', 'Existing custom phone clip; no corresponding authored bed-phone capture documented.'),
    ]
    for name in ('Walking', 'Texting', 'Texting While Standing', 'Standing Using Touchscreen Tablet', 'Gaming'):
        candidates.append(('downloaded_' + name.lower().replace(' ', '_'), downloads/(name+'.fbx'),
                           'Existing user-downloaded Mixamo source; private import only, never standalone redistribution.'))
    output.mkdir(parents=True, exist_ok=True)
    entries = []
    for role, path, provenance in candidates:
        if not path.is_file():
            entries.append({'role': role, 'source': str(path), 'missing': True})
            continue
        info = inspect_glb(path) if path.suffix == '.glb' else inspect_fbx(path)
        entry = {'role': role, 'source': str(path), 'sha256': digest(path),
                 'bytes': path.stat().st_size, 'provenance': provenance, 'inspection': info}
        if role in ('owner_skin', 'authored_typing') or role.startswith('downloaded_'):
            target = output/'SourceAssets'/path.name
            target.parent.mkdir(exist_ok=True)
            shutil.copy2(path, target)
            entry['staged'] = str(target.relative_to(output))
        entries.append(entry)
    owner = next(e for e in entries if e['role'] == 'owner_skin')['inspection']
    owner_names = set(owner['joint_names'])
    for entry in entries:
        inspection = entry.get('inspection', {})
        names = set(inspection.get('animation_target_names', [])) or set(inspection.get('joint_names', []))
        if names:
            entry['owner_name_compatibility'] = {'matched': len(names & owner_names),
                                                'targets': len(names), 'unmatched': sorted(names-owner_names),
                                                'note': 'Name coverage only; rest-pose/axis and first-person framing remain server validation requirements.'}
    manifest = {'private_only': True, 'rendered': False, 'procedural_motion_added': False,
                'selection': [entry['role'] for entry in entries if 'staged' in entry],
                'raw_remy_with_skin_found': False,
                'game_animation_sample_found': False,
                'missing_requirements': ['Authored mouse-use motion capture or authored first-person mouse clip.',
                                         'A reviewed adult realistic first-person hand mesh if existing owner hands are rejected.',
                                         'Server conversion to skeletal FBX and real contact checks; no raw clip is claimed ready in Unreal.'],
                'binding_requirements': {
                    'rig_source': 'SourceAssets/char_mixamo.glb',
                    'ue_skeletal_mesh_object_path': None, 'ue_skeleton_object_path': None,
                    'runtime_ready': False,
                    'animation_sources': {'Walk': 'SourceAssets/Walking.fbx',
                                          'DeskTyping': 'SourceAssets/room_mx_typing.glb',
                                          'Phone': 'SourceAssets/Texting.fbx',
                                          'Gaming': 'SourceAssets/Gaming.fbx', 'DeskMouse': None},
                    'gates': ['Import all clips onto the validated chosen skeleton with an explicit rest-pose retarget when needed.',
                              'Verify skin bind matrices, arm/finger chain axes and scale; matching names alone is not compatibility.',
                              'Do not bind DeskMouse until a genuine mouse clip exists; Gaming is not mouse-use motion.',
                              'Verify contact with actual keyboard, mouse, phone and visible anatomy on server.'],
                    'walking_rest_pose_warning': 'Raw Walking hips Y209.1508 and spine pre-rotation[-5.735,0,.6593] differ from Texting/Gaming hipsY104.2749 and spine[-9.195,0,0].'},
                'license_policy': 'Mixamo raw FBX is private source input only. See docs/design/mixamo/README.md; do not publish this bundle.',
                'entries': entries}
    (output/'source-manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    archive = output.with_suffix('.tar.gz')
    with tarfile.open(archive, 'w:gz', compresslevel=6) as packed:
        packed.add(output/'source-manifest.json', arcname='source-manifest.json')
        packed.add(output/'SourceAssets', arcname='SourceAssets')
    print(json.dumps({'archive': str(archive), 'archive_sha256': digest(archive), 'output': str(output), 'inspected': len(entries),
                      'staged': sum('staged' in e for e in entries),
                      'clips': [{'role': e['role'], 'mesh': e.get('inspection', {}).get('mesh_count'),
                                 'skin': e.get('inspection', {}).get('skin_count'),
                                 'durations': [c['duration_s'] for c in e.get('inspection', {}).get('clips', [])],
                                 'moving_finger_tracks': [c['moving_finger_tracks'] for c in e.get('inspection', {}).get('clips', [])]}
                                for e in entries]}, indent=2))
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'out/first-person-assets')
    parser.add_argument('--downloads', type=Path, default=Path.home()/'Downloads')
    args = parser.parse_args()
    stage(args.output, args.downloads)
