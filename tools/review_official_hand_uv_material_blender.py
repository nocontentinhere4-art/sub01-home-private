"""Actual posed source UV and nail materials; no skin or native acceptance."""
import bpy,json,sys,hashlib
from pathlib import Path
from mathutils import Vector
uv_source,source,out=map(Path,sys.argv[sys.argv.index('--')+1:]);out.mkdir(parents=True,exist_ok=False);bpy.ops.wm.open_mainfile(filepath=str(uv_source));s=bpy.context.scene;s.render.fps=30;arm=bpy.data.objects['CC0AnatomicalHandRig'];assert len(arm.data.bones)==44;meshes=[bpy.data.objects['CC0Adult_'+side+'_ForearmHand_SOURCE_UNRIGGED']for side in['Left','Right']];before=set(bpy.data.objects);actions=set(bpy.data.actions);bpy.ops.import_scene.gltf(filepath=str(source));created=set(bpy.data.objects)-before;pose_rig=next(o for o in created if o.type=='ARMATURE');assert set(arm.data.bones.keys())==set(pose_rig.data.bones.keys());error=max(abs(a-b)for bone in arm.data.bones for row_a,row_b in zip(bone.matrix_local,pose_rig.data.bones[bone.name].matrix_local)for a,b in zip(row_a,row_b));assert error<1e-5,('Source pose rest differs',error);action=next(a for a in bpy.data.actions if a not in actions);arm.animation_data_create();arm.animation_data.action=action
if pose_rig.animation_data.action_slot:arm.animation_data.action_slot=pose_rig.animation_data.action_slot
for track in arm.animation_data.nla_tracks:track.mute=True
for o in created:o.hide_render=True
for o in meshes:assert len(o.data.materials)==2 and o.data.uv_layers.active;o.hide_render=False
w=bpy.data.worlds.new('Neutral anatomy studio');w.use_nodes=True;w.node_tree.nodes['Background'].inputs[0].default_value=(.13,.14,.16,1);w.node_tree.nodes['Background'].inputs[1].default_value=.35;s.world=w
bpy.ops.object.camera_add();camera=bpy.context.object;camera.data.type='ORTHO';camera.data.ortho_scale=.255;s.camera=camera;lights=[]
for energy,size in[(65,1.1),(25,.9)]:bpy.ops.object.light_add(type='AREA');o=bpy.context.object;o.data.energy=energy;o.data.size=size;lights.append(o)
s.render.engine='CYCLES';s.cycles.device='CPU';s.cycles.samples=24;s.cycles.use_denoising=True;s.render.resolution_x=750;s.render.resolution_y=950;s.render.resolution_percentage=100;s.render.image_settings.file_format='PNG';s.view_settings.view_transform='AgX';records=[]
for frame in[1,21]:
 s.frame_set(frame);bpy.context.view_layer.update()
 for side,sign in [('Left',1),('Right',-1)]:
  points=[arm.matrix_world@arm.pose.bones['mixamorig:'+side+'Hand'+f+str(i)].head for f in['Thumb','Index','Middle','Ring','Pinky']for i in[1,2,3,4]];target=sum(points,Vector())/len(points);direction=Vector((sign*.5,-.5,.1));camera.location=target+direction;camera.rotation_euler=(target-camera.location).to_track_quat('-Z','Y').to_euler()
  for light,offset in zip(lights,[direction.normalized()+Vector((-.2,0,.4)),Vector((.1,.4,.7))]):light.location=target+offset;light.rotation_euler=(target-light.location).to_track_quat('-Z','Y').to_euler()
  s.render.filepath=str(out/f'actual-new-{side.lower()}-walk-{frame:03}.png');bpy.ops.render.render(write_still=True);records.append({'side':side,'frame':frame,'image':s.render.filepath,'deformed_joint_positions':{f+str(i):list(arm.matrix_world@arm.pose.bones['mixamorig:'+side+'Hand'+f+str(i)].head)for f in['Thumb','Index','Middle','Ring','Pinky']for i in[1,2,3,4]}})
report={'pose_source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'uv_source_blend':str(uv_source),'action_frames':list(arm.animation_data.action.frame_range),'actual_new_skin_evaluated':True,'bones':44,'frames':records,'material':'Actual authored nail mask separate mild-gloss material; neutral skin PBR, no scanned texture claimed; original official loop UDIM UV preserved','baseline0_is_only_candidate_pending_visual_review':True,'cuff_fit_verified':False,'self_contact_or_prop_contact_verified':False,'native_imported':False,'visual_accepted':False};(out/'render-report.json').write_text(json.dumps(report,indent=2)+'\n');print('ACTUAL_NEW_HAND_DEFORMED_REPLAY_RENDERED',flush=True)
