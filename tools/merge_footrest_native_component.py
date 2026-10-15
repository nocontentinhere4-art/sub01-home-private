"""Pack the proven19-part source into one native component without touching geometry.

This concatenates their primitives and bakes their actual rigid world transforms.
Original buffers, UVs and PBR remain unchanged; float32 position/normal baking is
independently compared to original world data at tight numerical bounds. Editable source
remains19 parts. Only an independently passed physical Idle report supplies placement.
"""
import argparse
import copy
import hashlib
import json
import struct
import math
from pathlib import Path

SOURCE_SHA='d805f7bcc58b919734a966e084d16aa509655f3d7df8c5088efbd6a17d425c50'

def merge(source,fit_report,output):
    from home_asset_audit import read_gltf
    source=Path(source);output=Path(output);report=json.loads(Path(fit_report).read_text())
    if hashlib.sha256(source.read_bytes()).hexdigest()!=SOURCE_SHA or report.get('footrest_sha256')!=SOURCE_SHA:raise ValueError('Exact closed footrest source required')
    if not report.get('source_idle_candidate_pass') or not report.get('readback_all126_main_rule_pass'):raise ValueError('Actual126frame physical Idle proof required')
    for name in ('chair','footrest','desk'):
        row=report.get('collision',{}).get(name,{})
        if row.get('frames_checked')!=126 or row.get('frames_with_penetration') or row.get('minimum_margin_cm',-1)<0:raise ValueError('Physical collision proof missing')
    d,b=read_gltf(source)
    if len(d['nodes'])!=19 or len(d['meshes'])!=19 or d.get('skins') or d.get('animations'):raise ValueError('Exact19 static components required')
    from structural_rail_source_patch import accessor,world_matrices,transformed
    matrices=world_matrices(d);payload=bytearray(b);primitives=[];world_rows=[];normal_rows=[]
    def append_vec3(values):
        payload.extend(b'\0'*(-len(payload)%4));start=len(payload)
        for row in values:payload.extend(struct.pack('<3f',*row))
        view=len(out['bufferViews']);out['bufferViews'].append({'buffer':0,'byteOffset':start,'byteLength':12*len(values),'target':34962})
        ai=len(out['accessors']);out['accessors'].append({'bufferView':view,'componentType':5126,'count':len(values),'type':'VEC3','min':[min(v[k]for v in values)for k in range(3)],'max':[max(v[k]for v in values)for k in range(3)]});return ai
    out=copy.deepcopy(d)
    for i,node in enumerate(d['nodes']):
        if 'children'in node or node.get('mesh')!=i:raise ValueError('Unexpected part hierarchy')
        m=matrices[i]
        # Actual source rotations have unit scale; reject shear/scale rather than
        # silently applying an incorrect normal transform.
        basis=[[m[r][c]for r in range(3)]for c in range(3)]
        if max(abs(sum(a*b for a,b in zip(basis[r],basis[c]))-(1 if r==c else 0))for r in range(3)for c in range(3))>1e-6:raise ValueError('Non-rigid source part')
        def cross(a,b):return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
        rows=[list(m[r][:3])for r in range(3)];cofactor=[cross(rows[1],rows[2]),cross(rows[2],rows[0]),cross(rows[0],rows[1])];det=sum(a*b for a,b in zip(rows[0],cofactor[0]))
        normal_matrix=[[v/det for v in row]for row in cofactor]
        for primitive in d['meshes'][i]['primitives']:
            if set(primitive['attributes'])not in({'POSITION','NORMAL','TEXCOORD_0'},{'POSITION','NORMAL'}):raise ValueError('Unreviewed vertex attribute')
            p=copy.deepcopy(primitive)
            positions=[transformed(m,v)for v in accessor(d,b,primitive['attributes']['POSITION'])]
            normals=[]
            for v in accessor(d,b,primitive['attributes']['NORMAL']):
                n=[sum(normal_matrix[r][c]*v[c]for c in range(3))for r in range(3)];length=math.sqrt(sum(x*x for x in n));normals.append([x/length for x in n])
            p['attributes']['POSITION']=append_vec3(positions);p['attributes']['NORMAL']=append_vec3(normals)
            primitives.append(p);world_rows.append(positions);normal_rows.append(normals)
    delta=report.get('footrest_rigid_delta_ue_cm')
    if not isinstance(delta,list)or len(delta)!=3 or delta[0]!=0 or delta[2]!=0:raise ValueError('Reviewed rigidY placement required')
    translation=[0.,0.,delta[1]/100]
    out['nodes']=[{'name':'SUB01_ReferenceFootrest_OneComponent','mesh':0,'translation':translation}]
    out['meshes']=[{'name':'SUB01_ReferenceFootrest_All19AuthoredParts','primitives':primitives}]
    if len(out.get('scenes',[]))!=1 or sorted(out['scenes'][0]['nodes'])!=list(range(19)):raise ValueError('Unexpected source scene')
    out['scenes'][0]['nodes']=[0]
    for key in('materials','textures','images','samplers'):
        if out.get(key)!=d.get(key):raise AssertionError('Source payload changed '+key)
    out['buffers']=[{'byteLength':len(payload)}];b=bytes(payload)
    j=json.dumps(out,separators=(',',':')).encode();j+=b' '*(-len(j)%4);b=bytes(b);b+=b'\0'*(-len(b)%4)
    output.parent.mkdir(parents=True,exist_ok=True);output.write_bytes(struct.pack('<III',0x46546c67,2,28+len(j)+len(b))+struct.pack('<II',len(j),0x4e4f534a)+j+struct.pack('<II',len(b),0x004e4942)+b)
    actual,actual_b=read_gltf(output)
    if bytes(actual_b)!=b or actual['meshes'][0]['primitives']!=primitives:raise AssertionError('Written source primitive payload changed')
    max_position=max_normal=0.
    for primitive,expected_positions,expected_normals in zip(actual['meshes'][0]['primitives'],world_rows,normal_rows):
        positions=accessor(actual,actual_b,primitive['attributes']['POSITION']);normals=accessor(actual,actual_b,primitive['attributes']['NORMAL'])
        max_position=max(max_position,max(math.dist(a,c)for a,c in zip(positions,expected_positions)))
        max_normal=max(max_normal,max(math.dist(a,c)for a,c in zip(normals,expected_normals)))
    if max_position>2e-7 or max_normal>1e-7:raise ValueError('Baked source geometry differs actual world source')
    proof={'schema':'sub01.reference-footrest-one-component.v1','source_sha256':SOURCE_SHA,'output_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'physical_idle_sha256':report['written_glb_sha256'],'original_parts':19,'native_mesh_components':1,'primitives':len(primitives),'original_buffer_prefix_unchanged':True,'source_indices_uv_pbr_unchanged':True,'position_bake_max_error_m':max_position,'normal_bake_max_error':max_normal,'source_world_rigid_placement_only':translation,'rigid_delta_ue_cm':delta,'editable_source_remains19_parts':True,'native_imported':False,'runtime_ready':False}
    output.with_suffix('.json').write_text(json.dumps(proof,indent=2)+'\n');return proof

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source');p.add_argument('fit_report');p.add_argument('output');a=p.parse_args();print(json.dumps(merge(a.source,a.fit_report,a.output)))
