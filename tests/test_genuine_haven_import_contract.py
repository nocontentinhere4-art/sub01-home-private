"""Retirement fails closed for wrong owner/partial actor or moved protected source."""
import copy,importlib.util
from pathlib import Path
import unittest
spec=importlib.util.spec_from_file_location('haven_import',Path(__file__).resolve().parents[1]/'tools/unreal_import_genuine_haven_sofa.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def owner():
 return {'label':'Haven_linen','transform':copy.deepcopy(m.OLD_TRS),'hidden':False,'editor_hidden':False,'components':[{'mesh':'/Game/Sub01Home/ImportedScene/full-home/StaticMeshes/Mesh_133.Mesh_133','transform':copy.deepcopy(m.OLD_TRS)}]}

class ContractTests(unittest.TestCase):
 def test_complete_pinned_owner(self):
  self.assertTrue(m.original_identity(owner(),174))
 def test_refuses_wrong_or_partial_retirement(self):
  mutations=[
   lambda r:r.update(label='Some other sofa'),
   lambda r:r['components'].append(copy.deepcopy(r['components'][0])),
   lambda r:r['components'][0].update(mesh='/Game/Other.Mesh_133'),
   lambda r:r['transform']['translation'].__setitem__(0,-179.0),
   lambda r:r['components'][0]['transform']['scale'].__setitem__(0,1.01),
   lambda r:r.update(hidden=True),
  ]
  for mutation in mutations:
   with self.subTest(mutation=mutation):
    row=owner();mutation(row)
    with self.assertRaises(AssertionError):m.original_identity(row,174)
if __name__=='__main__':unittest.main()
