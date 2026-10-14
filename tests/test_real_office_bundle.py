import hashlib,json,struct,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from prepare_real_office_bundle import shelf_export,pack_books,measured_shelf_depth_plan

class AuthenticOffice(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'shelves.glb';self.source=ROOT/'web/house/assets/real-steel-shelf/originalsource.glb';self.report=shelf_export(self.source,self.path)
 def tearDown(self):self.tmp.cleanup()
 def test_measured_depth_fits_and_impossible_interval_refused(self):
  depth=[-.2510587692260742,.2510587692260742];p=measured_shelf_depth_plan(depth,-3.882499980740249,-3.37298013245)
  self.assertAlmostEqual(p['centre_ue_y_m'],-3.626441211514175,places=7);self.assertGreaterEqual(p['front_desk_gap_m'],.002)
  with self.assertRaisesRegex(ValueError,'cannot fit'):measured_shelf_depth_plan(depth,-3.882499980740249,-3.38)
 def test_actual_five_boards_two_copies_and_original_binary_unchanged(self):
  old=self.source.read_bytes();new=self.path.read_bytes();a=struct.unpack_from('<I',old,12)[0];b=struct.unpack_from('<I',new,12)[0]
  self.assertEqual(old[20+a:],new[20+b:]);self.assertEqual(len(self.report['boards']),10);self.assertEqual(self.report['triangles_per_authentic_shelf'],4348)
  self.assertAlmostEqual(self.report['boards'][0]['top_ue_m'],.15897059442311526)
  oldjson=json.loads(old[20:20+a]);newjson=json.loads(new[20:20+b]);self.assertEqual(oldjson['materials'],newjson['materials']);self.assertEqual(oldjson['meshes'][0]['primitives'],newjson['meshes'][0]['primitives'])
 def test_all46_complete_bounds_are_supported_only_by_actual_boards(self):
  books=[{'id':f'Book{i:02d}','old_bounds_ue_m':[[0,0,0],[.035+(i%4)*.015,.24,.20]],'geometry_uv_materials_unchanged':True}for i in range(46)]
  placed=pack_books(books,self.report['boards']);self.assertEqual(len(placed),46);lookup={(b['instance'],b['board']):b for b in self.report['boards']}
  for p in placed:
   board=lookup[p['shelf_instance'],p['board']];lo,hi=p['new_bounds_ue_m'];a,b=board['xy_bounds_m'];self.assertGreaterEqual(lo[0],a[0]+.02-1e-8);self.assertLessEqual(hi[0],b[0]-.02+1e-8);self.assertAlmostEqual(lo[2],board['top_ue_m']+.0005);self.assertTrue(p['geometry_uv_materials_unchanged'])
 def test_whole_book_too_wide_refused_instead_of_geometry_deletion(self):
  books=[{'id':f'Book{i}','old_bounds_ue_m':[[0,0,0],[1.1,.24,.20]]}for i in range(46)]
  with self.assertRaises(ValueError):pack_books(books,self.report['boards'])

if __name__=='__main__':unittest.main()
