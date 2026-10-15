"""Actual candidate-home viewport WIP, normal body/head policy, temporary actor only."""
from pathlib import Path
import json,hashlib,time

def run():
 import unreal as u
 from private_home_candidate_scope import active_candidate_guard,CANDIDATE
 from unreal_import_reference_entry import snapshot
 import unreal_candidate_visual_review as review
 assert active_candidate_guard();r=CANDIDATE/'private-audit';source=json.loads((r/'anatomical-owner-fbx-candidate.json').read_text());body=json.loads((r/'anatomical-body-pose-audit.json').read_text());pbr=json.loads((r/'anatomical-source-material-binding.json').read_text());assert body['body_pose_equivalence_passed']and pbr['core_factors_textures_transforms_two_sided_verified']and pbr['cuff_normal_625x625_verified']
 eas=u.get_editor_subsystem(u.EditorActorSubsystem);before=snapshot(u,eas.get_all_level_actors());mapfile=CANDIDATE/'Content/Sub01Home/ActualHome.umap';mapsha=hashlib.sha256(mapfile.read_bytes()).hexdigest();prior_camera=u.EditorLevelLibrary.get_level_viewport_camera_info()
 actor=None;c=None;world=u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world();phase={'last':0,'destroyed':False,'samples':[]}
 def record_pose(name):
  if c:
   values={}
   for bone in ['Hips','Head','LeftHand','RightHand','LeftFoot','RightFoot']:
    v=c.get_socket_location(bone);values[bone]=[v.x,v.y,v.z]
   origin,extent=actor.get_actor_bounds(False);phase['samples'].append({'name':name,'phase_s':phase['last'],'actual_component_position_s':float(c.get_position()),'bones_world_cm':values,'bounds_origin':[origin.x,origin.y,origin.z],'bounds_extent':[extent.x,extent.y,extent.z]})
 def restore(error=None):
  if actor and not phase['destroyed']:
   try:record_pose('final')
   except Exception as diagnostic_error:phase['samples'].append({'diagnostic_error':str(diagnostic_error)})
   finally:
    assert eas.destroy_actor(actor);phase['destroyed']=True
  u.EditorLevelLibrary.set_level_viewport_camera_info(*prior_camera);u.SystemLibrary.execute_console_command(world,'t.MaxFPS 1')
  assert snapshot(u,eas.get_all_level_actors())==before and hashlib.sha256(mapfile.read_bytes()).hexdigest()==mapsha and active_candidate_guard()
  (r/'anatomical-first-person-restored.json').write_text(json.dumps({'schema':'sub01.anatomical-first-person-restored.v1','temporary_actor_destroyed':True,'protected_world_exact':True,'map_unchanged':True,'game_input_changed':False,'capture_error':str(error)if error else None,'pose_diagnostics':phase['samples'],'epoch':time.time()},indent=2)+'\n');return True
 try:
  # Exact normal Walk policy: pawn[200,70,95.65],yaw−90; mesh offsetZ−91,
  # mesh relative yaw−90; iris-derived camera offset[22.208151,3.580561,64.610182].
  actor=eas.spawn_actor_from_class(u.SkeletalMeshActor,u.Vector(200,70,4.65),u.Rotator(yaw=-180));assert actor;actor.set_actor_label('SUB01_AnatomicalOwner_TEMP_WIP');actor.set_actor_enable_collision(False)
  c=actor.get_editor_property('skeletal_mesh_component');mesh=u.load_asset(source['meshes'][0]['path']);clip=u.load_asset(source['clips'][0]['path']);assert clip.get_editor_property('skeleton')==mesh.get_editor_property('skeleton')
  c.set_skeletal_mesh_asset(mesh);c.set_collision_enabled(u.CollisionEnabled.NO_COLLISION);c.override_animation_data(clip,False,False,0,0);c.set_update_animation_in_editor(True);c.hide_bone_by_name('Head',u.PhysBodyOp.PBO_NONE)
  u.SystemLibrary.execute_console_command(world,'t.MaxFPS 15')
  camera=(203.580561,47.791849,160.260182)
  views=[('body-front',(200,-140,130),(-12,90,0)),('hands-down-phase-03',camera,(-82,-90,0)),('hands-down-phase-15',camera,(-82,-90,0)),('hands-down-phase-28',camera,(-82,-90,0)),('body-side',(410,70,120),(-8,180,0))]
  samples={'body-front':15/30,'hands-down-phase-03':3/30,'hands-down-phase-15':15/30,'hands-down-phase-28':28/30,'body-side':15/30}
  def set_pose(name):
   assert active_candidate_guard();record_pose('previous-before-'+name);c.override_animation_data(clip,False,False,samples[name],0);c.set_position(samples[name],False);c.set_update_animation_in_editor(True);phase['last']=samples[name]
  result=review.run(views,capture_delay=3,initial_delay=3,before_view=set_pose,on_finish=restore)
  (r/'anatomical-first-person-review.json').write_text(json.dumps({'schema':'sub01.anatomical-first-person-review.v1','actual_candidate_editor':True,'review':result,'mesh':mesh.get_path_name(),'clip':clip.get_path_name(),'normal_hidden_head_bones':['Head'],'normal_component_policy':True,'temporary_only':True,'native_game_owner_changed':False,'contact_accepted':False,'epoch':time.time()},indent=2)+'\n');return result
 except Exception:
  restore('setup refused');raise
