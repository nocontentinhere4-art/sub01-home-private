"""Index-only derivative of repaired owner: no new geometry, caps, or skin edits."""
import copy,hashlib,json,struct
from pathlib import Path

OWNER_SHA='831790a62b81e7e2faa5a201e04740d0911c5bfebd49aa03b124808521e3a2b1'


def derive(doc,binary,selections):
    d=copy.deepcopy(doc);data=bytearray(binary);meshes=[];meshmap={};triangles=0
    by_primitive={(r['mesh'],r['primitive']):r for r in selections}
    for mi,mesh in enumerate(doc['meshes']):
        prims=[]
        for pi,prim in enumerate(mesh['primitives']):
            row=by_primitive.get((mi,pi));chosen=[]if row is None else row['kept_source_triangle_ids']
            if not chosen:continue
            if not row['protected_hand_triangles_retained'] or row['non_arm_majority_retained_vertices']:
                raise ValueError('Hand geometry preservation and absence of torso-majority leakage required')
            a=doc['accessors'][prim['indices']];v=doc['bufferViews'][a['bufferView']];assert a['type']=='SCALAR'and a['componentType']in(5123,5125)and not a.get('sparse')
            size={5123:2,5125:4}[a['componentType']];stride=v.get('byteStride',size);offset=v.get('byteOffset',0)+a.get('byteOffset',0)
            assert len(set(chosen))==len(chosen) and chosen==sorted(chosen) and max(chosen)<a['count']//3
            while len(data)%4:data.append(0)
            start=len(data)
            for triangle in chosen:
                for k in range(3):
                    at=offset+(triangle*3+k)*stride;data.extend(binary[at:at+size])
            d['bufferViews'].append({'buffer':0,'byteOffset':start,'byteLength':len(data)-start,'target':34963});d['accessors'].append({'bufferView':len(d['bufferViews'])-1,'componentType':a['componentType'],'count':len(chosen)*3,'type':'SCALAR'})
            fresh=copy.deepcopy(prim);fresh['indices']=len(d['accessors'])-1;prims.append(fresh);triangles+=len(chosen)
        if prims:
            fresh=copy.deepcopy(mesh);fresh['primitives']=prims;meshmap[mi]=len(meshes);meshes.append(fresh)
    for node in d['nodes']:
        if 'mesh'not in node:continue
        if node['mesh']in meshmap:node['mesh']=meshmap[node['mesh']]
        else:node.pop('mesh');node.pop('skin',None)
    if len(meshes)!=1:raise ValueError('Unique authentic source arm mesh expected')
    d['meshes']=meshes;d['buffers'][0]['byteLength']=len(data)
    for name in ['skins','materials','textures','images','animations']:
        assert d.get(name)==doc.get(name)
    for old,new in zip(doc['nodes'],d['nodes']):
        assert {k:v for k,v in old.items()if k not in('mesh','skin')}=={k:v for k,v in new.items()if k not in('mesh','skin')}
    assert bytes(data[:len(binary)])==binary
    return d,bytes(data),{'triangles':triangles,'mesh_components':1,'source_binary_prefix_exact':True,'positions_normals_tangents_uv_skin_weight_accessors_exact':True,'all65_joints_and_IBMs_exact':True,'all_rest_TRS_and_hierarchy_exact':True,'all_captured_animation_values_exact':True,'materials_textures_images_exact':True,'new_geometry_or_cap_triangles':0,'source_ready':False,'native_ready':False}
