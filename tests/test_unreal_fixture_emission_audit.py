import hashlib
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from unreal_fixture_emission_audit import source_fixtures


class FixtureSourceGuards(unittest.TestCase):
    def test_only_positive_source_tags_qualify_and_shared_instances_are_retained(self):
        document = {'materials': [
            {'name': 'fixture', 'extras': {'lampEmission': 1.3}, 'emissiveFactor': [1, .6, .2]},
            {'name': 'PCscreen', 'emissiveFactor': [1, 1, 1]},
            {'name': 'bad_bool', 'extras': {'lampEmission': True}},
            {'name': 'off', 'extras': {'lampEmission': 0}},
            {'name': 'invalid', 'extras': {'lampEmission': float('nan')}}],
            'meshes': [{'primitives': [{'material': i} for i in range(5)]}],
            'nodes': [{'name': 'Bulb', 'mesh': 0}, {'name': 'OtherBulb', 'mesh': 0}]}
        data = json.dumps(document).encode()
        data += b' ' * (-len(data) % 4)
        raw = struct.pack('<4sIIII', b'glTF', 2, 20+len(data), len(data), 0x4E4F534A)+data
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'source.glb';path.write_bytes(raw)
            sha = hashlib.sha256(raw).hexdigest()
            result = source_fixtures(path, sha)
            self.assertEqual(result['tagged_material_count'], 1)
            self.assertEqual([f['source_node_index'] for f in result['fixtures']], [0, 1])
            self.assertTrue(all(f['source_material_name'] == 'fixture' for f in result['fixtures']))
            with self.assertRaisesRegex(ValueError, 'SHA256'):
                source_fixtures(path, '0'*64)
            with self.assertRaisesRegex(ValueError, 'SHA256'):
                source_fixtures(path, sha[:8])


if __name__ == '__main__':
    unittest.main()
