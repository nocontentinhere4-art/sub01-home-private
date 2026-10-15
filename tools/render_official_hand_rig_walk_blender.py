"""Actual new skin replay on Runpod; no native home or contact acceptance."""
import bpy,json,sys,hashlib
from pathlib import Path
from mathutils import Vector
source,out=map(Path,sys.argv[sys.argv.index('--')+1:]);out.mkdir(parents=True,exist_ok=False)
bpy.ops.wm.read_factory_settings(use_empty=True);s=bpy.context.scene;s.render.fps=30;bpy.ops.import_scene.gltf(filepath=str(source));arm=next(o for o in s.objects if o.type=='ARMATURE');assert len(arm.data.bones)==44;arm.animation_data_create();arm.animation_data.action=list(bpy.data.actions)[0]
for t in arm.animation_data.nla_tracks:t.mute=True
meshes=[o for o in s.objects if o.type=='MESH'and o.name.startswith('CC0Adult_')];glyphs={p.custom_shape for p in arm.pose.bones if p.custom_shape};extras=[o for o in s.objects if o.type=='MESH'and o not in meshes];print('GENERATED_BONE_GLYPHS',[(o.name,o in glyphs,o.hide_render)for o in extras],flush=True);assert len(meshes)==2 and all(o in glyphs for o in extras),'Unknown additional source mesh refused'
for glyph in extras:glyph.hide_render=True
mat=bpy.data.materials.new('Diagnostic skin material, scanned texture pending');mat.use_nodes=True;p=mat.node_tree.nodes['Principled BSDF'];p.inputs['Base Color'].default_value=(.43,.255,.18,1);p.inputs['Roughness'].default_value=.5;p.inputs['Subsurface Weight'].default_value=.06
for o in meshes:o.data.materials.clear();o.data.materials.append(mat)
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
report={'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'action_frames':list(arm.animation_data.action.frame_range),'actual_new_skin_evaluated':True,'bones':44,'frames':records,'material':'Neutral diagnostic skin, no scan texture claimed','baseline0_is_only_candidate_pending_visual_review':True,'cuff_fit_verified':False,'self_contact_or_prop_contact_verified':False,'native_imported':False,'visual_accepted':False};(out/'render-report.json').write_text(json.dumps(report,indent=2)+'\n');print('ACTUAL_NEW_HAND_DEFORMED_REPLAY_RENDERED',flush=True)
