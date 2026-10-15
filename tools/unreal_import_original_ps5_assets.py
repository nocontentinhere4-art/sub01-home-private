"""Complete original DatSketch PS5 assets only. No existing device/world assignment.

Only technical names and an external uniform unit/root frame change; original
24 mesh primitives,13 PBRs, binary and hierarchy remain recoverable unchanged.
"""
import copy,hashlib,json,struct,time,uuid
from pathlib import Path
ROOT=Path('/workspace/sub01-home-private/ps5-datsketch-original-r1')
SHA='cbe651c6e8064eaba6da3fb0aa8c9b9ad616eaa02fd4ef3821c86b64d8ed94b9'
UNIT=.001200652897522776
STAND_NODE=18

def contract(doc):
 assert len(doc['nodes'])==42 and len(doc['meshes'])==24 and len(doc['materials'])==13 and not doc.get('images')
 assert doc['asset']['extras']['author']=='DatSketch (https://sketchfab.com/DatSketch)'
 assert doc['asset']['extras']['source']=='https://sketchfab.com/3d-models/playstation-5-digital-edition-ea891a5332934095a5c6407b3b14b296'
 mesh_nodes={i:n for i,n in enumerate(doc['nodes'])if 'mesh'in n}
 assert len(mesh_nodes)==24 and {n['mesh']for n in mesh_nodes.values()}==set(range(24))
 assert doc['nodes'][STAND_NODE]['mesh']==8 and doc['nodes'][STAND_NODE]['name']=='PS STAND_PS Stand_0'
 assert doc['materials'][6]['name']=='PS_Stand'
 for n in mesh_nodes.values():assert len(doc['meshes'][n['mesh']]['primitives'])==1
 assert sum(doc['accessors'][p['indices']]['count']//3 for m in doc['meshes']for p in m['primitives'])==37707
 return mesh_nodes

def prepare_names(source,target):
 from home_asset_audit import read_gltf
 doc,blob=read_gltf(Path(source));contract(doc);out=copy.deepcopy(doc)
 for i,n in enumerate(out['nodes']):n['name']=f'PS5N{i:03}'
 for i,m in enumerate(out['meshes']):m['name']=f'PS5M{i:03}'
 text=json.dumps(out,separators=(',',':')).encode();text+=b' '*(-len(text)%4);data=bytes(blob);data+=b'\0'*(-len(data)%4)
 target=Path(target);target.parent.mkdir(parents=True,exist_ok=True);assert not target.exists()
 target.write_bytes(struct.pack('<III',0x46546c67,2,28+len(text)+len(data))+struct.pack('<II',len(text),0x4e4f534a)+text+struct.pack('<II',len(data),0x004e4942)+data)
 check,binary=read_gltf(target);restored=copy.deepcopy(check)
 for field in ('nodes','meshes'):
  for i,n in enumerate(doc[field]):
   if 'name'in n:restored[field][i]['name']=n['name']
   else:restored[field][i].pop('name',None)
 assert restored==doc and bytes(binary)==bytes(blob),'Technical names modified source art/binary'
 return doc,check,binary

def unit_frame(doc,blob):
 from unreal_import_real_wc import expected_triangles
 points=[p for t in expected_triangles(doc,blob,STAND_NODE)for p in t]
 offset=[-(min(p[0]for p in points)+max(p[0]for p in points))/2*UNIT,-(min(p[1]for p in points)+max(p[1]for p in points))/2*UNIT,-min(p[2]for p in points)*UNIT]
 body=[p[2]for i,n in enumerate(doc['nodes'])if 'mesh'in n and i!=STAND_NODE for t in expected_triangles(doc,blob,i)for p in t]
 assert abs((max(body)-min(body))*UNIT-39)<1e-8,'Body excluding base must be39cm'
 return offset

def normalize_point(point,offset):return [float(point[i])*UNIT+offset[i]for i in range(3)]

def run():
 import unreal as u
 from private_home_candidate_scope import active_candidate_guard,CANDIDATE
 from home_asset_audit import read_gltf
 from unreal_import_reference_entry import snapshot
 from unreal_import_real_wc import expected_triangles,owned_geometry
 from unreal_import_reference_wall_console import positive_triangles
 from unreal_remove_frame_backings import native_triangles,same_triangles
 from unreal_import_real_bathroom_pendant import verify_owned_material
 from unreal_owned_import_cleanup import detach_added
 assert active_candidate_guard();source=ROOT/'original-unmodified-console.glb';assert hashlib.sha256(source.read_bytes()).hexdigest()==SHA
 proof=json.loads((ROOT/'format-conversion-proof.json').read_text());assert proof['glb_sha256']==SHA and proof['all_original_binary_bytes_exact']is True and proof['JSON_original_exact_except_buffer_uri_removal']is True
 provenance=json.loads((ROOT/'provenance.json').read_text());assert provenance['primary_license_current']=='CC-BY-ND-4.0' and provenance['private_only']is True
 doc,blob=read_gltf(source);mesh_nodes=contract(doc);offset=unit_frame(doc,blob)
 project=Path(u.Paths.project_dir()).resolve();assert project==Path(CANDIDATE).resolve()
 eas=u.get_editor_subsystem(u.EditorActorSubsystem);actors=list(eas.get_all_level_actors());before=snapshot(u,actors);mapfile=project/'Content/Sub01Home/ActualHome.umap';mapsha=hashlib.sha256(mapfile.read_bytes()).hexdigest()
 dest='/Game/Sub01Home/OriginalDatSketchPS5/V_'+SHA[:12]+'/Attempt_'+uuid.uuid4().hex
 prepared=project/'Saved/PrivateImportInputs'/('original-ps5-'+uuid.uuid4().hex+'.glb');original,pd,pb=prepare_names(source,prepared)
 records=[];deadline=time.monotonic()+180
 try:
  manager=u.InterchangeManager.get_interchange_manager_scripted();params=u.ImportAssetParameters();params.set_editor_property('is_automated',True)
  assert manager.import_scene(dest,manager.create_source_data(str(prepared)),params);manager.wait_until_all_tasks_done(False)
  by={};added=[a for a in eas.get_all_level_actors()if a.get_path_name()not in before]
  for a in added:
   a.set_actor_hidden_in_game(True);a.set_actor_enable_collision(False)
   for c in a.get_components_by_class(u.StaticMeshComponent):
    mesh=c.get_editor_property('static_mesh');assert mesh and mesh.get_path_name().startswith(dest+'/')
    c.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
    keys={a.get_actor_label(),mesh.get_name()}
    for i,n in mesh_nodes.items():
     if pd['nodes'][i]['name']in keys or pd['meshes'][n['mesh']]['name']in keys:by.setdefault(i,{})[c.get_path_name()]=(a,c)
  assert set(by)==set(mesh_nodes) and all(len(v)==1 for v in by.values()),'Every complete original part required'
  for i,node in mesh_nodes.items():
   assert time.monotonic()<deadline,'Bounded originalPS5 source import deadline'
   a,c=next(iter(by[i].values()));assert len(a.get_components_by_class(u.StaticMeshComponent))==1
   raw=snapshot(u,[a])[a.get_path_name()]
   if a.get_attach_parent_actor():
    assert a.get_attach_parent_actor().get_path_name()not in before
    a.detach_from_actor(u.DetachmentRule.KEEP_WORLD,u.DetachmentRule.KEEP_WORLD,u.DetachmentRule.KEEP_WORLD)
   t=a.get_actor_transform();transform=u.Transform();transform.translation=u.Vector(*normalize_point([t.translation.x,t.translation.y,t.translation.z],offset));transform.rotation=t.rotation;transform.scale3d=u.Vector(t.scale3d.x*UNIT,t.scale3d.y*UNIT,t.scale3d.z*UNIT);a.set_actor_transform(transform,False,True)
   owned_geometry(u,c.get_editor_property('static_mesh'),dest);assert u.Sub01HomeHandsInstance.finish_pending_static_compilation()==0
   expected=[list(map(lambda p:normalize_point(p,offset),tri))for tri in expected_triangles(pd,pb,i)]
   expected,zero=positive_triangles(expected);actual,nativezero=positive_triangles(native_triangles(u,c))
   assert same_triangles(expected,actual,.0001,deadline_monotonic=min(deadline,time.monotonic()+30)),'Complete original physical source differs node'+str(i)
   primitive=pd['meshes'][node['mesh']]['primitives'][0];material=pd['materials'][primitive['material']]
   pbr=verify_owned_material(u,c,material,dest,source_primitive_verified=True)
   c.set_collision_profile_name('NoCollision');c.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
   normalized=snapshot(u,[a])[a.get_path_name()]
   records.append({'source_node_index':i,'original_node_name':original['nodes'][i]['name'],'source_mesh_index':node['mesh'],'original_mesh_name':original['meshes'][node['mesh']]['name'],'source_material_index':primitive['material'],'source_material_name':material['name'],'is_original_base':i==STAND_NODE,'actor':a.get_path_name(),'component':c.get_path_name(),'mesh':c.get_editor_property('static_mesh').get_path_name(),'raw_actor_and_component_state':raw,'canonical_actor_and_component_state':normalized,'canonical_actor_transform':normalized['transform'],'actual_rendered_material':c.get_material(0).get_path_name(),'positive_triangles':len(actual),'exact_zero_source_indices':zero,'exact_zero_native_indices':nativezero,'physical_world_tolerance_cm':.0001,'pbr':pbr})
  assert len(records)==24 and len({r['source_material_index']for r in records})==13
  assert snapshot(u,actors)==before and active_candidate_guard();assert u.EditorAssetLibrary.save_directory(dest,only_if_is_dirty=False,recursive=True)
  detach_added(u,eas,before);assert snapshot(u,eas.get_all_level_actors())==before and hashlib.sha256(mapfile.read_bytes()).hexdigest()==mapsha
  result={'schema':'sub01.original-ps5-native-assets.v1','saved_assets':True,'source_sha256':SHA,'source_provenance':provenance,'original_geometry_and_13PBR_unchanged':True,'technical_names_only_input':str(prepared),'prepared_sha256':hashlib.sha256(prepared.read_bytes()).hexdigest(),'owned_destination':dest,'parts':records,'external_unit_conversion':UNIT,'external_canonical_offset_cm':offset,'canonical_front_direction_UE':[0,1,0],'body_height_excluding_original_base_cm':39,'whole_original_model_height_cm':39.51869201622763,'physical_world_tolerance_cm':.0001,'map_changed':False,'world_restored_exact':True,'current_device_assignment_changed':False,'native_visual_accepted':False,'game_changed':False,'publication_authorized':False,'epoch':time.time()}
  (project/'private-audit/original-ps5-native-assets.json').write_text(json.dumps(result,indent=2)+'\n');return result
 except Exception:
  detach_added(u,eas,before);assert snapshot(u,eas.get_all_level_actors())==before and hashlib.sha256(mapfile.read_bytes()).hexdigest()==mapsha;raise
