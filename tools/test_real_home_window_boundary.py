import unittest
from prove_real_home_windows import supported_boundary_contact

class RealMasonryContacts(unittest.TestCase):
 def test_vertical_wall_top_edge_support_is_not_penetration(self):
  tri=[(-4,0,0),(-4,0,.7),(-4,1,.7)]
  self.assertTrue(supported_boundary_contact('InteriorWalnutSill',158,tri,[[-4,0,.7],[-3.85,1,.72]]))
 def test_one_millimetre_intrusion_remains_refused(self):
  tri=[(-4,0,0),(-4,0,.7),(-4,1,.7)]
  self.assertFalse(supported_boundary_contact('InteriorWalnutSill',158,tri,[[-4,0,.699],[-3.85,1,.72]]))
 def test_no_global_wall_or_fixture_exemption(self):
  tri=[(-4,0,0),(-4,0,.7),(-4,1,.7)];b=[[-4,0,.7],[-3.85,1,.72]]
  self.assertFalse(supported_boundary_contact('Glass',158,tri,b))
  self.assertFalse(supported_boundary_contact('InteriorWalnutSill',159,tri,b))
 def test_protected_tv_backer_cannot_be_called_sill_support(self):
  tri=[(-3.91,-1.125,0),(-3.91,-1.125,2.8),(-3.91,1.025,2.8)]
  self.assertFalse(supported_boundary_contact('InteriorWalnutSill',158,tri,[[-3.92,-1,.7],[-3.85,1,.72]]))
if __name__=='__main__':unittest.main()
