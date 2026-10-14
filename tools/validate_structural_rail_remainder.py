"""Independent byte-level GLB roundtrip check before original batched actor hide.

Reads source + actual export + sidecar. Compares every nonrail triangle's world
positions, normals and UV (cyclic vertex order allowed, reverse winding refused).
No Blender, Unreal, source mutations, or acceptance from construction assertions.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
from home_asset_audit import read_gltf
from structural_rail_source_patch import accessor,world_matrices,transformed

POSITION_TOLERANCE=1e-5
ATTRIBUTE_TOLERANCE=2e-5


def normal_matrix(matrix):
    a,b,c=matrix[0][:3];d,e,f=matrix[1][:3];g,h,i=matrix[2][:3]
    determinant=a*(e*i-f*h)-b*(d*i-f*g)+c*(d*h-e*g)
    if abs(determinant)<1e-12:raise ValueError('Singular source normal transform')
    return [[(e*i-f*h)/determinant,(f*g-d*i)/determinant,(d*h-e*g)/determinant],
            [(c*h-b*i)/determinant,(a*i-c*g)/determinant,(b*g-a*h)/determinant],
            [(b*f-c*e)/determinant,(c*d-a*f)/determinant,(a*e-b*d)/determinant]]


def triangle_stream(doc,binary,node_index,primitive_index,excluded=()):
    matrix=world_matrices(doc)[node_index];primitive=doc['meshes'][doc['nodes'][node_index]['mesh']]['primitives'][primitive_index]
    positions=accessor(doc,binary,primitive['attributes']['POSITION']);indices=[v[0] for v in accessor(doc,binary,primitive['indices'])] if 'indices' in primitive else list(range(len(positions)))
    normals=accessor(doc,binary,primitive['attributes']['NORMAL']) if 'NORMAL' in primitive['attributes'] else None
    uvs=accessor(doc,binary,primitive['attributes']['TEXCOORD_0']) if 'TEXCOORD_0' in primitive['attributes'] else None
    transform=normal_matrix(matrix)
    def vertex(index):
        position=transformed(matrix,positions[index]);normal=None
        if normals is not None:
            raw=tuple(sum(transform[r][c]*normals[index][c] for c in range(3)) for r in range(3));length=math.sqrt(sum(v*v for v in raw))
            if length<=0:raise ValueError('Source/output normal has zero length')
            normal=tuple(v/length for v in raw)
        return {'position':position,'normal':normal,'uv':uvs[index] if uvs is not None else None}
    return [tuple(vertex(i) for i in indices[j*3:j*3+3]) for j in range(len(indices)//3) if j not in excluded],primitive


def position_key(triangle):
    return tuple(sorted(tuple(round(c,4) for c in v['position']) for v in triangle))


def compare_triangles(expected,actual):
    if len(expected)!=len(actual):return {'ok':False,'error':'triangle count differs','expected':len(expected),'actual':len(actual)}
    buckets={}
    for triangle in actual:buckets.setdefault(position_key(triangle),[]).append(triangle)
    maxima={'position':0.,'normal':0.,'uv':0.}
    for triangle in expected:
        key=position_key(triangle);candidates=buckets.get(key,[]);found=None
        for candidate_index,candidate in enumerate(candidates):
            for shift in range(3):
                deltas={};valid=True
                for kind,tolerance in (('position',POSITION_TOLERANCE),('normal',ATTRIBUTE_TOLERANCE),('uv',ATTRIBUTE_TOLERANCE)):
                    differences=[]
                    for j in range(3):
                        a,b=triangle[j][kind],candidate[(j+shift)%3][kind]
                        if (a is None)!=(b is None):valid=False;break
                        if a is not None:differences.extend(abs(x-y) for x,y in zip(a,b))
                    delta=max(differences,default=0);deltas[kind]=delta
                    if delta>tolerance:valid=False
                if valid:found=(candidate_index,deltas);break
            if found:break
        if found is None:return {'ok':False,'error':'nonrail triangle position/normal/UV/winding differs','position_key':key,'candidate_count':len(candidates)}
        candidates.pop(found[0])
        for kind,delta in found[1].items():maxima[kind]=max(maxima[kind],delta)
    return {'ok':True,'triangle_count':len(expected),'max_absolute_difference':maxima}


def validate(source,replacement,sidecar):
    report=json.loads(Path(sidecar).read_text());source_hash=hashlib.sha256(Path(source).read_bytes()).hexdigest();replacement_hash=hashlib.sha256(Path(replacement).read_bytes()).hexdigest()
    if source_hash!=report['source_audit']['source_sha256'] or replacement_hash!=report['output_sha256']:raise ValueError('Actual source/export bytes differ from audited identity')
    original,original_bin=read_gltf(Path(source));output,output_bin=read_gltf(Path(replacement));checks=[]
    selected={}
    for row in report['source_audit']['matched_rails']:selected.setdefault((row['source_node_index'],row['primitive_index']),set()).update(row['triangle_indices'])
    for remainder in report['scoped_original_mesh_remainder']:
        source_node,source_primitive=remainder['source_node_index'],remainder['primitive_index'];name=f'SUB01_PreservedSource_{source_node}_{source_primitive}'
        nodes=[i for i,n in enumerate(output['nodes']) if n.get('name')==name]
        if len(nodes)!=1:checks.append({'mesh':name,'ok':False,'error':'exact exported preserved node missing or duplicate'});continue
        primitives=output['meshes'][output['nodes'][nodes[0]]['mesh']]['primitives']
        if len(primitives)!=1:checks.append({'mesh':name,'ok':False,'error':'preserved primitive layout differs'});continue
        expected,source_prim=triangle_stream(original,original_bin,source_node,source_primitive,selected.get((source_node,source_primitive),set()))
        actual,output_prim=triangle_stream(output,output_bin,nodes[0],0)
        result=compare_triangles(expected,actual);result['mesh']=name
        src=original['materials'][source_prim['material']].get('pbrMetallicRoughness',{});dst=output['materials'][output_prim['material']].get('pbrMetallicRoughness',{})
        factors={}
        for key,default in (('baseColorFactor',[1,1,1,1]),('roughnessFactor',1),('metallicFactor',1)):
            a,b=src.get(key,default),dst.get(key,default);delta=max(abs(x-y) for x,y in zip(a,b)) if isinstance(a,list) else abs(a-b);factors[key]=delta
        result['material_factor_max_differences']=factors
        if max(factors.values())>ATTRIBUTE_TOLERANCE:result.update(ok=False,error='Preserved original material PBR factors differ')
        checks.append(result)
    return {'schema':'sub01-private-structural-remainder-roundtrip-v1','read_only':True,'source_sha256':source_hash,'replacement_sha256':replacement_hash,'position_tolerance_m':POSITION_TOLERANCE,'normal_uv_factor_tolerance':ATTRIBUTE_TOLERANCE,'checks':checks,'ok':bool(checks) and all(r['ok'] for r in checks),'native_acceptance_pending':True}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--source',required=True);parser.add_argument('--replacement',required=True);parser.add_argument('--sidecar',required=True);parser.add_argument('--output',required=True);args=parser.parse_args()
    result=validate(args.source,args.replacement,args.sidecar);Path(args.output).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));raise SystemExit(0 if result['ok'] else 2)
