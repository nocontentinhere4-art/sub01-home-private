import unittest
from real_home_window_plan import plan

class ApertureConstructionTests(unittest.TestCase):
 def test_frame_is_inside_measured_wall_and_header(self):
  p=plan();d=p['construction_dimensions']
  self.assertLess(d['overall_profile_depth_m'],d['wall_depth_m'])
  for u in p['units']:
   self.assertEqual(u['rough_v'],[.70,2.575])
   self.assertAlmostEqual(u['unit_v'][0]-.70,.020)
   self.assertAlmostEqual(2.575-u['unit_v'][1],.020)
   self.assertLess(u['unit_v'][1],2.575) # old273.75cm frame penetrated header
 def test_entry_and_upper_assemblies_are_separate_ownership(self):
  p=plan();nodes=p['exact_old_lower_frame_nodes']
  self.assertEqual(len(nodes),30);self.assertEqual(len(set(nodes)),30)
  self.assertFalse(set(nodes)&set(range(41,60)))
  entry=p['entry_boundary_renderer_owned'];left,right=entry['rough_u']
  for a,b in p['new_front_wall_infill_piers_u_m']:
   self.assertTrue(b<=left or a>=right)
 def test_lights_have_real_house_scale_not_stretched_single_sash(self):
  p=plan()
  self.assertEqual(sum(u['lights']for u in p['units']),15)
  for u in p['units']:
   self.assertLess(u['unit_width_m']/u['lights'],1.)
  middle=next(u for u in p['units']if u['id']=='WestMiddleTV')
  self.assertIsNone(middle['operable_light'])

if __name__=='__main__':unittest.main()
