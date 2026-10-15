import copy,json,unittest
from pathlib import Path
from prove_reference_living_layout import prove,segment_rect
class Layout(unittest.TestCase):
 def setUp(self):self.c=json.loads((Path(__file__).resolve().parents[1]/'docs/proposed/living-layout-clearance-r1/layout-proposal.json').read_text())
 def test_original_narrow_slot_refuses(self):
  self.c['furniture']['sofa'][:2]=[-226.25,-133.75];self.c['furniture']['coffeeTable'][:2]=[-298,-253]
  with self.assertRaisesRegex(AssertionError,'insufficient'):prove(self.c)
 def test_full_scale_real_furniture_allows_local_routes(self):
  p=prove(self.c);self.assertEqual(p['gaps']['table_to_sofa_cm'],38.25);self.assertFalse(p['nativePlacementVerified'])
 def test_functional_tv_plane_cannot_be_shifted(self):
  self.c['tvFunctionalPlane']['x']=-375.7
  with self.assertRaisesRegex(AssertionError,'TV/input'):prove(self.c)
 def test_diagonal_capsule_distance_uses_corner_not_axis_gap(self):
  self.assertAlmostEqual(segment_rect([-2,-2],[-1,-1],[0,1,0,1]),2**.5)
  self.assertEqual(segment_rect([-2,-2],[2,2],[0,1,0,1]),0)
if __name__=='__main__':unittest.main()
