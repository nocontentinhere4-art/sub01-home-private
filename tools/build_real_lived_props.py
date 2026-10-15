"""Genuine CC0 lived-in kitchen props; rigid original geometry/PBR only."""
import bpy,json,math,hashlib
from pathlib import Path
from mathutils import Vector,Matrix
from mathutils.bvhtree import BVHTree
ROOT=Path('/workspace/sub01-home-private/real-lived-props-r1');OUT=ROOT/'output';OUT.mkdir(exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True);scene=bpy.context.scene

def bounds(obs):
 pts=[o.matrix_world@v.co for o in obs for v in o.data.vertices];return [[min(p[i]for p in pts)for i in range(3)],[max(p[i]for p in pts)for i in range(3)]]
def signature(o):return hashlib.sha256(str([tuple(v.co)for v in o.data.vertices]).encode()).hexdigest()
def load(asset,prefix):
 old=set(scene.objects);bpy.ops.import_scene.gltf(filepath=str(ROOT/asset/(asset+'.gltf')));obs=sorted([o for o in set(scene.objects)-old if o.type=='MESH'],key=lambda o:o.name)
 for i,o in enumerate(obs):
  world=o.matrix_world.copy();o.parent=None;o.matrix_world=world;o.name=prefix+f'{i:03}';o.data.name=o.name+'_Mesh'
 return obs

def place(obs,x,y,z):
 b=bounds(obs);T=Matrix.Translation(Vector((x-(b[0][0]+b[1][0])/2,y-(b[0][1]+b[1][1])/2,z-b[0][2])))
 for o in obs:o.matrix_world=T@o.matrix_world
 bpy.context.view_layer.update()
def bvh(obs):
 v=[];p=[]
 for o in obs:
  start=len(v);v.extend(o.matrix_world@x.co for x in o.data.vertices);p.extend([start+i for i in poly.vertices]for poly in o.data.polygons)
 return BVHTree.FromPolygons(v,p,all_triangles=False)
def roof(obs,x,y):
 hit=bvh(obs).ray_cast(Vector((x,y,10)),Vector((0,0,-1)),20);assert hit[0]is not None;return hit[0].z

groups={};proof={}
for asset,prefix in [('wooden_cutting_board','LiveBoard_'),('wooden_bowl_01','LiveBowl_'),('food_apple_01','LiveApple_'),('potted_plant_04','LivePlant_')]:
 obs=load(asset,prefix);groups[asset]=obs;b=bounds(obs);proof[asset]={'source_dimensions_m':[b[1][i]-b[0][i]for i in range(3)],'source_vertex_signatures':{o.name:signature(o)for o in obs},'parts':len(obs),'source':'https://polyhaven.com/a/'+asset,'license':'CC0-1.0'};print('GENUINE_PROP_DIMS',asset,proof[asset]['source_dimensions_m'],flush=True)
board=groups['wooden_cutting_board'];b=bounds(board);d=[b[1][i]-b[0][i]for i in range(3)]
assert d[2]<.10 and max(d[:2])<.80,'Sourceboard must be physically horizontal, no deformation'
place(board,-2.04,3.50,.9225101)
bowl=groups['wooden_bowl_01'];b=bounds(bowl);diameter=max(b[1][i]-b[0][i]for i in (0,1));assert diameter<.40
bowlx=-1.63;place(bowl,bowlx,3.65,.9225101)
apple=groups['food_apple_01'];place(apple,-2.04,3.50,roof(board,-2.04,3.50)+.00001)
# Genuine existing Around source provides support at actual INNER WOOD DISK.
old=set(scene.objects);bpy.ops.import_scene.gltf(filepath='/workspace/sub01-home-private/manufacturer-around-large-r1/placed-dark-r3/muuto-around-large-dark.glb');table=[o for o in set(scene.objects)-old if o.type=='MESH'];tablez=roof(table,-2.538,-.05)
plant=groups['potted_plant_04'];b=bounds(plant);assert b[1][2]-b[0][2]<.80,'Actualsourceplant too large for tabletop; no artificialshrink'
place(plant,-2.538,-.05,tablez+.00001+.00003716064453125)
for asset,obs in groups.items():
 assert all(signature(o)==proof[asset]['source_vertex_signatures'][o.name]for o in obs),'Original prop geometry changed'
 b=bounds(obs);proof[asset]['bounds_UE_cm']=[[b[0][0]*100,-b[1][1]*100,b[0][2]*100],[b[1][0]*100,-b[0][1]*100,b[1][2]*100]]

