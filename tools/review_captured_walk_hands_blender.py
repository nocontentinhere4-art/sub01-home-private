"""Private isolated Blender source review. No native editor or running input."""
import bpy,sys,json,hashlib,math
from pathlib import Path
from mathutils import Vector
source,output=map(Path,sys.argv[sys.argv.index('--')+1:]);output.mkdir(parents=True,exist_ok=False)
assert hashlib.sha256(source.read_bytes()).hexdigest()=='9258cf17cc7f192e90205894a9a439f0d668a4eef808fd467756567f1d95c2a2'
bpy.ops.wm.read_factory_settings(use_empty=True);s=bpy.context.scene;s.render.fps=20;bpy.ops.import_scene.gltf(filepath=str(source));arm=next(o for o in s.objects if o.type=='ARMATURE');assert len(arm.data.bones)==65
arm.animation_data_create();arm.animation_data.action=list(bpy.data.actions)[0]
for track in arm.animation_data.nla_tracks:track.mute=True
world=bpy.data.worlds.new('Source hand review neutral');world.use_nodes=True;world.node_tree.nodes['Background'].inputs[0].default_value=(.17,.18,.2,1);world.node_tree.nodes['Background'].inputs[1].default_value=.4;s.world=world
bpy.ops.object.camera_add();camera=bpy.context.object;camera.data.type='ORTHO';s.camera=camera
lights=[]
for energy,size in[(160,2.5),(90,2)]:bpy.ops.object.light_add(type='AREA');light=bpy.context.object;light.data.energy=energy;light.data.size=size;lights.append(light)
s.render.engine='CYCLES';s.cycles.device='CPU';s.cycles.samples=24;s.cycles.use_denoising=True;s.render.resolution_x=700;s.render.resolution_y=850;s.render.resolution_percentage=100;s.render.image_settings.file_format='PNG';s.view_settings.view_transform='AgX'
records=[]
for frame in[90,240]:
 s.frame_set(frame);bpy.context.view_layer.update()
 for side in['Left','Right']:
  bones=arm.pose.bones;names=[f'mixamorig:{side}Hand{finger}{segment}'for finger in['Thumb','Index','Middle','Ring','Pinky']for segment in[1,2,3,4]];points=[arm.matrix_world@bones[name].head for name in names];wrist=arm.matrix_world@bones[f'mixamorig:{side}Hand'].head;target=sum(points,Vector())/len(points)
  camera.data.ortho_scale=.31;camera.location=target+Vector((.38,-.62,.3));camera.rotation_euler=(target-camera.location).to_track_quat('-Z','Y').to_euler()
  for light,offset in zip(lights,[Vector((-1,-2,3)),Vector((2,1,2))]):light.location=target+offset;light.rotation_euler=(target-light.location).to_track_quat('-Z','Y').to_euler()
  s.render.filepath=str(output/f'captured-{side.lower()}-frame-{frame:03}.png');bpy.ops.render.render(write_still=True)
  bends={}
  for finger in['Index','Middle','Ring','Pinky']:
   p=[arm.matrix_world@bones[f'mixamorig:{side}Hand{finger}{i}'].head for i in[1,2,3,4]];bends[finger]={'PIP_unsigned_degrees':math.degrees((p[1]-p[0]).angle(p[2]-p[1])),'DIP_unsigned_degrees':math.degrees((p[2]-p[1]).angle(p[3]-p[2])),'tip_to_wrist_cm':100*(p[-1]-wrist).length}
  records.append({'side':side,'frame':frame,'world_m':{n:list(p)for n,p in zip(names,points)},'measured_distal_chain_bends':bends,'image':s.render.filepath,'visual_accepted':False})
(output/'review-report.json').write_text(json.dumps({'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'native_imported':False,'source_skin_evaluated':True,'records':records,'note':'Each real hand uses its own capture. Unsigned chain angles do not certify flexion sign; rendered independent anatomy review required.'},indent=2)+'\n');print('CAPTURED_HAND_REVIEW_DONE',flush=True)
