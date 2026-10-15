"""Runpod-only actual owner motion inspection, separate from the running home."""
import bpy,sys,json,hashlib,math
from pathlib import Path
from mathutils import Vector
source,output=map(Path,sys.argv[sys.argv.index('--')+1:]);output.mkdir(parents=True,exist_ok=False)
expected='48fdd0db549c843491f615368d7f1fa74f332558ebcc4289548d6718f9d32618'
assert hashlib.sha256(source.read_bytes()).hexdigest()==expected
bpy.ops.wm.read_factory_settings(use_empty=True)
s=bpy.context.scene;s.render.fps=20
bpy.ops.import_scene.gltf(filepath=str(source))
arms=[o for o in s.objects if o.type=='ARMATURE'];assert len(arms)==1
arm=arms[0];assert len(arm.data.bones)==65
actions=list(bpy.data.actions);assert len(actions)==1
arm.animation_data_create();arm.animation_data.action=actions[0]
for track in arm.animation_data.nla_tracks:track.mute=True
start,end=actions[0].frame_range
assert abs((end-start)/20-17.95)<1e-4
hips=arm.pose.bones['mixamorig:Hips']
world=bpy.data.worlds.new('Neutral motion review');world.use_nodes=True;world.node_tree.nodes['Background'].inputs[0].default_value=(.16,.17,.19,1);world.node_tree.nodes['Background'].inputs[1].default_value=.35;s.world=world
floor_mat=bpy.data.materials.new('Neutral floor');floor_mat.diffuse_color=(.14,.15,.17,1)
bpy.ops.mesh.primitive_plane_add(size=30,location=(0,0,-.015));bpy.context.object.data.materials.append(floor_mat)
bpy.ops.object.camera_add();camera=bpy.context.object;camera.data.type='ORTHO';camera.data.ortho_scale=2.2;s.camera=camera
lights=[]
for energy,size in[(180,3),(90,2)]:
 bpy.ops.object.light_add(type='AREA');light=bpy.context.object;light.data.energy=energy;light.data.shape='DISK';light.data.size=size;lights.append(light)
s.render.engine='CYCLES';s.cycles.device='CPU';s.cycles.samples=16;s.cycles.use_denoising=True;s.render.resolution_x=700;s.render.resolution_y=850;s.render.resolution_percentage=100;s.render.image_settings.file_format='PNG';s.view_settings.view_transform='AgX'
records=[]
for frame in[1,90,240,360]:
 s.frame_set(frame);bpy.context.view_layer.update();center=arm.matrix_world@hips.head;target=Vector((center.x,center.y,.95))
 camera.location=target+Vector((2.8,-5,1.0));camera.rotation_euler=(target-camera.location).to_track_quat('-Z','Y').to_euler()
 for light,offset in zip(lights,[Vector((-2,-3,4)),Vector((3,2,2))]):light.location=target+offset;light.rotation_euler=(target-light.location).to_track_quat('-Z','Y').to_euler()
 s.render.filepath=str(output/f'cozy-owner-frame-{frame:03}.png');bpy.ops.render.render(write_still=True)
 records.append({'frame':frame,'hips_world_m':list(center),'hands_world_m':{side:list(arm.matrix_world@arm.pose.bones[f'mixamorig:{side}Hand'].head)for side in['Left','Right']},'image':s.render.filepath})
(output/'render-report.json').write_text(json.dumps({'source_sha256':expected,'frames':records,'bones':65,'source_action_frames':[start,end],'native_imported':False,'visual_accepted':False,'scope':'Blender evaluation of actual owner and CozyClay demo motion; no live home, hand contact, or new inference claim'},indent=2)+'\n')
print('COZY_OWNER_ACTUAL_REVIEW_RENDERED',json.dumps(records),flush=True)
