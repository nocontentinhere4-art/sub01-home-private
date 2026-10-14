"""Preserve source glTF attribute bytes directly in the generated rail GLB.

No Blender/job/renderer required. New rails remain untouched. Only the exact
preserved source node geometry is replaced with referenced original vertices
and surviving original triangle indices, bypassing Blender normal/UV handling.
Writes a NEW GLB/sidecar; strict roundtrip validator must pass before import.
"""
import argparse
import copy
import hashlib
import json
import struct
from pathlib import Path
from home_asset_audit import read_gltf
from structural_rail_source_patch import accessor,world_matrices


def selected_attribute_bytes(doc,binary,index,vertices):
    row=doc['accessors'][index]
    if row.get('sparse'):raise ValueError('Sparse original attributes unsupported')
    sizes={5120:1,5121:1,5122:2,5123:2,5125:4,5126:4};components={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4}
    width=sizes[row['componentType']]*components[row['type']];view=doc['bufferViews'][row['bufferView']]
    stride=view.get('byteStride',width);start=view.get('byteOffset',0)+row.get('byteOffset',0)
    return b''.join(binary[start+v*stride:start+v*stride+width] for v in vertices)


def splice(source,generated,sidecar,output,sidecar_output,remove_reviewed_desk_stem=False):
    report=json.loads(Path(sidecar).read_text())
    if hashlib.sha256(Path(source).read_bytes()).hexdigest()!=report['source_audit']['source_sha256'] or hashlib.sha256(Path(generated).read_bytes()).hexdigest()!=report['output_sha256']:raise ValueError('Actual source/generated identity differs')
    source_doc,source_bin=read_gltf(Path(source));target_doc,target_bin=read_gltf(Path(generated));blob=bytearray(target_bin)
    if len(target_doc.get('buffers',[]))!=1:raise ValueError('Generated GLB must have one binary buffer')
    parents={c:i for i,n in enumerate(target_doc['nodes']) for c in n.get('children',[])}
    if remove_reviewed_desk_stem:
        from desk_lamp_stem_source_patch import select_stem,union_remainder_selection
        stem=select_stem(source_doc,source_bin,report['source_audit']['source_sha256'])
        if stem['triangle_indices']!=list(range(1800,1840)) or stem['selected_triangle_count']!=40:raise ValueError('Reviewed exact legacy stem triangle identity differs')
        union_remainder_selection(report['source_audit']['matched_rails'],stem)
        report['additional_source_removals']=[stem]
    matrices=world_matrices(source_doc);removed={}
    for row in [*report['source_audit']['matched_rails'],*report.get('additional_source_removals',[])]:removed.setdefault((row['source_node_index'],row['primitive_index']),set()).update(row['triangle_indices'])
    proofs=[]
    def append(data,meta,target=None):
        blob.extend(b'\0'*(-len(blob)%4));offset=len(blob);blob.extend(data)
        view={'buffer':0,'byteOffset':offset,'byteLength':len(data)}
        if target:view['target']=target
        view_index=len(target_doc['bufferViews']);target_doc['bufferViews'].append(view)
        definition={k:copy.deepcopy(v) for k,v in meta.items() if k not in ('bufferView','byteOffset','sparse')};definition['bufferView']=view_index
        index=len(target_doc['accessors']);target_doc['accessors'].append(definition);return index
    for remainder in report['scoped_original_mesh_remainder']:
        node_index,primitive_index=remainder['source_node_index'],remainder['primitive_index']
        if node_index!=163 or primitive_index!=0:raise ValueError('Only proven source163/primitive0 remainder may be patched')
        name=f'SUB01_PreservedSource_{node_index}_{primitive_index}';matches=[i for i,n in enumerate(target_doc['nodes']) if n.get('name')==name]
        if len(matches)!=1 or matches[0] in parents:raise ValueError('Exact root-level preserved output node unavailable')
        node=target_doc['nodes'][matches[0]];mesh=target_doc['meshes'][node['mesh']]
        if len(mesh['primitives'])!=1:raise ValueError('Exact output primitive layout unavailable')
        original=source_doc['meshes'][source_doc['nodes'][node_index]['mesh']]['primitives'][primitive_index]
        indices=[v[0] for v in accessor(source_doc,source_bin,original['indices'])]
        surviving=[v for triangle in range(len(indices)//3) if triangle not in removed.get((node_index,primitive_index),set()) for v in indices[triangle*3:triangle*3+3]]
        vertices=sorted(set(surviving));mapping={v:i for i,v in enumerate(vertices)};attributes={};hashes={}
        remainder.update(original_triangle_count=len(indices)//3,removed_rail_triangles=len(removed.get((node_index,primitive_index),set())),preserved_triangle_count=len(surviving)//3,preserved_vertex_count=len(vertices))
        for kind,index in original['attributes'].items():
            data=selected_attribute_bytes(source_doc,source_bin,index,vertices);meta=copy.deepcopy(source_doc['accessors'][index]);meta['count']=len(vertices)
            if 'min' in meta or 'max' in meta:
                values=accessor(source_doc,source_bin,index);components=list(zip(*(values[v] for v in vertices)));meta['min']=[min(c) for c in components];meta['max']=[max(c) for c in components]
            attributes[kind]=append(data,meta,34962);hashes[kind]=hashlib.sha256(data).hexdigest()
        new_indices=[mapping[v] for v in surviving];index_data=struct.pack('<'+'I'*len(new_indices),*new_indices)
        new_primitive={'attributes':attributes,'indices':append(index_data,{'componentType':5125,'type':'SCALAR','count':len(new_indices),'min':[min(new_indices)],'max':[max(new_indices)]},34963),'mode':4,'material':mesh['primitives'][0]['material']}
        mesh['primitives']=[new_primitive]
        for field in ('translation','rotation','scale'):node.pop(field,None)
        node['matrix']=[matrices[node_index][r][c] for c in range(4) for r in range(4)]
        proofs.append({'source_node_index':node_index,'primitive_index':primitive_index,'preserved_triangle_count':len(surviving)//3,'preserved_vertex_count':len(vertices),'exact_original_attribute_byte_sha256':hashes,'original_world_matrix_preserved':True})
    if len(proofs)!=1:raise ValueError('Expected exactly one preserved source163 remainder')
    blob.extend(b'\0'*(-len(blob)%4));target_doc['buffers'][0]['byteLength']=len(blob)
    text=json.dumps(target_doc,separators=(',',':')).encode();text+=b' '*(-len(text)%4)
    result=struct.pack('<4sII',b'glTF',2,12+8+len(text)+8+len(blob))+struct.pack('<II',len(text),0x4E4F534A)+text+struct.pack('<II',len(blob),0x004E4942)+bytes(blob)
    Path(output).write_bytes(result);report['output_sha256']=hashlib.sha256(result).hexdigest();report['source_attribute_byte_splice']=proofs;report['native_acceptance_pending']=True
    Path(sidecar_output).write_text(json.dumps(report,indent=2)+'\n');return {'output':str(output),'sha256':report['output_sha256'],'source_attribute_byte_splice':proofs}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for argument in ('source','generated','sidecar','output','sidecar-output'):parser.add_argument('--'+argument,required=True)
    parser.add_argument('--remove-reviewed-desk-stem',action='store_true',help='Only when exact replacement desk lamp is ready; source-proven one union remainder')
    args=parser.parse_args();print(json.dumps(splice(args.source,args.generated,args.sidecar,args.output,args.sidecar_output,args.remove_reviewed_desk_stem)))
