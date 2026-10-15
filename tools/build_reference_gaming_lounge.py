"""Private Blender assembly from pinned genuine CC0 sofa/table/pillow meshes.
No original model vertices are authored, remeshed or procedurally replaced.
"""
import bpy,json,math,hashlib
from pathlib import Path
from mathutils import Vector,Matrix
ROOT=Path('/workspace/sub01-home-private/reference-gaming-lounge-r1');ASSETS=ROOT/'assets';OUT=ROOT/'output';OUT.mkdir(parents=True,exist_ok=True)
manifest=json.loads((ROOT/'source-manifest.json').read_text())
for asset in manifest:
 for item in asset['files']:
  p=ASSETS/item['file'];assert p.stat().st_size==item['bytes']and hashlib.sha256(p.read_bytes()).hexdigest()==item['sha256']
bpy.ops.wm.read_factory_settings(use_empty=True);scene=bpy.context.scene;parts=[]
def bounds(objects):
 p=[o.matrix_world@Vector(v)for o in objects for v in o.bound_box]
 return [[min(v[i]for v in p)for i in range(3)],[max(v[i]for v in p)for i in range(3)]]
def load(asset,label,x,y,bottom):
 before=set(bpy.data.objects);bpy.ops.import_scene.gltf(filepath=str(ASSETS/asset/(asset+'.gltf')));objects=sorted([o for o in set(bpy.data.objects)-before if o.type=='MESH'],key=lambda o:o.name);assert 1<=len(objects)<=4,(asset,len(objects))
 signatures={o:hashlib.sha256(bytes(str([tuple(v.co)for v in o.data.vertices]),'utf8')).hexdigest()for o in objects};b=bounds(objects);center=Vector(((b[0][0]+b[1][0])/2,(b[0][1]+b[1][1])/2,b[0][2]));angle=-math.pi/2 if label!='Table'else 0
 transform=Matrix.Translation(Vector((x,y,bottom)))@Matrix.Rotation(angle,4,'Z')@Matrix.Translation(-center)
 for i,obj in enumerate(objects):
  obj.matrix_world=transform@obj.matrix_world;obj.name='GamingLounge_'+label+'_'+str(i).zfill(3);obj.data.name=obj.name+'_Mesh';obj.data.calc_loop_triangles();assert signatures[obj]==hashlib.sha256(bytes(str([tuple(v.co)for v in obj.data.vertices]),'utf8')).hexdigest()
 bpy.context.view_layer.update();parts.append({'role':label,'source_asset':asset,'source_position_bytes_preserved':True,'source_vertex_signatures':{o.name:signatures[o]for o in objects},'physical_uniform_scale':1,'nodes':[o.name for o in objects],'vertices':sum(len(o.data.vertices)for o in objects),'triangles':sum(len(o.data.loop_triangles)for o in objects),'world_bounds_blender_m':bounds(objects),'world_bounds_UE_cm':None});return objects
sofa=load('sofa_03','Sofa',-1.445,-.1,.02505)
table=load('modern_coffee_table_01','Table',-2.59,.05,.02505)
# Source pair is a real scanned two-pillow assembly; source local geometry intact.
pillows=load('throw_pillows_01','Pillows',-1.19,-.1,.51505)
for part,objects in zip(parts,[sofa,table,pillows]):
 pts=[obj.matrix_world@Vector(v)for obj in objects for v in obj.bound_box];ue=[Vector((p.x,-p.y,p.z))*100 for p in pts];part['world_bounds_UE_cm']=[[min(p[i]for p in ue)for i in range(3)],[max(p[i]for p in ue)for i in range(3)]]
# Preserve all actual imported PBR maps. These first images show original source
# colors; a later cloth tint may be reviewed, but not concealed as a new scan.
source_objects=sofa+table+pillows
bpy.ops.object.select_all(action='DESELECT')
for obj in source_objects:obj.select_set(True)
bpy.context.view_layer.objects.active=sofa[0]
bpy.ops.export_scene.gltf(filepath=str(OUT/'genuine-gaming-lounge-source.glb'),export_format='GLB',use_selection=True,export_animations=False,export_apply=True)
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'genuine-gaming-lounge-source.blend'))
# Neutral source review stage, not the live home and not a furniture model.
bpy.ops.mesh.primitive_plane_add(size=12,location=(-1,0,.025));floor=bpy.context.object;floor.name='REVIEW_STAGE_NOT_EXPORT';mat=bpy.data.materials.new('Neutral source stage');mat.diffuse_color=(.13,.135,.14,1);floor.data.materials.append(mat)
world=bpy.data.worlds.new('Source studio');world.use_nodes=True;world.node_tree.nodes['Background'].inputs[1].default_value=.35;scene.world=world
for loc,power,size in[((-3.2,-2.5,3.2),450,3),((.1,2.8,2.6),250,2.3)]:
 bpy.ops.object.light_add(type='AREA',location=loc);light=bpy.context.object;light.data.energy=power;light.data.shape='DISK';light.data.size=size;light.rotation_euler=(Vector((-1.5,0,.6))-light.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.object.camera_add(location=(-4.8,-3.8,2.5));camera=bpy.context.object;scene.camera=camera;camera.rotation_euler=(Vector((-1.6,0,.65))-camera.location).to_track_quat('-Z','Y').to_euler();camera.data.type='ORTHO';camera.data.ortho_scale=4.5
scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=24;scene.cycles.use_denoising=True;scene.render.resolution_x=1440;scene.render.resolution_y=1080;scene.render.resolution_percentage=100;scene.render.image_settings.file_format='PNG';scene.view_settings.view_transform='AgX';scene.render.filepath=str(OUT/'genuine-gaming-lounge-source-review.png');bpy.ops.render.render(write_still=True)
report={'schema':'sub01.genuine-gaming-lounge-source.v1','source_assets':manifest,'parts':parts,'ref_scope':'original real-model comparison before sofa style selection; references gray sectional and compact navy plush gaming sofa','active_game_mutated':False,'native_imported':False,'seating_contact_ready':False,'clearance_independently_pending':True,'original_material_colors_preserved':True,'no_procedural_furniture':True,'source_output_sha256':hashlib.sha256((OUT/'genuine-gaming-lounge-source.glb').read_bytes()).hexdigest()};(OUT/'source-report.json').write_text(json.dumps(report,indent=2));print('LOUNGE_SOURCE_READY',report['source_output_sha256'],flush=True)
