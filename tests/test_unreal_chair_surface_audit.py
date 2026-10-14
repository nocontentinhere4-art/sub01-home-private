import importlib.util,math,unittest
from pathlib import Path
p=Path(__file__).resolve().parents[1]/'tools/unreal_chair_surface_audit.py';s=importlib.util.spec_from_file_location('audit',p);a=importlib.util.module_from_spec(s);s.loader.exec_module(a)
class Surface(unittest.TestCase):
 def test_actual_triangles_not_box_and_lumbar_excluded(self):
  vertices=[[180,-210,50.5],[220,-210,50.5],[220,-170,50.5],[180,-170,50.5],[180,-210,85],[220,-210,85],[220,-170,85]]
  x=a.cushion_top(vertices,[0,1,2,0,2,3,4,5,6]);self.assertEqual(x['triangle_indices'],[[0,1,2],[0,2,3]]);self.assertFalse(x['collision_trace_verified'])
 def test_bad_identity_and_wrong_height_refused(self):
  self.assertFalse(a.material_identity(['chair_plastic','generic_fabric']));self.assertTrue(a.material_identity(['MI_chair_fabric']))
  measured=a.cushion_top([[180,-210,60],[220,-210,60],[220,-170,60]],[0,1,2])
  self.assertEqual(measured['authored_top_delta_cm'],9.5);self.assertFalse(measured['collision_trace_verified'])
  with self.assertRaises(ValueError):a.cushion_top([[180,-210,50.5],[220,-210,50.5],[220,-170,50.5]],[0,2,1])
  with self.assertRaises(ValueError):a.cushion_top([[math.nan,0,0]],[0,0,0])
 def test_imported_normals_identify_ue_clockwise_surface(self):
  vertices=[[180,-210,50.5],[220,-210,50.5],[220,-170,50.5],[180,-170,50.5]]
  actual=a.cushion_top(vertices,[0,2,1,0,3,2],[[0,0,1]]*4)
  self.assertEqual(actual['triangle_indices'],[[0,2,1],[0,3,2]])
  with self.assertRaises(ValueError):a.cushion_top(vertices,[0,2,1,0,3,2],[[0,0,-1]]*4)
  with self.assertRaises(ValueError):a.cushion_top(vertices,[0,2,1],[[0,0,1]])
 def test_seat_and_lumbar_ledge_are_distinct_real_patches(self):
  vertices=[[180,-210,48],[220,-210,48],[220,-170,48],[180,-170,48],
            [180,-170,57],[220,-170,57],[220,-166,57],[180,-166,57]]
  measured=a.cushion_top(vertices,[0,1,2,0,2,3,4,5,6,4,6,7])
  self.assertEqual(len(measured['patches']),2);self.assertEqual(measured['triangle_indices'],[[0,1,2],[0,2,3]])
  self.assertEqual(measured['world_bounds_cm']['max'][2],48)
if __name__=='__main__':unittest.main()
