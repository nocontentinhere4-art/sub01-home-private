import json,sys,unittest,tempfile,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from real_linea_lamp_mount import mount_plan
from prepare_real_linea140_placement import place_bytes,SHA
from unreal_import_real_linea140 import run

class GenuineMount(unittest.TestCase):
 def fixture(self):
  return {'planned':{'DeskLamp':{'yaw_deg':90,'location_cm':[92.32936859130861,-314.5301260612905,84.49999491373697],'bulb_cm':[110,-315,154.06085650126138],'light_cm':[110,-315,135],'actor':'reviewed-exact-actor','materials':[{'material':'reviewed-body'},{'material':'reviewed-bulb'}]}}}
 def test_actual_mount_pin_clearance_and_distinct_light_delta(self):
  p=mount_plan(ROOT/'web/house/assets/real-linea140/originalsource.glb',ROOT/'web/house/assets/desk_lamp_arm_01/desk_lamp_arm_01.gltf',self.fixture())
  self.assertGreater(p['radial_pin_clearance_m'],.004);self.assertEqual(p['opened_cap_source_node'],8)
  self.assertAlmostEqual(p['new_origin_ue_cm'][2],84.85840868537889)
  self.assertAlmostEqual(p['light_delta_ue_cm'][2]-p['geometry_delta_ue_cm'][2],19.06085650126138)
  self.assertEqual(p['lamp_source_triangle_count'],24102);self.assertFalse(p['native_ready'])
 def test_changed_actual_yaw_refused(self):
  f=self.fixture();f['planned']['DeskLamp']['yaw_deg']=0
  with self.assertRaises(ValueError):mount_plan(ROOT/'web/house/assets/real-linea140/originalsource.glb',ROOT/'web/house/assets/desk_lamp_arm_01/desk_lamp_arm_01.gltf',f)
 def test_missing_collision_proof_refuses_before_editor_access(self):
  class NoEditor:
   def __getattr__(self,n):raise AssertionError('Native accessed before actual source proof '+n)
  with tempfile.TemporaryDirectory()as tmp:
   p=Path(tmp)/'desk.glb';p.write_bytes(place_bytes((ROOT/'web/house/assets/real-linea140/originalsource.glb').read_bytes()))
   p.with_suffix('.json').write_text(json.dumps({'source_sha256':SHA,'output_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'source_binary_unchanged':True}))
   with self.assertRaisesRegex(RuntimeError,'collision proof missing'):run(p,dry_run=False,u=NoEditor())

if __name__=='__main__':unittest.main()
