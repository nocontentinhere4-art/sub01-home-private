"""Exact licensed physical-unit DualSense assets only; no original device retirement."""
from pathlib import Path
import json,hashlib,time,uuid
ROOT=Path('/workspace/sub01-home-private/real-dualsense-chizuko-r1/native-source-r1')
SHA='0c86d9bda650856c51946aefe2497e176d4c6aeb57aa806e7789e33c32428598'

def run():
 import unreal as u
 from private_home_candidate_scope import active_candidate_guard,CANDIDATE
 from home_asset_audit import read_gltf
 from unreal_import_reference_entry import snapshot,assigned_material_binding
 from unreal_import_real_wc import expected_triangles,owned_geometry
 from unreal_import_reference_wall_console import positive_triangles
 from unreal_remove_frame_backings import native_triangles,same_triangles
 from unreal_import_real_bathroom_pendant import verify_owned_material
 from unreal_owned_import_cleanup import detach_added
 assert active_candidate_guard();source=ROOT/'real-dualsense-160mm.glb';assert hashlib.sha256(source.read_bytes()).hexdigest()==SHA;proof=json.loads((ROOT/'packet.json').read_text());assert proof['packed_sha256']==SHA and proof['source_binary_prefix_exact']and proof['materials_exact']and proof['source_geometry_modified']is False and proof['canonical_width_m']==.16 and proof['nodes']==2 and proof['triangles']==76548 and proof['source_attribution']['author'].startswith('Chizuko V')
 doc,blob=read_gltf(source);assert len(doc['nodes'])==len(doc['meshes'])==len(doc['materials'])==2 and {n['name']for n in doc['nodes']}=={'RDS00','RDS01'}
 eas=u.get_editor_subsystem(u.EditorActorSubsystem);actors=list(eas.get_all_level_actors());before=snapshot(u,actors);mapfile=CANDIDATE/'Content/Sub01Home/ActualHome.umap';mapsha=hashlib.sha256(mapfile.read_bytes()).hexdigest();dest='/Game/Sub01Home/RealDualSense/V_'+SHA[:12]+'/Attempt_'+uuid.uuid4().hex;deadline=time.monotonic()+180;parts=[]
 try:
  manager=u.InterchangeManager.get_interchange_manager_scripted();params=u.ImportAssetParameters();params.set_editor_property('is_automated',True);assert manager.import_scene(dest,manager.create_source_data(str(source)),params);manager.wait_until_all_tasks_done(False);matches={}
  for a in eas.get_all_level_actors():
   if a.get_path_name()in before:continue
   a.set_actor_hidden_in_game(True)
   for c in a.get_components_by_class(u.StaticMeshComponent):
    mesh=c.get_editor_property('static_mesh')
    if mesh and mesh.get_path_name().startswith(dest+'/'):
     for key in{a.get_actor_label(),mesh.get_name()}:
      if key in{'RDS00','RDS01'}:matches.setdefault(key,{})[c.get_path_name()]=(a,c)
  for i,node in enumerate(doc['nodes']):
   assert time.monotonic()<deadline;pairs=list(matches.get(node['name'],{}).values());assert len(pairs)==1;a,c=pairs[0];assert len(a.get_components_by_class(u.StaticMeshComponent))==1;owned_geometry(u,c.get_editor_property('static_mesh'),dest);expected,zero=positive_triangles(expected_triangles(doc,blob,i));actual,nativezero=positive_triangles(native_triangles(u,c));assert same_triangles(expected,actual,.0001,deadline_monotonic=min(deadline,time.monotonic()+45)),'Genuine complete source geometry differs';pr=doc['meshes'][node['mesh']]['primitives'];assert len(pr)==1;material=doc['materials'][pr[0]['material']];assigned_material_binding(c,material,dest);pbr=(__import__('unreal_dualsense_glass_contract').verify(u,c,material,dest)if material['name']=='button_trans'else verify_owned_material(u,c,material,dest,source_primitive_verified=True));c.set_collision_profile_name('NoCollision');c.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
   native_mat=c.get_material(0);mel=u.MaterialEditingLibrary;scalar={str(n):float(mel.get_material_instance_scalar_parameter_value(native_mat,n))for n in mel.get_scalar_parameter_names(native_mat)}
   parts.append({'source_node':node['name'],'actor':a.get_path_name(),'component':c.get_path_name(),'mesh':c.get_editor_property('static_mesh').get_path_name(),'actor_transform':snapshot(u,[a])[a.get_path_name()]['transform'],'positive_triangles':len(actual),'source_exact_zero_indices':zero,'native_exact_zero_indices':nativezero,'pbr':pbr,'material_name':material['name'],'source_alpha_mode':material.get('alphaMode','OPAQUE'),'source_transmission':material.get('extensions',{}).get('KHR_materials_transmission'),'actual_scalar_parameters':scalar})
  assert len(parts)==2 and snapshot(u,actors)==before and active_candidate_guard();assert u.EditorAssetLibrary.save_directory(dest,only_if_is_dirty=False,recursive=True);detach_added(u,eas,before);assert snapshot(u,eas.get_all_level_actors())==before and hashlib.sha256(mapfile.read_bytes()).hexdigest()==mapsha
  r={'schema':'sub01.genuine-licensed-dualsense-native-assets.v1','saved_assets':True,'source_sha256':SHA,'source_attribution':proof['source_attribution'],'source_materials_unchanged':True,'owned_destination':dest,'parts':parts,'map_changed':False,'world_restored_exact':True,'current_device_assignment_changed':False,'hand_contact_accepted':False,'native_visual_accepted':False,'game_changed':False,'epoch':time.time()};(CANDIDATE/'private-audit/genuine-dualsense-native-assets.json').write_text(json.dumps(r,indent=2)+'\n');return r
 except Exception:
  detach_added(u,eas,before);assert snapshot(u,eas.get_all_level_actors())==before and hashlib.sha256(mapfile.read_bytes()).hexdigest()==mapsha;raise
