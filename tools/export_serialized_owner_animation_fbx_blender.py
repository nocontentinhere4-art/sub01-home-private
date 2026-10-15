"""Source-only same-axis FBX animation; compare every captured joint frame after export."""
import bpy,json,sys,hashlib,math
from pathlib import Path
import numpy as np
source,expected,out=sys.argv[sys.argv.index('--')+1:];source=Path(source);out=Path(out);out.mkdir(parents=True,exist_ok=False)
raw=source.read_bytes();assert hashlib.sha256(raw).hexdigest()==expected
bpy.ops.wm.read_factory_settings(use_empty=True);scene=bpy.context.scene;scene.render.fps=30;bpy.ops.import_scene.gltf(filepath=str(source));arm=next(o for o in scene.objects if o.type=='ARMATURE');assert len(arm.data.bones)==65;assert len(bpy.data.actions)==1;action=list(bpy.data.actions)[0];arm.animation_data.action=action
for t in arm.animation_data.nla_tracks:t.mute=True
start,end=action.frame_range;assert abs(start-round(start))<.001 and abs(end-round(end))<.001;first,last=round(start),round(end);assert 2<=last-first+1<=300
names=sorted(arm.data.bones.keys())
def binds(arm):return np.asarray([arm.matrix_world@arm.data.bones[n].matrix_local for n in names])
def poses(arm,frames):
 result=[]
 for frame in frames:
  scene.frame_set(int(frame));bpy.context.view_layer.update();result.append([arm.matrix_world@arm.pose.bones[n].matrix for n in names])
 return np.asarray(result,dtype=float)
source_bind=binds(arm);source_pose=poses(arm,range(first,last+1));scene.frame_start=first;scene.frame_end=last;scene.frame_set(first)
# Mesh-bearing transport is necessary: FBX omits an exact bind pose for a naked armature.
# Native must import ANIMATION ONLY against the already validated owner skeleton.
for o in scene.objects:o.select_set(o.type in {'ARMATURE','MESH'})
bpy.context.view_layer.objects.active=arm;fbx=out/'captured-animation-only.fbx';bpy.ops.export_scene.fbx(filepath=str(fbx),use_selection=True,object_types={'ARMATURE','MESH'},add_leaf_bones=False,use_armature_deform_only=False,apply_unit_scale=True,axis_forward='-Z',axis_up='Y',bake_anim=True,bake_anim_use_all_actions=False,bake_anim_use_nla_strips=False,bake_anim_simplify_factor=0,bake_anim_step=1)
bpy.ops.wm.read_factory_settings(use_empty=True);scene=bpy.context.scene;scene.render.fps=30;bpy.ops.import_scene.fbx(filepath=str(fbx),use_anim=True,automatic_bone_orientation=False,anim_offset=0.0);arm=next(o for o in scene.objects if o.type=='ARMATURE');assert sorted(arm.data.bones.keys())==names;assert len([o for o in scene.objects if o.type=='MESH'])==9;assert len(bpy.data.actions)==1;action=list(bpy.data.actions)[0];arm.animation_data.action=action
for t in arm.animation_data.nla_tracks:t.mute=True
rs,re=action.frame_range;assert abs(re-rs-(last-first))<.001;assert abs(rs-round(rs))<.001;actual_bind=binds(arm);actual_pose=poses(arm,range(round(rs),round(re)+1))
# Coordinate-frame changes are diagnosed separately from physical heads/skin.
head=float(np.linalg.norm(actual_pose[:,:,:3,3]-source_pose[:,:,:3,3],axis=-1).max());matrix_error=float(np.abs(actual_pose-source_pose).max());bind_error=float(np.abs(actual_bind-source_bind).max())
curves=[]
for a in bpy.data.actions:
 for layer in a.layers:
  for strip in layer.strips:
   for bag in strip.channelbags:curves.extend(bag.fcurves)
counts=sorted(set(len(c.keyframe_points)for c in curves));assert counts==[last-first+1],counts
report={'schema':'sub01.serialized-owner-animation-only-fbx-roundtrip.v1','source_sha256':expected,'fbx_sha256':hashlib.sha256(fbx.read_bytes()).hexdigest(),'fbx':str(fbx),'fps':30,'samples':last-first+1,'source_Blender_frame_range':[start,end],'FBX_Blender_frame_range':[rs,re],'duration_seconds':(last-first)/30,'all65_joint_pose_samples':len(names)*(last-first+1),'maximum_world_joint_head_error_m':head,'maximum_pose_matrix_component_error':matrix_error,'maximum_bind_matrix_component_error':bind_error,'FBX_curve_key_counts':counts,'FBX_contains_meshes':True,'native_import_mode_required':'animation-only; never replace owner mesh','same_axis_flags_as_validated_final_owner':True,'source_new_owner_family_sha256':'fd2f3b8e521b99f8c02d142d1b80f9df0fe3d37bd762b2ca587e0408d53c9f0e','native_skeleton_binding_pending':True,'controller_prop_contact_accepted':False,'native_imported':False}
(out/'animation-conversion-proof.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True);assert head<.00002 and matrix_error<.00002 and bind_error<.00002,'Animation-only FBX changed actual joint frame beyond20micrometre/component bound'
