"""Prevent source review packets from activating unverified controller gameplay."""
import copy,json,struct,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from controller_reference_packet import validate_packet
from unreal_import_reference_controller_candidate import prepare_groups
ROOT=Path(__file__).resolve().parents[1]
class ControllerPacketTests(unittest.TestCase):
 def setUp(self):
  self.frozen=json.loads((ROOT/'docs/proposed/reference-controller-r11-frozen-wip.json').read_text());self.s=self.frozen['source'];self.p=self.frozen['proof']
 def check(self):return validate_packet(self.s,self.p,self.s['held_glb_sha256'],self.s['display_glb_sha256'])
 def test_actual_frozen_wip_keeps_readiness_false(self):self.assertTrue(self.check());self.assertFalse(self.frozen['review']['native_visual_accepted'])
 def test_each_native_or_contact_readiness_flag_is_refused(self):
  for record in ('source','proof'):
   for flag in ('native_imported','hand_contact_accepted','activity_ready'):
    with self.subTest(record=record,flag=flag):
     saved=copy.deepcopy((self.s,self.p));(self.s if record=='source'else self.p)[flag]=True
     with self.assertRaises(ValueError):self.check()
     self.s,self.p=saved
 def test_old_grip_receipts_cannot_be_reused(self):
  self.s['old_contact_proofs_invalidated']=False
  with self.assertRaises(ValueError):self.check()
 def test_half_extent_is_not_full_held_width(self):
  self.p['held']['width_m']/=2
  with self.assertRaises(ValueError):self.check()
 def test_nan_width_is_not_accepted(self):
  self.p['held']['width_m']=float('nan')
  with self.assertRaises(ValueError):self.check()
 def test_changed_actual_export_hash_is_refused(self):
  self.p['held']['sha256']='0'*64
  with self.assertRaises(ValueError):self.check()
 def test_open_repaired_cover_is_refused(self):
  self.p['source_shell_topology'][1]['boundary_edges']=1
  with self.assertRaises(ValueError):self.check()
 def test_missing_surface_primitive_is_refused(self):
  self.p['held']['material_primitives']=5
  with self.assertRaises(ValueError):self.check()
 def test_primitive_split_preserves_every_binary_byte_and_pbr(self):
  d={'asset':{'version':'2.0'},'nodes':[{'name':'Original','mesh':0,'translation':[1,2,3]}],'meshes':[{'primitives':[{'attributes':{'POSITION':0},'indices':1,'material':i}for i in range(6)]}],'materials':[{'name':f'C3M{i:02}','pbrMetallicRoughness':{'baseColorFactor':[i/6,0,0,1]}}for i in range(6)],'buffers':[{'byteLength':8}],'scenes':[{'nodes':[0]}],'scene':0}
  raw=json.dumps(d).encode();raw+=b' '*(-len(raw)%4);binary=b'ABCDEFGH';glb=struct.pack('<III',0x46546c67,2,28+len(raw)+len(binary))+struct.pack('<II',len(raw),0x4e4f534a)+raw+struct.pack('<II',8,0x004e4942)+binary
  with tempfile.TemporaryDirectory()as td:
   source=Path(td)/'original.glb';source.write_bytes(glb);actual,payload=prepare_groups(source,Path(td)/'owned.glb','C11H')
  self.assertEqual(bytes(payload),binary);self.assertEqual(actual['materials'],d['materials']);self.assertEqual([n['translation']for n in actual['nodes']],[[1,2,3]]*6);self.assertEqual([m['primitives'][0]for m in actual['meshes']],d['meshes'][0]['primitives']);self.assertEqual(len({n['name']for n in actual['nodes']}),6)
if __name__=='__main__':unittest.main()
