import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from unreal_home_texture_usage_audit import classify


class TextureUsageClassificationTests(unittest.TestCase):
    def test_linear_albedo_is_not_definitive_without_source_parity(self):
        result = classify([{'role': 'albedo'}], False, 'TC_DEFAULT')
        self.assertEqual(result['definite_binding_settings_mismatches'], [])
        self.assertIn('linear_albedo_requires_source_parity', result['warnings'])

    def test_role_conflict_does_not_hide_normal_compression_albedo_mismatch(self):
        result = classify([{'role': 'albedo'}, {'role': 'normal'}], False,
                          '<TextureCompressionSettings.TC_NORMALMAP: 1>')
        self.assertEqual(result['definite_binding_settings_mismatches'],
                         ['normalmap_compression_used_as_albedo'])
        self.assertIn('ambiguous_albedo_normal_role_conflict', result['warnings'])

    def test_normal_settings_are_not_misclassified_as_bad_albedo(self):
        result = classify([{'role': 'normal'}], False, 'TextureCompressionSettings.TC_NORMALMAP')
        self.assertEqual(result['definite_binding_settings_mismatches'], [])
        self.assertEqual(result['warnings'], [])


if __name__ == '__main__':
    unittest.main()
