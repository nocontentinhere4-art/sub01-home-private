"""Source-only lit review of the actual new wall/cabinet with original TV geometry."""
import bpy,json,sys,math
from pathlib import Path
from mathutils import Vector
sys.path.insert(0,'/home/unreal/runtime-tools')
from home_asset_audit import read_gltf
ROOT=Path('/workspace/sub01-home-private/reference-living-tv-wall-r2/output');HOME=Path('/workspace/sub01-private-recovered-project/Sub01HomeLab/SourceAssets/full-home.glb')
bpy.ops.wm.open_mainfile(filepath=str(ROOT/'living-tv-wall.blend'));before=set(bpy.context.scene.objects);doc,_=read_gltf(HOME);bpy.ops.import_scene.gltf(filepath=str(HOME));added=set(bpy.context.scene.objects)-before;keep=[]
for i in (0,130,131):
 name=doc['nodes'][i]['name'];found=[o for o in added if o.type=='MESH'and o.name==name];assert len(found)==1,(i,name);keep+=found
for o in added:
 if o not in keep:bpy.data.objects.remove(o,do_unlink=True)
scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=24;scene.cycles.use_denoising=True;scene.render.threads_mode='FIXED';scene.render.threads=2;scene.render.resolution_x=1120;scene.render.resolution_y=840;scene.render.resolution_percentage=100
scene.world.color=(.18,.18,.18)
bpy.ops.object.light_add(type='AREA',location=(-1.9,-2.1,2.7));a=bpy.context.object;a.name='Source review daylight softbox';a.data.energy=220;a.data.shape='DISK';a.data.size=3;a.rotation_euler=(Vector((-3.75,0,1.25))-a.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.object.light_add(type='AREA',location=(-2.1,1.5,2.6));a=bpy.context.object;a.data.energy=100;a.data.size=2;a.rotation_euler=(Vector((-3.75,0,1.0))-a.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.object.camera_add(location=(-.8,-1.55,1.65));camera=bpy.context.object;camera.rotation_euler=(Vector((-3.78,.05,1.44))-camera.location).to_track_quat('-Z','Y').to_euler();camera.data.lens=40;scene.camera=camera;scene.view_settings.view_transform='AgX';scene.render.image_settings.file_format='PNG';scene.render.filepath=str(ROOT/'living-tv-wall-source-lit-review.png');bpy.ops.render.render(write_still=True);print('SOURCE_ONLY_LIT_REVIEW',scene.render.filepath,flush=True)
