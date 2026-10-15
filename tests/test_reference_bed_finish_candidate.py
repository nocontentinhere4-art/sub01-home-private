"""Frozen bed source cannot expand retirement or conceal failed physical proof."""
import copy,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from unreal_import_reference_bed_finish import validate_contract
ROOT=Path(__file__).resolve().parents[1]/'docs/proposed/reference-bed-finish-r2'
class BedFinishCandidateTests(unittest.TestCase):
 def setUp(self):self.report=json.loads((ROOT/'bed-finish-source.json').read_text());self.proof=json.loads((ROOT/'bed-finish-physical-proof.json').read_text())
 def check(self):validate_contract(self.report,self.proof)
 def test_actual_frozen_source(self):self.check()
 def test_mattress_cannot_be_retired(self):
  self.report['retire_only_source_nodes'].append(262)
  with self.assertRaises(RuntimeError):self.check()
 def test_lamp_cannot_be_changed(self):
  self.report['functional_bedside_lamp195_199_unchanged']=False
  with self.assertRaises(RuntimeError):self.check()
 def test_slats_cannot_be_changed(self):
  self.report['slats265_unchanged']=False
  with self.assertRaises(RuntimeError):self.check()
 def test_cloth_geometry_cannot_change(self):
  self.report['all72200cloth_triangles_and_original_binary_unchanged']=False
  with self.assertRaises(RuntimeError):self.check()
 def test_wrong_original_cloth_source_refused(self):
  self.report['cloth_source_original_unchanged_sha256']='0'*64
  with self.assertRaises(RuntimeError):self.check()
 def test_physical_intersection_cannot_be_ignored(self):
  self.proof['new_head_source_bvh']['unresolved_intersections']=[{'owner':'lamp'}]
  with self.assertRaises(RuntimeError):self.check()
 def test_geometry_epsilon_cannot_be_widened(self):
  self.proof['new_head_source_bvh']['epsilon_m']=.001
  with self.assertRaises(RuntimeError):self.check()
 def test_headboard_outside_original_bounds_refused(self):
  self.proof['new_headboard_inside_original_261'][0]['inside_old_headboard_AABB']=False
  with self.assertRaises(RuntimeError):self.check()
if __name__=='__main__':unittest.main()
