import json,struct,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from prepare_real_linea140_placement import place_bytes,SCALE

class ExactSourcePlacement(unittest.TestCase):
 def test_authored_binary_and_materials_survive_uniform_placement(self):
  source=Path(__file__).resolve().parents[1]/'web/house/assets/real-linea140/originalsource.glb';raw=source.read_bytes();output=place_bytes(raw)
  a=struct.unpack_from('<I',raw,12)[0];b=struct.unpack_from('<I',output,12)[0]
  self.assertEqual(raw[20+a:],output[20+b:]);old=json.loads(raw[20:20+a]);new=json.loads(output[20:20+b])
  for field in ('accessors','materials','images','bufferViews'):self.assertEqual(old[field],new[field])
  self.assertEqual([m['primitives'] for m in old['meshes']],[m['primitives'] for m in new['meshes']]);self.assertEqual(len({n['name'] for n in new['nodes']}),len(new['nodes']))
  root=new['nodes'][new['scenes'][new.get('scene',0)]['nodes'][0]]
  self.assertEqual(root['children'],old['scenes'][old.get('scene',0)]['nodes']);self.assertEqual(root['translation'],[2.1,.025,-3.02]);self.assertEqual(root['scale'],[SCALE]*3)
  self.assertAlmostEqual(.755*SCALE+.025,.845)
 def test_unreviewed_source_refused(self):
  with self.assertRaises(ValueError):place_bytes(b'glTFchanged')

if __name__=='__main__':unittest.main()
