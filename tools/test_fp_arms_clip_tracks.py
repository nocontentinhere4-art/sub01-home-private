import copy,struct,unittest
from fp_arms_clip_tracks import restore_unchanged_rotations


def fixture():
    binary=struct.pack('<2f',0.,1.)+struct.pack('<8f',0.,0.,0.,-1.,0.,0.,0.,1.)+struct.pack('<8f',0.,0.,0.,1.,0.,0.,0.,-1.)
    doc={'nodes':[{'name':'mixamorig:RightHandIndex1'},{'name':'mixamorig:RightArm'}],'bufferViews':[{'byteOffset':0},{'byteOffset':8},{'byteOffset':40}],'accessors':[{'bufferView':0,'componentType':5126,'type':'SCALAR','count':2},{'bufferView':1,'componentType':5126,'type':'VEC4','count':2},{'bufferView':2,'componentType':5126,'type':'VEC4','count':2}],'animations':[{'name':'typing','channels':[{'target':{'node':0,'path':'rotation'},'sampler':0},{'target':{'node':1,'path':'rotation'},'sampler':1}],'samplers':[{'input':0,'output':1},{'input':0,'output':2}]}]}
    return doc,binary


class CapturedTrackTests(unittest.TestCase):
    def test_captured_finger_sign_bytes_restored_arm_derivative_retained(self):
        source,binary=fixture();target=copy.deepcopy(source);data=bytearray(binary);data[8:]=bytes(64)
        out,names=restore_unchanged_rotations(source,binary,target,data,{'RightArm'})
        self.assertEqual(out[8:40],binary[8:40]);self.assertEqual(out[40:],bytes(32));self.assertEqual(names,['RightHandIndex1']);self.assertEqual(binary,fixture()[1])
    def test_time_mismatch_refuses(self):
        source,binary=fixture();target=copy.deepcopy(source);data=bytearray(binary);struct.pack_into('<f',data,4,1.1)
        with self.assertRaisesRegex(ValueError,'times differ'):restore_unchanged_rotations(source,binary,target,data,{'RightArm'})
    def test_count_mismatch_refuses(self):
        source,binary=fixture();target=copy.deepcopy(source);target['accessors'][1]['count']=1
        with self.assertRaisesRegex(ValueError,'shape differs'):restore_unchanged_rotations(source,binary,target,binary,{'RightArm'})

if __name__=='__main__':unittest.main()
