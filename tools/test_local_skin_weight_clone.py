import struct
import unittest
from write_local_skin_weight_clone import patch

class SparseSkinPatchTest(unittest.TestCase):
    def test_interleaved_slots_and_unlisted_vertices_are_exact(self):
        doc={'meshes':[{'primitives':[{'attributes':{'JOINTS_0':0,'WEIGHTS_0':1}}]}],'accessors':[{'type':'VEC4','bufferView':0,'componentType':5121,'count':2},{'type':'VEC4','bufferView':0,'componentType':5121,'normalized':True,'byteOffset':4,'count':2}],'bufferViews':[{'buffer':0,'byteOffset':8,'byteStride':16}]}
        raw=b'PREFIX!!'+bytes([1,2,3,4,128,127,0,0])+b'GEOMETRY'+bytes([5,6,7,8,255,0,0,0])+b'PROTECT!'
        rows=[{'mesh':0,'primitive':0,'vertices':[{'id':1,'new_joints':[9,8,7,6],'new_weights':[.4,.3,.2,.1]}]}]
        out,proof=patch(doc,raw,rows)
        self.assertEqual(out[:24],raw[:24]);self.assertEqual(out[32:],raw[32:]);self.assertEqual(sum(out[28:32]),255);self.assertEqual(out[24:28],bytes([9,8,7,6]));self.assertTrue(proof['all_unlisted_bytes_exact'])
    def test_no_patch_retains_every_byte(self):
        raw=bytes(range(255));self.assertEqual(patch({},raw,[])[0],raw)

if __name__=='__main__':unittest.main()
