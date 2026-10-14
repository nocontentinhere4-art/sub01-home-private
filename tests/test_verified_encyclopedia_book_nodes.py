import copy
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as S
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import verified_encyclopedia_book_nodes as provider
import build_real_shelf_books as books


class Identity:
    def __matmul__(self,point):return point


def fixtures():
    contract=[{'name':name,'source_vertex_count':8,'source_triangle_count':4,
               'source_slots':[{'material':provider.MATERIALS[0],'triangles':2,'vertices':4},{'material':provider.MATERIALS[1],'triangles':2,'vertices':4}]} for name in provider.NAMES]
    coordinates=[(x,y,z) for x in (0,.035) for y in (0,.14) for z in (0,.25)]
    objects=[S(name=name,matrix_world=Identity(),data=S(vertices=[S(co=c) for c in coordinates],polygons=[S(vertices=(0,1,2),material_index=slot) for slot in (0,0,1,1)],materials=[S(name=m) for m in provider.MATERIALS])) for name in provider.NAMES]
    return objects,contract


class VerifiedProviderBookTests(unittest.TestCase):
    def test_exact20_whole_objects_preserve_all_source_vertices_and_cover_page_faces(self):
        objects,contract=fixtures()
        verified=provider.verify_objects(objects,contract)
        self.assertEqual(len(verified),20)
        self.assertTrue(all(proof['all_cover_page_triangles_selected'] for obj,proof in verified))
        with patch('verified_encyclopedia_book_nodes.source_contract',return_value=contract),patch.object(books,'islands',side_effect=AssertionError('seam splitting forbidden')),patch.object(books,'cluster_parts',side_effect=AssertionError('generic clustering forbidden')):
            result,ignored=books._measure_books(objects,'-Y',1,'verified.gltf')
        self.assertEqual(ignored,[]);self.assertEqual(len(result),20)
        self.assertTrue(all(book['parts'][0]['verts']==list(range(8)) for book in result))

    def test_extra_name_missing_pages_or_lost_vertices_refuse(self):
        for change in ('name','paper','vertex','material'):
            objects,contract=fixtures()
            if change=='name':objects[0].name+='fake'
            if change=='paper':objects[0].data.polygons.pop()
            if change=='vertex':objects[0].data.vertices.pop()
            if change=='material':objects[0].data.materials.pop()
            with self.assertRaises(ValueError):provider.verify_objects(objects,contract)

    def test_output_mesh_count_proof_and_dimension_gate_remain(self):
        objects,contract=fixtures()
        self.assertEqual(provider.verify_mesh(objects[0].data,contract[0]),[2,2])
        for v in objects[0].data.vertices:v.co=(v.co[0]*100,v.co[1],v.co[2])
        with patch('verified_encyclopedia_book_nodes.source_contract',return_value=contract):
            with self.assertRaises(books.RefusedError):books._measure_books(objects,'-Y',1,'verified.gltf')


if __name__=='__main__':unittest.main()
