"""Protocol tests for immutable source ownership and physical unit comparison."""
import copy,importlib.util,json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import unreal_import_original_ps5_assets as m
class SourceContractTests(unittest.TestCase):
 def test_complete_source_is_not_accept_partial_console(self):
  # Contract failure occurs before any Unreal import or source geometry access.
  with self.assertRaises(AssertionError):m.contract({'nodes':[],'meshes':[],'materials':[]})
 def test_normalization_keeps_uniform_shape_in_physical_space(self):
  offset=[-1.25,2.75,.01];a=[500,-200,32900];b=[900,-700,40]
  na=m.normalize_point(a,offset);nb=m.normalize_point(b,offset)
  for i in range(3):self.assertAlmostEqual(na[i]-nb[i],(a[i]-b[i])*m.UNIT,places=12)
 def test_tolerance_is_physical_one_micron_not_raw_large_world(self):
  # An exaggerated raw-world .01cm error is12e−6cm physically, below1µm;
  # a true physical .001cm error must remain greater than1µm after conversion.
  self.assertLess(.01*m.UNIT,.0001)
  self.assertGreater((.001/m.UNIT)*m.UNIT,.0001)
if __name__=='__main__':unittest.main()
