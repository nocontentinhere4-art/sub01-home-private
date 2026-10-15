"""Source metadata checks supplement actual Runpod BVH proof; no native claims."""
import copy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import unreal_import_reference_media as media

class MediaLayout(unittest.TestCase):
 def rows(self):
  proof={'schema':'sub01.reference-media-source-bvh.v1','ok':True,'sha256':media.SHA,'parts':11,'pairs':[],'epsilon_m':0,'ignored_collision_pairs':0,'retained_source_sha256':media.HOME_SHA}
  fit={'schema':'sub01.reference-media-real-leveling.v1','sha256':media.SHA,'unchanged_coffee_table':True,'unchanged_sofa':True,'cabinet_dimensions_unchanged':True,'material_groups':11,'floor_side_feet':[{'extension_m':.00775,'clearance_m':.0000487}for _ in range(2)]}
  return proof,fit
 def test_refuses_source_intersections_or_different_asset(self):
  p,f=self.rows();self.assertTrue(media.validate_source_layout(p,f))
  for bad in ({**p,'pairs':[{'source_node':275,'pairs':1}]},{**p,'sha256':'0'*64},{**p,'ok':False}):
   with self.assertRaises(RuntimeError):media.validate_source_layout(bad,f)
 def test_requires_supported_leveling_and_preserved_furniture(self):
  p,f=self.rows()
  for bad in ({**f,'unchanged_sofa':False},{**f,'floor_side_feet':[]},{**f,'floor_side_feet':[{'extension_m':.00775,'clearance_m':-.001}for _ in range(2)]}):
   with self.assertRaises(RuntimeError):media.validate_source_layout(p,bad)
if __name__=='__main__':unittest.main()
