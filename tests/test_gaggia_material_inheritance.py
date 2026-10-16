"""Regression for actual Interchange Water parent override discovered by task114."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

spec = importlib.util.spec_from_file_location('gaggia_import', Path(__file__).parents[1] / 'tools/unreal_import_real_gaggia.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class Properties:
    def __init__(self, **values): self.values = values
    def get_editor_property(self, key): return self.values[key]

class Material(Properties):
    def get_path_name(self): return self.values['path']

class Instance(Material): pass

class Component:
    def __init__(self, material): self.material = material
    def get_material(self, index):
        assert index == 0
        return self.material

U = SimpleNamespace(Material=Material, MaterialInstanceConstant=Instance,
                    BlendMode=SimpleNamespace(BLEND_TRANSLUCENT=2, BLEND_OPAQUE=0))

def instance(path, parent, override=False, mode=0):
    return Instance(path=path, parent=parent, base_property_overrides=Properties(
        override_blend_mode=override, blend_mode=mode))

class MaterialInheritanceRegression(unittest.TestCase):
    def setUp(self):
        self.root = Material(path='/InterchangeAssets/gltf/M_Default', blend_mode=0)
        self.blend = instance('/InterchangeAssets/gltf/MaterialInstances/MI_Default_Blend_DS', self.root, True, 2)

    def check(self, material, mode='BLEND'):
        return module.verify_alpha(U, Component(material), {'name': 'Water', 'alphaMode': mode}, '/owned')

    def test_actual_interchange_intermediate_override(self):
        result = self.check(instance('/owned/Water', self.blend))
        self.assertEqual(result['actual_blend_mode'], '2')
        self.assertEqual(result['effective_blend_from'], self.blend.get_path_name())
        self.assertEqual(len(result['inheritance_chain']), 3)

    def test_opaque_parent_is_still_rejected_for_blend_source(self):
        with self.assertRaisesRegex(AssertionError, 'Authored source opacity/blend differs'):
            self.check(instance('/owned/Water', self.root))

    def test_closest_override_wins_over_translucent_parent(self):
        result = self.check(instance('/owned/Opaque', self.blend, True, 0), 'OPAQUE')
        self.assertEqual(result['effective_blend_from'], '/owned/Opaque')

    def test_cycle_fails_closed(self):
        material = instance('/owned/Water', self.blend)
        self.blend.values['parent'] = material
        with self.assertRaisesRegex(AssertionError, 'Cyclic material inheritance'):
            self.check(material)

if __name__ == '__main__': unittest.main()
