import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from plant_physical_geometry import partition,area_squared
class Physical(unittest.TestCase):
 def test_zero_padding_cannot_supply_base_but_tiny_positive_surface_is_preserved(self):
  fake=[[0,0,0],[0,0,0],[1,0,0]]
  tiny=[[0,0,1],[1e-12,0,1],[0,1e-12,1]]
  positive,discarded=partition([fake,tiny])
  self.assertEqual(discarded,[0]);self.assertEqual(positive,[tiny]);self.assertGreater(area_squared(tiny),0)
 def test_nonfinite_source_refused_not_discarded(self):
  with self.assertRaises(ValueError):partition([[[0,0,0],[1,0,0],[0,float('nan'),0]]])
if __name__=='__main__':unittest.main()
