import importlib.util,math,unittest
from pathlib import Path
p=Path(__file__).resolve().parents[1]/'tools/unreal_chair_surface_audit.py';s=importlib.util.spec_from_file_location('audit',p);a=importlib.util.module_from_spec(s);s.loader.exec_module(a)
class Surface(unittest.TestCase):
 def test_actual_triangles_not_box_and_lumbar_excluded(self):
  vertices=[[180,-210,50.5],[220,-210,50.5],[220,-170,50.5],[180,-170,50.5],[180,-210,85],[220,-210,85],[220,-170,85]]
  x=a.cushion_top(vertices,[0,1,2,0,2,3,4,5,6]);self.assertEqual(x['triangle_indices'],[[0,1,2],[0,2,3]]);self.assertFalse(x['collision_trace_verified'])
 def test_bad_identity_and_wrong_height_refused(self):
  self.assertFalse(a.material_identity(['chair_plastic','generic_fabric']));self.assertTrue(a.material_identity(['MI_chair_fabric']))
  with self.assertRaises(ValueError):a.cushion_top([[180,-210,60],[220,-210,60],[220,-170,60]],[0,1,2])
  with self.assertRaises(ValueError):a.cushion_top([[180,-210,50.5],[220,-210,50.5],[220,-170,50.5]],[0,2,1])
  with self.assertRaises(ValueError):a.cushion_top([[math.nan,0,0]],[0,0,0])
if __name__=='__main__':unittest.main()
