import struct,unittest
from derive_fp_keyboard_loop import derive,add_midpoint_keys
from fp_arms_clip_tracks import rows


class KeyboardLoopTests(unittest.TestCase):
    def test_original_rows_exact_and_loop_closed(self):
        times=struct.pack('<6f',0.,1.,2.,3.,4.,5.);quats=struct.pack('<24f',*sum(([0.,0.,0.,(-1.)**i]for i in range(6)),[]));binary=times+quats;doc={'nodes':[{'name':'mixamorig:RightHandIndex1'}],'buffers':[{'byteLength':len(binary)}],'bufferViews':[{'byteOffset':0,'byteLength':24},{'byteOffset':24,'byteLength':96}],'accessors':[{'bufferView':0,'componentType':5126,'type':'SCALAR','count':6},{'bufferView':1,'componentType':5126,'type':'VEC4','count':6}],'animations':[{'name':'typing','channels':[{'target':{'node':0,'path':'rotation'},'sampler':0}],'samplers':[{'input':0,'output':1}]}]};out,data,proof=derive(doc,binary,1,4,4,.4);a=out['animations'][0]['samplers'][0]['output'];new=rows(out,data,a);self.assertEqual(new[:4],rows(doc,binary,1)[1:5]);self.assertEqual(new[-1],new[0]);self.assertEqual(data[:len(binary)],binary);self.assertEqual(proof['total_keys'],8)
        for value in new:self.assertAlmostEqual(sum(x*x for x in struct.unpack('<4f',value)),1.,places=6)
        up,updata=add_midpoint_keys(out,data);ua=up['animations'][0]['samplers'][0]['output'];self.assertEqual(rows(up,updata,ua)[::2],new);self.assertEqual(updata[:len(data)],data);self.assertEqual(len(rows(up,updata,ua)),15)
    def test_missing_velocity_neighbor_refuses(self):
        with self.assertRaises(ValueError):derive({},b'',0,2)

if __name__=='__main__':unittest.main()
