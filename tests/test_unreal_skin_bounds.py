import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from unreal_skin_bounds import select_built_primary,source_body_candidate
class BoundsTests(unittest.TestCase):
 def test_zero_and_nonfinite_bounds_are_not_runtime_candidates(self):
  self.assertIsNone(select_built_primary([{'row':{'bounds_extent_cm':[0,0,0]}}]))
  self.assertIsNone(select_built_primary([{'row':{'bounds_extent_cm':[10,float('nan'),10]}}]))
 def test_actual_nonzero_body_selected_not_first_lining(self):
  lining={'row':{'bounds_extent_cm':[0,0,0]}}
  body={'row':{'bounds_extent_cm':[50,30,90]}}
  self.assertIs(select_built_primary([lining,body]),body)
 def test_node_named_import_association_is_diagnostic_only(self):
  class Mesh:
   def get_name(self):return 'tripo_node_id'
  row={'mesh':Mesh(),'row':{'bounds_extent_cm':[0,0,0]}}
  doc={'meshes':[{'name':'tripo_mesh_id','primitives':[{'attributes':{'POSITION':0}}]}], 'accessors':[{'count':100}], 'nodes':[{'name':'tripo_node_id','mesh':0}]}
  self.assertIs(source_body_candidate(doc,[row],lambda n:n),row)
  self.assertIsNone(select_built_primary([row]))
if __name__=='__main__' :unittest.main()
