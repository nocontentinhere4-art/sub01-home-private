"""Blender-only actual source verification, byte-preserving full-world GLB placement.

Run on same authorized pod: blender -b --python tools/prepare_real_linea140_placement.py --
--source source-candidates/linea140/source.glb --output out/real-linea140/desk.glb
No scene/runtime mutation, no new furniture geometry, no Blender re-encoding of PBR.
"""
import argparse,copy,hashlib,json,math,struct,sys
from pathlib import Path
from real_furniture_base import glb_json,sha256_file
SHA='99bdf3fd42eea5fc4cb2fadd52c8cae18c4459a94000b85f7df4c515234ba43d'
SCALE=(.845-.025)/.755


def place_bytes(raw):
    if hashlib.sha256(raw).hexdigest()!=SHA:raise ValueError('Unreviewed desk source bytes')
    length,kind=struct.unpack_from('<II',raw,12)
    if kind!=0x4E4F534A:raise ValueError('GLB JSON missing')
    doc=json.loads(raw[20:20+length]);rest=raw[20+length:]
    if len(doc['materials'])!=7 or len(doc['images'])!=6:raise ValueError('Complete original PBR contract differs')
    primitives=[p for m in doc['meshes'] for p in m['primitives']]
    if len(primitives)!=60 or sum(doc['accessors'][p['indices']]['count']//3 for p in primitives)!=20024:raise ValueError('Complete60 primitive/20024 triangle contract differs')
    for i,node in enumerate(doc['nodes']):node['name']=f'SUB01_RealLinea140_99bdf3fd_Node{i:03d}'
    for i,mesh in enumerate(doc['meshes']):mesh['name']=f'SUB01_RealLinea140_99bdf3fd_Mesh{i:03d}'
    scene=doc['scenes'][doc.get('scene',0)];children=scene['nodes'];root=len(doc['nodes'])
    doc['nodes'].append({'name':'SUB01_RealLinea140_Complete_99bdf3fd','children':children,'translation':[2.1,.025,-3.1],'scale':[SCALE]*3})
    scene['nodes']=[root];scene['name']='SUB01_RealLinea140_WorldPlacement'
    encoded=json.dumps(doc,separators=(',',':')).encode();encoded+=b' '*(-len(encoded)%4)
    return struct.pack('<4sII',b'glTF',2,20+len(encoded)+len(rest))+struct.pack('<II',len(encoded),0x4E4F534A)+encoded+rest


def run(source,output,lamp_source=None,lamp_receipt=None,home_source=None):
    import bpy
    from mathutils import Matrix,Vector
    source=Path(source);output=Path(output)
    if sha256_file(source)!=SHA:raise ValueError('Actual source hash differs')
    # Sole bounded CPU source job; no existing .blend or home geometry is opened.
    if bpy.data.filepath or any(o.type=='MESH' and o.name not in {'Cube'} for o in bpy.data.objects):raise ValueError('Require fresh Blender source-only scene, not the home')
    original=set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(source),merge_vertices=False)
    added=[o for o in bpy.data.objects if o not in original];meshes=[o for o in added if o.type=='MESH']
    if sum(len(o.data.polygons) for o in meshes)!=20024:raise ValueError('Actual Blender import lost source triangles')
    materials={m for o in meshes for m in o.data.materials if m}
    if len(materials)!=7:raise ValueError('Actual Blender import lost materials')
    vertices=[o.matrix_world@v.co for o in meshes for v in o.data.vertices]
    lo=[min(v[a] for v in vertices) for a in range(3)];hi=[max(v[a] for v in vertices) for a in range(3)]
    expected_dims=[1.4,.65,.7582999824]
    if any(abs(hi[a]-lo[a]-expected_dims[a])>.0001 for a in range(3)):raise ValueError('Actual source Blender axes/dimensions differ')
    raw=source.read_bytes();placed=place_bytes(raw);output.parent.mkdir(parents=True,exist_ok=True);output.write_bytes(placed)
    from inventory_cc0_desk_candidate import inventory
    result=inventory(output);doc=glb_json(output);source_doc=glb_json(source)
    if result['dimensions_m']!=[d*SCALE for d in inventory(source)['dimensions_m']]:
        expected=[d*SCALE for d in inventory(source)['dimensions_m']]
        if any(abs(a-b)>1e-8 for a,b in zip(result['dimensions_m'],expected)):raise ValueError('Export actual bounds differ')
    if [m['primitives'] for m in doc['meshes']] != [m['primitives'] for m in source_doc['meshes']]:raise ValueError('Source mesh primitive attributes changed')
    for key in ('accessors','bufferViews','materials','textures','images','samplers','buffers'):
        if doc.get(key)!=source_doc.get(key):raise ValueError('Original source '+key+' changed')
    length=struct.unpack_from('<I',raw,12)[0];outlength=struct.unpack_from('<I',placed,12)[0]
    if raw[20+length:]!=placed[20+outlength:]:raise ValueError('Original binary geometry/texture bytes changed')
    top_bounds=[[2.1-.699*SCALE,-3.1-.325*SCALE],[2.1+.699*SCALE,-3.1+.325*SCALE]]
    device_bounds={'monitor':[[1.64,-3.345],[2.36,-3.255]],'keyboard':[[1.8145,-3.020465],[2.1855,-2.859535]],'mouse':[[2.29,-3.014501],[2.510001,-2.8055]],'phone':[[2.661,-2.995001],[2.739001,-2.845]]}
    margins={name:min([box[0][a]-top_bounds[0][a] for a in range(2)]+[top_bounds[1][a]-box[1][a] for a in range(2)]) for name,box in device_bounds.items()}
    if min(margins.values())<=0:raise ValueError('Source device support envelope outside exported actual top')
    report={'schema':'sub01.real-linea140-placement-export.v1','source_sha256':SHA,'output_sha256':sha256_file(output),'output_bytes':output.stat().st_size,'blender_import_meshes':len(meshes),'source_triangle_count':20024,'all60_source_primitives_preserved':True,'all7_materials_6_embedded_images_binary_exact':True,'source_binary_unchanged':True,'uniform_scale':SCALE,'actual_export_bounds_m':result['bounds_m'],'actual_export_dimensions_m':result['dimensions_m'],'top_world_height_m':.845,'device_xy_support_margins_m':margins,'hide_only_source_actor_nodes':[181,182],'lamp_mount_plan_required':True,'opened_grommet_cap_source_node':8,'expected_actor_nodes':{str(i):n['name'] for i,n in enumerate(doc['nodes']) if 'mesh' in n},'lamp_delta_ue_cm':None,'lamp_delta_status':'SEPARATE_REVIEWED_FIXTURE_AND_LIGHT_MOVE_NOT_APPLIED','not_a_native_import_receipt':True,'native_acceptance_required':['Floor is actually2.5cm','Device foot contact and functional screen bindings remain unchanged','Chair/knee collision and lamp full bounds checked before exact olddesk hide']}
    if lamp_source and lamp_receipt and home_source:
        from real_linea_lamp_mount import mount_plan,blender_collision_proof
        mount=mount_plan(source,lamp_source,json.loads(Path(lamp_receipt).read_text()))
        mount['collision_proof']=blender_collision_proof(source,lamp_source,mount,home_source)
        report['lamp_mount']=mount
        if not mount['collision_proof']['ok']:raise ValueError('Actual lamp/desk/home collision proof failed '+json.dumps(mount['collision_proof']))
    output.with_suffix('.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report));return report

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source',required=True);parser.add_argument('--output',required=True)
    parser.add_argument('--lamp-source');parser.add_argument('--lamp-receipt');parser.add_argument('--home-source')
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else None);run(args.source,args.output,args.lamp_source,args.lamp_receipt,args.home_source)
