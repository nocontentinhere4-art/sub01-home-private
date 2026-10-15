"""Actual lit genuine licensed DualSense on genuine cabinet; temporary display only, no hands."""
import json,time,hashlib,importlib
from pathlib import Path

def run():
 import unreal as u
 from private_home_candidate_scope import active_candidate_guard,CANDIDATE
 from unreal_import_reference_entry import snapshot
 from unreal_import_real_dualsense import ROOT,SHA
 from unreal_import_real_wc import expected_triangles
 from unreal_import_reference_wall_console import positive_triangles
 from unreal_remove_frame_backings import native_triangles,same_triangles
 from home_asset_audit import read_gltf
 import unreal_candidate_visual_review as review
 assert active_candidate_guard()and review._handle is None;review=importlib.reload(review)
 receipt=json.loads((CANDIDATE/'private-audit/genuine-dualsense-native-assets.json').read_text());assert receipt['saved_assets']and receipt['world_restored_exact']and receipt['source_sha256']==SHA
 source=ROOT/'real-dualsense-160mm.glb';assert hashlib.sha256(source.read_bytes()).hexdigest()==SHA;pd,pb=read_gltf(source)
 eas=u.get_editor_subsystem(u.EditorActorSubsystem);before=snapshot(u,eas.get_all_level_actors());mapfile=CANDIDATE/'Content/Sub01Home/ActualHome.umap';mapsha=hashlib.sha256(mapfile.read_bytes()).hexdigest();prior=u.EditorLevelLibrary.get_level_viewport_camera_info();parts=[]
 def restore(error=None):
  for a in reversed(parts):assert eas.destroy_actor(a)
  parts.clear();u.EditorLevelLibrary.set_level_viewport_camera_info(*prior);u.SystemLibrary.execute_console_command(u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world(),'t.MaxFPS 1');assert snapshot(u,eas.get_all_level_actors())==before and hashlib.sha256(mapfile.read_bytes()).hexdigest()==mapsha and active_candidate_guard();(CANDIDATE/'private-audit/genuine-dualsense-review-restored.json').write_text(json.dumps({'schema':'sub01.genuine-dualsense-temporary-display-restored.v1','all_temporary_actors_destroyed':True,'world_restored_exact':True,'map_unchanged':True,'game_input_changed':False,'source_original_licensed':True,'physical_hands_or_controller_assignment_changed':False,'capture_error':str(error)if error else None,'epoch':time.time()},indent=2)+'\n');return True
 try:
  rows=receipt['parts'];assert len(rows)==2
  for n,row in enumerate(rows):
   assert row['source_node']==pd['nodes'][n]['name'];mesh=u.load_asset(row['mesh']);assert isinstance(mesh,u.StaticMesh)and mesh.get_path_name().startswith(receipt['owned_destination']+'/');a=eas.spawn_actor_from_class(u.StaticMeshActor,u.Vector(0,0,0),u.Rotator());parts.append(a);a.set_actor_label('SUB01_REAL_DUALSENSE_TEMP_'+str(n));c=a.get_components_by_class(u.StaticMeshComponent)[0];c.set_static_mesh(mesh);assert c.get_num_materials()==1;matpath=row['pbr']['pbr'][0]['actual_material'];mat=u.load_asset(matpath);assert mat and matpath.startswith(receipt['owned_destination']+'/');c.set_material(0,mat);t=row['actor_transform'];transform=u.Transform();transform.translation=u.Vector(*t['translation']);transform.rotation=u.Quat(*t['rotation']);transform.scale3d=u.Vector(*t['scale']);a.set_actor_transform(transform,False,False);expected,_=positive_triangles(expected_triangles(pd,pb,n));actual,_=positive_triangles(native_triangles(u,c));assert same_triangles(expected,actual,.0001,deadline_monotonic=time.monotonic()+20),'Temporary display complete source differs';a.set_actor_enable_collision(False);c.set_collision_enabled(u.CollisionEnabled.NO_COLLISION);a.set_actor_location(u.Vector(*[t['translation'][k]+[-350,-45,56.735][k]for k in range(3)]),False,False)
  assert snapshot(u,[a for a in eas.get_all_level_actors()if a not in parts])==before
  u.SystemLibrary.execute_console_command(u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world(),'t.MaxFPS 15')
  return review.run([('genuine-dualsense-detail',(-350,-15,87),(-45,-90,0)),('genuine-dualsense-side',(-325,-25,71),(-24,-141.34,0))],capture_delay=3,initial_delay=3,on_finish=restore)
 except Exception:restore('setup refused');raise
