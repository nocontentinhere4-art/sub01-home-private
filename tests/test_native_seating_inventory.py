import importlib.util,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('inventory',ROOT/'tools/inventory_native_seating.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class SeatingInventory(unittest.TestCase):
 def test_actual_captures_and_chair_not_fallback(self):
  report=m.inventory()
  self.assertEqual(report['chair']['authored_seat_top_cm'],50.5)
  for row in report['clips'].values():
   self.assertTrue(row['bone_names_match']);self.assertTrue(row['reference_trs_match']);self.assertEqual(row['bone_count'],65);self.assertFalse(row['physical_contact_verified'])
  self.assertAlmostEqual(report['clips']['sit_down']['duration_s'],2.2333333,places=5)
  self.assertGreater(report['clips']['sit_down']['hip_translation_cm']['first'][2]-report['clips']['sit_down']['hip_translation_cm']['last'][2],35)
  self.assertFalse(report['ready']);self.assertIsNone(report['chair']['native_unique_component'])
 def test_mismatched_reference_is_reported_not_retarged(self):
  owner=m.dump(ROOT/'web/room/char_mixamo.glb');clip=m.dump(ROOT/'web/room/mh_mx/room_mx_stand_to_sit.glb')
  clip['nodes'][6]['translation'][0]+=1
  record=m.clip_record(owner,clip);self.assertFalse(record['reference_trs_match']);self.assertEqual(record['max_reference_trs_error'],1)
if __name__=='__main__':unittest.main()
