"""Authentic threaded component motion preserves every other source attribute."""
import sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tools'))
from real_linea_edge_clamp import mount_plan,source_mechanics
from home_asset_audit import read_gltf
from structural_rail_source_patch import accessor

class EdgeClamp(unittest.TestCase):
 def test_real_measured_opening_and_only_rigid_screw_moves(self):
  lamp=ROOT/'web/house/assets/desk_lamp_arm_01/desk_lamp_arm_01.gltf'
  saved={'planned':{'DeskLamp':{'yaw_deg':90,'location_cm':[92.32936859130861,-314.5301260612905,84.49999491373697],'bulb_cm':[110,-315,154.06085650126138],'light_cm':[110,-315,135],'actor':'exact-reviewed','materials':[{'material':'body'},{'material':'light'}]}}}
  doc,rows,selected,upper,lower,caps=source_mechanics(lamp)
  with tempfile.TemporaryDirectory()as tmp:
   output=Path(tmp)/'lamp-posed.glb';plan=mount_plan(ROOT/'web/house/assets/real-linea140/originalsource.glb',lamp,saved,output)
   self.assertAlmostEqual(plan['actual_closed_opening_m'],.020573013607645407,places=8)
   delta=plan['posed_lamp']['rigid_screw_delta_local_y_m'];self.assertAlmostEqual(delta,-.009857579311508415,places=7)
   self.assertGreater(plan['actual_jaw_support']['actual_flat_wood_contact_fraction'],.89);self.assertLess(plan['actual_jaw_support']['actual_flat_wood_contact_fraction'],.90)
   self.assertEqual(plan['opened_hardware_source_nodes'],[]);self.assertEqual(plan['preserved_grommet_source_nodes'],[7,8,35])
   self.assertAlmostEqual(upper-(lower+delta),plan['wood_thickness_m']+.00002,places=9)
   old,oldbin=read_gltf(lamp);oldbin=(lamp.parent/old['buffers'][0]['uri']).read_bytes();new,newbin=read_gltf(output)
   for primitive_index,(a,b)in enumerate(zip(old['meshes'][0]['primitives'],new['meshes'][0]['primitives'])):
    self.assertEqual(a,b)
    for name,index in a['attributes'].items():
     original=accessor(old,oldbin,index);posed=accessor(new,newbin,index)
     for vertex,(x,y)in enumerate(zip(original,posed)):
      if name=='POSITION'and primitive_index==0 and vertex in selected:
       self.assertEqual(x[0],y[0]);self.assertEqual(x[2],y[2]);self.assertAlmostEqual(y[1]-x[1],delta,places=7)
      else:self.assertEqual(x,y)
    self.assertEqual(accessor(old,oldbin,a['indices']),accessor(new,newbin,b['indices']))
   self.assertEqual(old['materials'],new['materials']);self.assertEqual(len(caps),len(plan['screw_contact_triangle_ids']))
 def test_unreviewed_source_refused(self):
  with tempfile.TemporaryDirectory()as tmp:
   p=Path(tmp)/'lamp.gltf';p.write_text('{}')
   with self.assertRaisesRegex(ValueError,'Unreviewed'):source_mechanics(p)
if __name__=='__main__':unittest.main()
