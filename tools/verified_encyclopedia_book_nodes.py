"""Read-only authored per-book boundaries for the exact verified CC0 asset.

No mesh welding, vertex deletion or geometry edits. All source cover/page
triangles, material slots and vertices must survive import before fastpath use.
"""
import hashlib
import json
from pathlib import Path

GLTF_SHA='89eb80fffd619ebbe5043d632bd8cf25b2d68a3614aee2f356e850c69ae498ba'
BIN_SHA='bbc726698b6e40ab5537b73e082f7bb4db97b9e6f978f52cdaf763dddc85d9ba'
NAMES=tuple(f'book_encyclopedia_set_01_book{i:02d}' for i in range(1,21))
MATERIALS=('book_encyclopedia_set_01_cover','book_encyclopedia_set_01_paper')


def source_contract(path):
    if path is None:return None
    path=Path(path)
    if path.suffix.lower()!='.gltf':return None
    raw=path.read_bytes();digest=hashlib.sha256(raw).hexdigest()
    if digest!=GLTF_SHA:
        if path.name=='book_encyclopedia_set_01_1k.gltf':raise ValueError('Verified provider GLTF bytes changed')
        return None
    doc=json.loads(raw)
    if len(doc.get('nodes',[]))!=20 or len(doc.get('meshes',[]))!=20 or set(n.get('name') for n in doc['nodes'])!=set(NAMES) or len({n.get('mesh') for n in doc['nodes']})!=20:raise ValueError('Verified authored20-book node/mesh contract differs')
    if len(doc.get('buffers',[]))!=1 or doc['buffers'][0].get('uri')!='book_encyclopedia_set_01.bin':raise ValueError('Verified provider binary identity differs')
    if hashlib.sha256((path.parent/doc['buffers'][0]['uri']).read_bytes()).hexdigest()!=BIN_SHA:raise ValueError('Verified provider binary bytes changed')
    contract=[]
    for node in sorted(doc['nodes'],key=lambda n:n['name']):
        primitives=doc['meshes'][node['mesh']]['primitives']
        if len(primitives)!=2:raise ValueError('Provider book must contain complete cover+paper primitives')
        slots=[]
        for primitive in primitives:
            if primitive.get('mode',4)!=4:raise ValueError('Provider book source primitive is not triangles')
            count=doc['accessors'][primitive['indices']]['count']
            if count%3:raise ValueError('Provider book source triangle index count differs')
            slots.append({'material':doc['materials'][primitive['material']]['name'],'triangles':count//3,'vertices':doc['accessors'][primitive['attributes']['POSITION']]['count']})
        if tuple(s['material'] for s in slots)!=MATERIALS:raise ValueError('Provider cover/page material identity differs')
        contract.append({'name':node['name'],'source_vertex_count':sum(s['vertices'] for s in slots),'source_triangle_count':sum(s['triangles'] for s in slots),'source_slots':slots,'gltf_sha256':GLTF_SHA,'binary_sha256':BIN_SHA})
    return contract


def verify_objects(meshes,contract):
    if len(meshes)!=20 or {o.name for o in meshes}!=set(NAMES):raise ValueError('Actual imported provider book objects must be exactly20 unique authored nodes')
    lookup={o.name:o for o in meshes};result=[]
    for expected in contract:
        obj=lookup[expected['name']];mesh=obj.data
        counts=verify_mesh(mesh,expected)
        result.append((obj,dict(expected,actual_vertex_count=len(mesh.vertices),actual_triangles_per_slot=counts,all_vertices_selected=True,all_cover_page_triangles_selected=True)))
    return result


def verify_mesh(mesh,expected):
    if len(mesh.vertices)!=expected['source_vertex_count']:raise ValueError(expected['name']+': full source vertex count differs')
    if len(mesh.materials)!=2 or tuple(m.name if m else None for m in mesh.materials)!=MATERIALS:raise ValueError(expected['name']+': full cover/page material slots differ')
    counts=[0,0]
    for polygon in mesh.polygons:
        if len(polygon.vertices)!=3 or polygon.material_index not in (0,1):raise ValueError(expected['name']+': actual full source triangle layout differs')
        counts[polygon.material_index]+=1
    if counts!=[s['triangles'] for s in expected['source_slots']]:raise ValueError(expected['name']+': complete source cover/page triangle counts differ')
    return counts
