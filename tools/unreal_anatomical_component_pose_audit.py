"""Actual Editor component evaluation versus independent animation FK, all32 poses."""
from pathlib import Path
import json,math,time
_handle=None

def run():
 global _handle
 import unreal as u
 import unreal_candidate_visual_review as review
 from private_home_candidate_scope import active_candidate_guard,CANDIDATE
 from unreal_import_reference_entry import snapshot
 assert active_candidate_guard()and _handle is None and review._handle is None
 r=CANDIDATE/'private-audit';d=json.loads((r/'anatomical-owner-fbx-candidate.json').read_text());mesh=u.load_asset(d['meshes'][0]['path']);clip=u.load_asset(d['clips'][0]['path']);eas=u.get_editor_subsystem(u.EditorActorSubsystem);before=snapshot(u,eas.get_all_level_actors());world=u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
 actor=eas.spawn_actor_from_class(u.SkeletalMeshActor,u.Vector(200,70,4.65),u.Rotator(yaw=-180));actor.set_actor_enable_collision(False);actor.set_actor_label('SUB01_AnatomicalComponent_TEMP_AUDIT');c=actor.get_editor_property('skeletal_mesh_component');c.set_skeletal_mesh_asset(mesh);c.set_collision_enabled(u.CollisionEnabled.NO_COLLISION);c.override_animation_data(clip,False,False,0,0);c.set_update_animation_in_editor(True);c.set_editor_property('visibility_based_anim_tick_option',u.VisibilityBasedAnimTickOption.ALWAYS_TICK_POSE_AND_REFRESH_BONES);c.hide_bone_by_name('Head',u.PhysBodyOp.PBO_NONE)
 names=[str(c.get_bone_name(i))for i in range(c.get_num_bones())];parents={n:str(c.get_parent_bone(n))for n in names};assert len(names)==66
 report={'schema':'sub01.actual-anatomical-component-pose-audit.v1','source':'actual SkeletalMeshComponent bone sockets after Editor pose evaluation versus independent AnimationLibrary local-to-component FK','mesh':mesh.get_path_name(),'clip':clip.get_path_name(),'head_hidden':True,'samples':[],'motion_phase_verified':False,'contact_accepted':False,'game_input_changed':False,'epoch':time.time()};state={'index':0,'frames':0,'after':time.monotonic()+.4,'busy':False}
 u.SystemLibrary.execute_console_command(world,'t.MaxFPS 15')
 def finish(error=None):
  global _handle
  try:assert eas.destroy_actor(actor)
  finally:
   u.SystemLibrary.execute_console_command(world,'t.MaxFPS 1')
   if _handle is not None:u.unregister_slate_post_tick_callback(_handle)
   _handle=None;review._handle=None;review._active_finish_hook=None
  report.update(error=error,world_restored_exact=snapshot(u,eas.get_all_level_actors())==before,finished_epoch=time.time())
  assert report['world_restored_exact']and active_candidate_guard()
  report['motion_phase_verified']=error is None and len(report['samples'])==32 and all(s['max_position_error_cm']<=.02 and s['max_rotation_error_degrees']<=.05 and s['max_scale_error']<=.0001 and abs(s['actual_position_s']-s['requested_s'])<=1e-5 for s in report['samples'])
  (r/'anatomical-component-pose-audit.json').write_text(json.dumps(report,indent=2)+'\n')
 def tick(delta):
  if state['busy']:return
  state['busy']=True
  try:
   state['frames']+=1
   if state['frames']<3 or time.monotonic()<state['after']:return
   assert active_candidate_guard();t=state['index']/30
   local=dict(zip(names,u.AnimationLibrary.get_bone_poses_for_time(clip,[u.Name(n)for n in names],t,False,mesh)));resolved={}
   def component(n):
    if n not in resolved:resolved[n]=u.MathLibrary.compose_transforms(local[n],component(parents[n]))if parents[n]in local else local[n]
    return resolved[n]
   maxp=maxr=maxs=0.;rows=[]
   for n in names:
    if n in ('Head','HeadTop_End'):continue
    expected=component(n);actual=c.get_socket_transform(n,u.RelativeTransformSpace.RTS_COMPONENT);pe=(expected.translation-actual.translation).length();q=expected.rotation;z=actual.rotation;dot=abs(q.x*z.x+q.y*z.y+q.z*z.z+q.w*z.w);re=math.degrees(2*math.acos(min(1.,dot)));se=(expected.scale3d-actual.scale3d).length();maxp=max(maxp,pe);maxr=max(maxr,re);maxs=max(maxs,se)
    if 'Hand'in n:rows.append({'bone':n,'actual_component_translation_cm':[actual.translation.x,actual.translation.y,actual.translation.z],'position_error_cm':pe,'rotation_error_degrees':re,'scale_error':se})
   report['samples'].append({'requested_s':t,'actual_position_s':float(c.get_position()),'max_position_error_cm':maxp,'max_rotation_error_degrees':maxr,'max_scale_error':maxs,'finger_and_wrist_rows':rows})
   state['index']+=1
   if state['index']==32:finish();return
   c.set_position(state['index']/30,False);state['frames']=0;state['after']=time.monotonic()+.1
  except Exception as exc:finish(type(exc).__name__+': '+str(exc))
  finally:state['busy']=False
 _handle=u.register_slate_post_tick_callback(tick);review._handle=_handle;review._active_finish_hook=finish
 return {'component_audit_started':True,'poses':32,'game_input_changed':False}