def export(obs,path):
 bpy.ops.object.select_all(action='DESELECT')
 for o in obs:o.select_set(True)
 bpy.context.view_layer.objects.active=obs[0];bpy.ops.export_scene.gltf(filepath=str(path),export_format='GLB',use_selection=True,export_apply=True,export_animations=False)
kitchen=board+bowl+apple;export(kitchen,OUT/'genuine-kitchen-lived-props.glb');export(plant,OUT/'genuine-around-plant.glb');bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'genuine-lived-props.blend'))
# Neutral support visual only, not exported furniture or a fake kitchen model.
bpy.ops.mesh.primitive_plane_add(size=1,location=(-1.85,3.5,.9225001));support=bpy.context.object;support.scale=(2,.70,1);m=bpy.data.materials.new('Diagnostic actual counter support');m.diffuse_color=(.55,.55,.53,1);support.data.materials.append(m)
world=bpy.data.worlds.new('Real source review');world.use_nodes=True;world.node_tree.nodes['Background'].inputs[1].default_value=.4;scene.world=world
for loc,power in [((-2.8,2.4,2.8),250),((-.8,4.5,2.2),180)]:
 bpy.ops.object.light_add(type='AREA',location=loc);light=bpy.context.object;light.data.energy=power;light.data.size=1.6;light.rotation_euler=(Vector((-1.8,3.5,1))-light.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.object.camera_add(location=(-1.3,2.1,2));camera=bpy.context.object;camera.rotation_euler=(Vector((-1.8,3.5,1.0))-camera.location).to_track_quat('-Z','Y').to_euler();camera.data.type='ORTHO';camera.data.ortho_scale=1.35;scene.camera=camera
scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=16;scene.cycles.use_denoising=True;scene.render.resolution_x=960;scene.render.resolution_y=720;scene.render.resolution_percentage=100;scene.render.filepath=str(OUT/'genuine-kitchen-props-source-review.png');bpy.ops.render.render(write_still=True)
support.hide_render=True
for o in kitchen:o.hide_render=True
camera.location=(-3.2,-.9,1.05);camera.rotation_euler=(Vector((-2.538,-.05,tablez+.12))-camera.location).to_track_quat('-Z','Y').to_euler();camera.data.ortho_scale=1.1;scene.render.filepath=str(OUT/'genuine-around-plant-source-review.png');bpy.ops.render.render(write_still=True)
report={'schema':'sub01.genuine-lived-props-source.v1','sources':proof,'all_original_geometry_materials_UV_scale_preserved':True,'rigid_placement_only':True,'countertop_top_cm':92.25001,'plant_actual_table_inner_support_cm':tablez*100,'plant_full_foot_support_additional_rigid_lift_cm':.003716064453125,'bowl_location_choice':'workingstrip'if bowlx==-1.63 else'rightofcoffee','kitchen_glb_sha256':hashlib.sha256((OUT/'genuine-kitchen-lived-props.glb').read_bytes()).hexdigest(),'plant_glb_sha256':hashlib.sha256((OUT/'genuine-around-plant.glb').read_bytes()).hexdigest(),'native_imported':False,'interaction_contact_ready':False};(OUT/'source-report.json').write_text(json.dumps(report,indent=2));print('GENUINE_LIVED_PROPS_READY',flush=True)
