import math
import struct
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from structural_rail_source_patch import select,is_exact_cylinder


class BatchedRailSelectionTests(unittest.TestCase):
    def test_batched_source_selects_only_exact_cylinder_and_keeps_other_fixture(self):
        points=[];indices=[]
        for x in (0,2):
            base=len(points)
            points.extend([(x+.013*math.cos(i*math.pi/2),y,.013*math.sin(i*math.pi/2)) for y in (0,.9) for i in range(4)])
            for i in range(4):
                a=base+i;b=base+(i+1)%4;c=base+4+i;d=base+4+(i+1)%4
                indices.extend((a,c,b,b,c,d))
        position_data=b''.join(struct.pack('<fff',*p) for p in points)
        index_data=struct.pack('<'+'I'*len(indices),*indices);binary=position_data+index_data
        doc={'nodes':[{'name':'Mesh_metal_batch','mesh':0}],
             'meshes':[{'primitives':[{'attributes':{'POSITION':0},'indices':1,'material':8}]}],
             'bufferViews':[{'byteOffset':0},{'byteOffset':len(position_data)}],
             'accessors':[{'bufferView':0,'componentType':5126,'type':'VEC3','count':len(points),'min':[-.013,0,-.013],'max':[2.013,.9,.013]},
                          {'bufferView':1,'componentType':5125,'type':'SCALAR','count':len(indices)}]}
        beam={'name':'incline post','a':[0,0,0],'b':[0,.9,0],'radius':.013}
        selected,errors=select(doc,binary,[beam])
        self.assertEqual(errors,[]);self.assertEqual(len(selected),1)
        self.assertEqual(selected[0]['triangle_indices'],list(range(8)))
        self.assertEqual(selected[0]['source_primitive_triangle_count'],16)
        self.assertEqual(selected[0]['selected_triangle_count'],8)
        self.assertFalse(is_exact_cylinder([(0,0,0),(.03,.5,0),(0,.9,0)],beam))
        self.assertFalse(is_exact_cylinder([(0,0,0),(.013,.5,0)],beam))


if __name__=='__main__':unittest.main()
