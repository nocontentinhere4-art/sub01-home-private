import math
import json,struct
from pathlib import Path
import unittest
from shorten_upright_getup_start import slerp,derive

class QuaternionBridge(unittest.TestCase):
    def test_sign_equivalent_endpoints_have_no_spin(self):
        q=(0.,0.,0.,1.)
        for u in (.1,.5,.9):self.assertEqual(slerp(q,tuple(-x for x in q),u),[0.,0.,0.,1.])
    def test_shortest_arc_and_exact_endpoint_bytes(self):
        a=(0.,0.,0.,1.);b=(0.,0.,math.sin(.3),math.cos(.3))
        self.assertIs(slerp(a,b,0),a);self.assertIs(slerp(a,b,1),b)
        q=slerp(a,b,.5);self.assertAlmostEqual(q[2],math.sin(.15));self.assertAlmostEqual(sum(x*x for x in q),1.)

class ActualPassedSource(unittest.TestCase):
    def test_every_retained_key_and_original_binary_are_exact(self):
        path=Path(__file__).resolve().parents[1]/'docs/proposed/upright-footrest-source/SUB01_GetUp_upright_footrest_DerivedReverse.glb'
        raw=path.read_bytes();size=struct.unpack_from('<I',raw,12)[0];doc=json.loads(raw[20:20+size]);binary=raw[28+size:]
        fresh,data,report=derive(doc,binary)
        self.assertEqual(data[:len(binary)],binary);self.assertEqual(fresh['nodes'],doc['nodes'])
        def rows(d,b,ai):
            a=d['accessors'][ai];v=d['bufferViews'][a['bufferView']];n={'SCALAR':1,'VEC3':3,'VEC4':4}[a['type']];size=n*4;o=v.get('byteOffset',0)+a.get('byteOffset',0);stride=v.get('byteStride',size)
            return [b[o+i*stride:o+i*stride+size]for i in range(a['count'])]
        for old,new in zip(doc['animations'][0]['samplers'],fresh['animations'][0]['samplers']):
            a=rows(doc,binary,old['output']);b=rows(fresh,data,new['output'])
            self.assertEqual(b[0],a[0]);self.assertEqual(b[6:],a[27:])
            self.assertEqual(len(b),47)
        self.assertEqual(report['geometry_and_main_support_pass'],False)

if __name__=='__main__':unittest.main()
