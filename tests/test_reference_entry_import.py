"""Guard visibility-only retirement and explicit native material binding."""
from pathlib import Path
import copy
import sys
import unittest
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import unreal_import_reference_entry as entry

class EntryImport(unittest.TestCase):
 def test_visibility_contract_does_not_change_any_original_collision(self):
  actors=[SimpleNamespace(get_path_name=lambda key=key:key)for key in('support','wall')]
  before={key:{'hidden':False,'editor_hidden':False,'actor_collision':True,'components':[{'collision':'QueryAndPhysics','profile':'BlockAll','mesh':'original','transform':[1,2,3],'materials':['original']}]}for key in('support','wall')}
  after=entry.expected_hidden(before,actors)
  self.assertFalse(before['support']['hidden'])
  for key in before:
   self.assertTrue(after[key]['hidden']);self.assertTrue(after[key]['editor_hidden'])
   self.assertEqual(after[key]['components'],before[key]['components'])
   self.assertEqual(after[key]['actor_collision'],before[key]['actor_collision'])
 def test_material_binding_uses_actual_assigned_owned_instance_not_asset_or_slot_names(self):
  material=SimpleNamespace(get_path_name=lambda:'/Owned/Mat_Truncated.Mat_Truncated')
  component=SimpleNamespace(get_num_materials=lambda:1,get_material=lambda index:material)
  self.assertEqual(entry.assigned_material_binding(component,{'name':'Full authentic source material'},'/Owned'),{'Full authentic source material':'/Owned/Mat_Truncated.Mat_Truncated'})
  with self.assertRaises(RuntimeError):entry.assigned_material_binding(component,{'name':'x'},'/Foreign')
  component.get_num_materials=lambda:2
  with self.assertRaises(RuntimeError):entry.assigned_material_binding(component,{'name':'x'},'/Owned')

if __name__=='__main__':unittest.main()
