import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from validate_structural_rail_remainder import compare_triangles,normal_matrix


class ExportedRemainderTests(unittest.TestCase):
    def triangle(self):
        return tuple({'position':p,'normal':(0,0,1),'uv':uv} for p,uv in zip(((0,0,0),(1,0,0),(0,1,0)),((0,0),(1,0),(0,1))))

    def test_order_and_vertex_splits_do_not_hide_changed_geometry_normals_uv_or_winding(self):
        expected=self.triangle();rotated=expected[1:]+expected[:1]
        self.assertTrue(compare_triangles([expected],[rotated])['ok'])
        self.assertFalse(compare_triangles([expected],[(expected[0],expected[2],expected[1])])['ok'])
        for kind,value in (('position',(0.0001,0,0)),('normal',(0,.01,1)),('uv',(.01,0))):
            actual=copy.deepcopy(expected);actual[0][kind]=value
            self.assertFalse(compare_triangles([expected],[actual])['ok'],kind)
        self.assertFalse(compare_triangles([expected],[])['ok'])

    def test_inverse_transpose_normal_transform(self):
        result=normal_matrix([[2,0,0,0],[0,3,0,0],[0,0,4,0],[0,0,0,1]])
        self.assertEqual(result,[[.5,0,0],[0,1/3,0],[0,0,.25]])


if __name__=='__main__':unittest.main()
