"""Native effective shader checks must reject opaque/unlit cloth substitutions."""
import copy
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import unreal_import_reference_sheer as sheer

class Properties:
 def __init__(self,**values):self.values=values
 def get_editor_property(self,name):return self.values[name]
class RootMaterial(Properties):
 def get_path_name(self):return '/Engine/RootLitMaterial'
class Instance(Properties):
 def get_path_name(self):return '/Owned/SCM00'

class SheerImport(unittest.TestCase):
 def fixture(self):
  root=RootMaterial(blend_mode='translucent',two_sided=True,shading_model='lit')
  overrides=Properties(override_blend_mode=False,override_two_sided=False,override_shading_model=False)
  material=Instance(parent=root,base_property_overrides=overrides)
  u=SimpleNamespace(MaterialInstance=Instance,Material=RootMaterial,BlendMode=SimpleNamespace(BLEND_TRANSLUCENT='translucent'),MaterialShadingModel=SimpleNamespace(MSM_UNLIT='unlit',MSM_DEFAULT_LIT='lit'),MaterialEditingLibrary=SimpleNamespace(get_scalar_parameter_names=lambda m:[],get_material_instance_scalar_parameter_value=lambda m,n:.12))
  return u,material,root,overrides
 def test_effective_actual_lit_translucent_parent_is_accepted_without_fake_transmission_claim(self):
  u,m,r,o=self.fixture();proof=sheer.lit_translucent_material(u,m)
  self.assertTrue(proof['native_lit_translucent_shader_verified'])
  self.assertFalse(proof['transmission_parameter_available']);self.assertIsNone(proof['actual_transmission_factor'])
 def test_instance_override_cannot_hide_opaque_or_unlit_shader(self):
  for setting,value,override in [('blend_mode','opaque','override_blend_mode'),('shading_model','unlit','override_shading_model'),('two_sided',False,'override_two_sided')]:
   u,m,r,o=self.fixture();o.values[override]=True;o.values[setting]=value
   with self.assertRaises(RuntimeError):sheer.lit_translucent_material(u,m)
 def test_root_opaque_or_unlit_and_cycles_refuse(self):
  for setting,value in [('blend_mode','opaque'),('shading_model','unlit'),('two_sided',False)]:
   u,m,r,o=self.fixture();r.values[setting]=value
   with self.assertRaises(RuntimeError):sheer.lit_translucent_material(u,m)
  u,m,r,o=self.fixture();m.values['parent']=m
  with self.assertRaises(RuntimeError):sheer.lit_translucent_material(u,m)
 def test_available_transmission_factor_must_match_actual_source(self):
  u,m,r,o=self.fixture();u.MaterialEditingLibrary.get_scalar_parameter_names=lambda m:['TransmissionFactor']
  self.assertAlmostEqual(sheer.lit_translucent_material(u,m)['actual_transmission_factor'],.12)
  u.MaterialEditingLibrary.get_material_instance_scalar_parameter_value=lambda m,n:.9
  with self.assertRaises(RuntimeError):sheer.lit_translucent_material(u,m)
 def test_wrong_collision_witness_or_material_names_cannot_be_substituted(self):
  p={'schema':'sub01.reference-sheer-actual-source-bvh.v1','source_sha256':sheer.SHA,'ok':True,'epsilon_cm':0,'unresolved':[],'full91cm_door_sweep_separated':True,'current_door_source_sha256':sheer.DOOR_SHA,'retired_old_balcony_nodes_excluded':list(range(41,49))}
  n={'prepared_sha256':sheer.SHA,'geometry_PBR_image_binary_unchanged':True,'node_names':list(sheer.NAMES),'material_names':['SCM00','SCM01']}
  sheer.validate_source_proof(p,n)
  with self.assertRaises(RuntimeError):sheer.validate_source_proof({**p,'unresolved':[{'positive_intersection':True}]},n)
  with self.assertRaises(RuntimeError):sheer.validate_source_proof(p,{**n,'material_names':['SamePrefix','SamePrefix']})

if __name__=='__main__':unittest.main()
