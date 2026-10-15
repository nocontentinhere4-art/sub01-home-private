import hashlib
import itertools
import json
import struct
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from prepare_frame_backing_remainder import read,elements
from unreal_remove_frame_backings import same_triangles,SHA


class RemainderTests(unittest.TestCase):
    def test_actual_source_transfer_preserves_door_frame_and_nightstand_only(self):
        folder=ROOT/'docs/proposed/generated-frame-backings';raw=(folder/'remainder.glb').read_bytes();proof=json.loads((folder/'remainder.json').read_text())
        self.assertEqual(hashlib.sha256(raw).hexdigest(),SHA)
        self.assertEqual(proof['removed_triangles'],list(range(600)))
        self.assertEqual(proof['preserved_triangles'],list(range(600,1200)))
        doc,blob=read(raw);p=doc['meshes'][0]['primitives'][0]
        ids,fmt=elements(doc,blob,p['indices']);self.assertEqual(len(ids)//3,600)
        for name,index in p['attributes'].items():
            data,_=elements(doc,blob,index)
            self.assertEqual(hashlib.sha256(b''.join(data)).hexdigest(),proof['retained_attribute_sha256'][name])
        points,fmt=elements(doc,blob,p['attributes']['POSITION']);points=[struct.unpack(fmt,v)for v in points]
        self.assertLess(max(v[0]for v in points),-2.13)
        self.assertGreater(min(v[2]for v in points),.53)

    def test_matcher_handles_reordering_and_tight_duplicate_faces_without_discarding(self):
        a=[[0.,0.,0.],[1.,0.,0.],[0.,1.,0.]]
        b=[[x,y,z+.0005]for x,y,z in a]
        self.assertTrue(same_triangles([a,b],[list(reversed(b)),list(reversed(a))]))
        self.assertFalse(same_triangles([a,b],[a]))
        self.assertFalse(same_triangles([a],[[[x,y,z+.002]for x,y,z in a]]))


if __name__=='__main__':unittest.main()
