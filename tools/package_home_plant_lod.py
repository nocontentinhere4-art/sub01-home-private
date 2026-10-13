"""Package leaf-only candidate geometry with untouched original PBR materials/maps."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'web/house/assets'
NAME = 'potted_plant_01_leaf_lod'


def read_glb(path):
    raw = path.read_bytes()
    assert raw[:4] == b'glTF'
    length = struct.unpack_from('<I', raw, 12)[0]
    doc = json.loads(raw[20:20 + length])
    offset = 20 + length
    size, kind = struct.unpack_from('<II', raw, offset)
    assert kind == 0x004E4942
    return doc, raw[offset + 8:offset + 8 + size]


def accessor_bytes(doc, binary, index):
    accessor = doc['accessors'][index]
    view = doc['bufferViews'][accessor['bufferView']]
    assert 'sparse' not in accessor and 'byteStride' not in view
    count = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4}[accessor['type']]
    width = {5120: 1, 5121: 1, 5122: 2, 5123: 2, 5125: 4, 5126: 4}[accessor['componentType']]
    start = view.get('byteOffset', 0) + accessor.get('byteOffset', 0)
    size = accessor['count'] * count * width
    return binary[start:start + size]


def package(candidate):
    original_path = ASSETS / 'potted_plant_01/potted_plant_01.gltf'
    original = json.loads(original_path.read_text())
    binary_path = original_path.parent / original['buffers'][0]['uri']
    original_binary = binary_path.read_bytes()
    modified, modified_binary = read_glb(candidate)
    leaf_node = next(n for n in modified['nodes'] if n['name'] == 'LOD_potted_plant_01_leaves')
    leaf_primitive = modified['meshes'][leaf_node['mesh']]['primitives'][0]
    doc = copy.deepcopy(original)
    leaf_index = next(n['mesh'] for n in original['nodes'] if n['name'] == 'potted_plant_01_leaves')
    doc['accessors'] = []
    doc['bufferViews'] = []
    packed = bytearray()
    for mesh_index, mesh in enumerate(doc['meshes']):
        primitive = mesh['primitives'][0]
        source, blob = (modified, modified_binary) if mesh_index == leaf_index else (original, original_binary)
        reference = leaf_primitive if mesh_index == leaf_index else original['meshes'][mesh_index]['primitives'][0]
        for key, index in [*reference['attributes'].items(), ('indices', reference['indices'])]:
            data = accessor_bytes(source, blob, index)
            packed.extend(b'\x00' * (-len(packed) % 4))
            offset = len(packed)
            packed.extend(data)
            accessor = copy.deepcopy(source['accessors'][index])
            accessor.pop('byteOffset', None)
            accessor['bufferView'] = len(doc['bufferViews'])
            doc['bufferViews'].append({'buffer': 0, 'byteOffset': offset, 'byteLength': len(data), 'target': 34963 if key == 'indices' else 34962})
            target = len(doc['accessors'])
            doc['accessors'].append(accessor)
            if key == 'indices':
                primitive[key] = target
            else:
                primitive['attributes'][key] = target
    doc['buffers'] = [{'byteLength': len(packed), 'uri': NAME + '.bin'}]
    output = original_path.parent
    (output / (NAME + '.bin')).write_bytes(packed)
    (output / (NAME + '.gltf')).write_text(json.dumps(doc, separators=(',', ':')) + '\n')
    lite_path = ASSETS / 'lite/potted_plant_01/potted_plant_01.gltf'
    lite_original = json.loads(lite_path.read_text())
    lite = copy.deepcopy(doc)
    for key in ('materials', 'images', 'textures', 'samplers'):
        if key in lite_original:
            lite[key] = lite_original[key]
    lite['buffers'][0]['uri'] = '../../potted_plant_01/' + NAME + '.bin'
    (lite_path.parent / (NAME + '.gltf')).write_text(json.dumps(lite, separators=(',', ':')) + '\n')
    digest = lambda data: hashlib.sha256(data).hexdigest()
    metadata = {'source': 'Poly Haven potted_plant_01 (CC0); original source and attribution unchanged', 'source_url': 'https://polyhaven.com/a/potted_plant_01', 'license': 'CC0-1.0', 'original_provenance': 'web/house/assets/manifest.json entry potted_plant_01 (unchanged source hashes)', 'builder': 'tools/build_home_plant_lod.py followed by tools/package_home_plant_lod.py', 'method': 'Blender collapse 20% leaves only, scanned split normals transferred; lossy geometry visually checked at 900px close range; pot/stem/pebbles accessors copied byte-for-byte', 'original_gltf_sha256': digest(original_path.read_bytes()), 'original_bin_sha256': digest(original_binary), 'candidate_glb_sha256': digest(candidate.read_bytes()), 'optimized_bin_sha256': digest(packed), 'original_bytes': len(original_binary), 'optimized_bytes': len(packed), 'full_lite_share_geometry': True, 'original_materials_and_image_urls_unchanged': True, 'triangles': {}}
    for m in doc['meshes']:
        p = m['primitives'][0]
        metadata['triangles'][m['name']] = doc['accessors'][p['indices']]['count'] // 3
    (output / (NAME + '.json')).write_text(json.dumps(metadata, indent=2) + '\n')
    print(json.dumps(metadata, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--candidate', type=Path, required=True)
    package(parser.parse_args().candidate)
