"""LOD integration checks: texture reuse, unchanged non-leaves, axis/UV/normal data."""
import importlib.util
import json
import math
from pathlib import Path
import struct
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('plant_pack', ROOT / 'tools/package_home_plant_lod.py')
pack = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pack)
ASSET = ROOT / 'web/house/assets/potted_plant_01'
NAME = 'potted_plant_01_leaf_lod'


def load(path):
    doc = json.loads(path.read_text())
    return doc, (path.parent / doc['buffers'][0]['uri']).read_bytes()


def floats(doc, binary, index):
    accessor = doc['accessors'][index]
    assert accessor['componentType'] == 5126
    dims = {'VEC2': 2, 'VEC3': 3}[accessor['type']]
    values = struct.unpack('<' + 'f' * (accessor['count'] * dims), pack.accessor_bytes(doc, binary, index))
    return [values[n:n + dims] for n in range(0, len(values), dims)]


class PlantLOD(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original, cls.original_bin = load(ASSET / 'potted_plant_01.gltf')
        cls.doc, cls.binary = load(ASSET / (NAME + '.gltf'))

    def test_source_roles_transforms_and_materials_unchanged(self):
        for key in ('nodes', 'scenes', 'scene', 'materials', 'images', 'textures', 'samplers'):
            self.assertEqual(self.original.get(key), self.doc.get(key), key)
        self.assertEqual(len(self.doc['images']), 6)
        self.assertNotEqual(self.original['buffers'][0]['uri'], self.doc['buffers'][0]['uri'])
        self.assertEqual(len(self.binary), self.doc['buffers'][0]['byteLength'])

    def test_non_leaf_accessors_exact_original_bytes(self):
        for old_mesh, new_mesh in zip(self.original['meshes'][:3], self.doc['meshes'][:3]):
            old, new = old_mesh['primitives'][0], new_mesh['primitives'][0]
            for key in (*old['attributes'], 'indices'):
                old_index = old['indices'] if key == 'indices' else old['attributes'][key]
                new_index = new['indices'] if key == 'indices' else new['attributes'][key]
                self.assertEqual(pack.accessor_bytes(self.original, self.original_bin, old_index), pack.accessor_bytes(self.doc, self.binary, new_index), (new_mesh['name'], key))

    def test_leaf_extent_uv_normal_conventions(self):
        old = self.original['meshes'][3]['primitives'][0]
        new = self.doc['meshes'][3]['primitives'][0]
        self.assertEqual(self.doc['accessors'][new['indices']]['count'] // 3, 21380)
        before = floats(self.original, self.original_bin, old['attributes']['POSITION'])
        after = floats(self.doc, self.binary, new['attributes']['POSITION'])
        for axis in range(3):
            for reducer in (min, max):
                self.assertLess(abs(reducer(v[axis] for v in before) - reducer(v[axis] for v in after)), .005)
        # Blender import/export retains glTF Y-up and normalized original UV convention.
        old_uv = floats(self.original, self.original_bin, old['attributes']['TEXCOORD_0'])
        new_uv = floats(self.doc, self.binary, new['attributes']['TEXCOORD_0'])
        for axis in range(2):
            self.assertGreaterEqual(min(v[axis] for v in new_uv), min(v[axis] for v in old_uv) - .0001)
            self.assertLessEqual(max(v[axis] for v in new_uv), max(v[axis] for v in old_uv) + .0001)
        for normal in floats(self.doc, self.binary, new['attributes']['NORMAL']):
            self.assertAlmostEqual(math.sqrt(sum(v*v for v in normal)), 1, delta=.001)

    def test_full_lite_one_geometry_and_original_maps(self):
        lite_path = ROOT / 'web/house/assets/lite/potted_plant_01'
        lite, binary = load(lite_path / (NAME + '.gltf'))
        original = json.loads((lite_path / 'potted_plant_01.gltf').read_text())
        self.assertEqual(binary, self.binary)
        for key in ('images', 'materials', 'textures', 'samplers'):
            self.assertEqual(lite.get(key), original.get(key))
        self.assertEqual(lite['meshes'], self.doc['meshes'])


if __name__ == '__main__':
    unittest.main()
