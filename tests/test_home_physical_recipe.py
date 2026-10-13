import hashlib
import json
import math
import struct
import sys
from pathlib import Path
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from home_physical_recipe import fixture_strength, validate_inputs, IMPORT_ENERGY_FACTOR, RUNTIME_HDR_ROTATION, CYCLES_HDR_LOOKUP_ROTATION

def glb(path, doc):
    payload = json.dumps(doc).encode()
    payload += b' ' * (-len(payload) % 4)
    raw = b'glTF' + struct.pack('<II', 2, 20 + len(payload)) + struct.pack('<II', len(payload), 0x4E4F534A) + payload
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()

def inputs(tmp_path):
    source, atlas, proof = (tmp_path / name for name in ['source.glb', 'atlas.glb', 'proof.json'])
    doc = {'nodes': [{'mesh': 0}], 'materials': [{'extras': {'lampEmission': .6}}, {'extensions': {'KHR_materials_unlit': {}}}], 'extensions': {'KHR_lights_punctual': {'lights': [{'type': 'directional', 'intensity': 3.2}]}}}
    source_sha = glb(source, doc)
    atlas_sha = glb(atlas, {'nodes': [{'mesh': 0}], 'extras': {'width': 32, 'height': 16}})
    proof.write_text(json.dumps({'source_sha256': source_sha, 'atlas_sha256': atlas_sha, 'receivers': 1, 'bad': {}, 'checks': {'receiver': {'fresh_matches_atlas': True}}}))
    return source, atlas, source_sha, atlas_sha, proof, doc

def check_immutable_photometric_source_and_geometry_proof(tmp_path):
    source, atlas, source_sha, atlas_sha, proof, _ = inputs(tmp_path)
    before = source.read_bytes(), atlas.read_bytes()
    report = validate_inputs(source, atlas, source_sha, atlas_sha, proof)
    assert report['source_lights'][0]['intensity'] == 3.2
    assert report['unlit_materials'] == 1
    assert report['tagged_fixtures'] == [{'material': 0, 'strength': .6}]
    assert (source.read_bytes(), atlas.read_bytes()) == before
    assert IMPORT_ENERGY_FACTOR == 683
    assert RUNTIME_HDR_ROTATION == -math.pi / 2
    assert CYCLES_HDR_LOOKUP_ROTATION == math.pi / 2

def check_refusals(test, tmp_path):
    source, atlas, source_sha, atlas_sha, proof, doc = inputs(tmp_path)
    with test.assertRaisesRegex(ValueError, 'SHA mismatch'):
        validate_inputs(source, atlas, '0' * 64, atlas_sha, proof)
    data = json.loads(proof.read_text());data['checks']['receiver']['fresh_matches_atlas'] = False;proof.write_text(json.dumps(data))
    with test.assertRaisesRegex(ValueError, 'Incomplete'):
        validate_inputs(source, atlas, source_sha, atlas_sha, proof)
    doc['nodes'][0]['extras'] = {'excludeStaticBake': True}
    source_sha = glb(source, doc)
    with test.assertRaisesRegex(ValueError, 'Excluded contact'):
        validate_inputs(source, atlas, source_sha, atlas_sha)

class PhysicalRecipeTests(unittest.TestCase):
    def test_immutable_photometric_source_and_geometry_proof(self):
        with tempfile.TemporaryDirectory() as folder:
            check_immutable_photometric_source_and_geometry_proof(Path(folder))

    def test_refuses_mutation_stale_proof_and_contact_remnants(self):
        with tempfile.TemporaryDirectory() as folder:
            check_refusals(self, Path(folder))

    def test_only_explicit_positive_finite_fixture_metadata(self):
        for value in [None, True, False, '1.3', -1, 0, float('nan'), float('inf')]:
            with self.subTest(value=value):
                self.assertEqual(fixture_strength(value, 'night'), 0)

    def test_no_fixture_emission_in_day(self):
        self.assertEqual(fixture_strength(1.3, 'day'), 0)
        self.assertEqual(fixture_strength(1.3, 'night'), 1.3)

if __name__ == '__main__':
    unittest.main()
