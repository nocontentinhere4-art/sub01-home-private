"""Runpod source-only original licensed DualSense PBR, no active Unreal changes."""
import bpy,sys,json,hashlib,math
from pathlib import Path
from mathutils import Vector
ROOT=Path('/workspace/sub01-home-private/real-dualsense-chizuko-r1');SOURCE=ROOT/'source/dualsense.gltf';OUT=ROOT/'source-review';OUT.mkdir(parents=True,exist_ok=True)
assert hashlib.sha256(SOURCE.read_bytes()).hexdigest()=='efb6114ec711cd3a697a8ce11c401e18b47449c026e82005ffde6047ef7a1df6'
d=json.loads(SOURCE.read_text());assert d['asset']['extras']['author'].startswith('Chizuko V')and 'CC-BY-4.0'in d['asset']['extras']['license']
bpy.ops.wm.read_factory_settings(use_empty=True);bpy.ops.import_scene.gltf(filepath=str(SOURCE));meshes=[o for o in bpy.context.scene.objects if o.type=='MESH'];assert len(meshes)==2
pts=[o.matrix_world@Vector(p)for o in meshes for p in o.bound_box];lo=Vector([min(p[k]for p in pts)for k in range(3)]);hi=Vector([max(p[k]for p in pts)for k in range(3)]);raw_bounds=[list(lo),list(hi)];dimensions=hi-lo;assert dimensions.x>dimensions.y>dimensions.z
scale=.16/dimensions.x;root=bpy.data.objects.new('Licensed source uniform physical160mm review',None);bpy.context.collection.objects.link(root)
for o in list(bpy.context.scene.objects):
 if o is root or o.parent:continue
 o.parent=root
root.scale=(scale,)*3;bpy.context.view_layer.update();pts=[o.matrix_world@Vector(p)for o in meshes for p in o.bound_box];lo=Vector([min(p[k]for p in pts)for k in range(3)]);hi=Vector([max(p[k]for p in pts)for k in range(3)]);root.location=-Vector(((lo.x+hi.x)/2,(lo.y+hi.y)/2,(lo.z+hi.z)/2));bpy.context.view_layer.update()
materials=[{'name':m.name,'blend':m.surface_render_method,'nodes':len(m.node_tree.nodes),'images':[n.image.filepath for n in m.node_tree.nodes if n.type=='TEX_IMAGE'and n.image]}for m in bpy.data.materials if m.use_nodes];assert len(materials)==2
scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=32;scene.cycles.use_denoising=True;scene.render.resolution_x=1200;scene.render.resolution_y=900;scene.render.resolution_percentage=100;scene.view_settings.view_transform='AgX';scene.view_settings.look='AgX - Medium High Contrast';scene.view_settings.exposure=0
world=bpy.data.worlds.new('Neutral source review only');world.use_nodes=True;world.node_tree.nodes['Background'].inputs[0].default_value=(.12,.12,.12,1);world.node_tree.nodes['Background'].inputs[1].default_value=.5;scene.world=world
for name,loc,power,size in [('Key',(.12,-.12,.25),18,.22),('Fill',(-.18,.06,.12),10,.2),('Bottom',(.1,.1,-.25),12,.2)]:
 data=bpy.data.lights.new(name,'AREA');data.energy=power;data.shape='DISK';data.size=size;o=bpy.data.objects.new(name,data);scene.collection.objects.link(o);o.location=loc;o.rotation_euler=(-o.location).to_track_quat('-Z','Y').to_euler()
camdata=bpy.data.cameras.new('SourceOnlyCamera');cam=bpy.data.objects.new('SourceOnlyCamera',camdata);scene.collection.objects.link(cam);scene.camera=cam;camdata.type='ORTHO';camdata.ortho_scale=.205
results=[]
for name,loc in [('front',(0,-.07,.35)),('underside',(0,.08,-.35)),('grip-side',(.20,-.19,.12))]:
 cam.location=loc;cam.rotation_euler=(-cam.location).to_track_quat('-Z','Y').to_euler();scene.render.filepath=str(OUT/(name+'.png'));bpy.ops.render.render(write_still=True);results.append({'view':name,'path':scene.render.filepath,'sha256':hashlib.sha256(Path(scene.render.filepath).read_bytes()).hexdigest()})
bpy.ops.file.pack_all();bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'licensed-dualsense-review.blend'))
report={'schema':'sub01.genuine-dualsense-pbr-source-review.v1','source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'license':d['asset']['extras'],'source_only':True,'native_imported':False,'game_changed':False,'raw_blender_bounds_m':raw_bounds,'uniform_physical_width_m':.16,'uniform_scale_only':scale,'source_materials_unmodified':True,'transparent_buttons_retained':True,'materials':materials,'images':results};(OUT/'review-report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)
