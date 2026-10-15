"""Separate approved genuine CC0 table and verified display-controller source packet."""
import bpy,json,math,hashlib
from pathlib import Path
from mathutils import Vector,Matrix
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree
ROOT=Path('/workspace/sub01-home-private/reference-gaming-lounge-r1');OUT=ROOT/'table-output';OUT.mkdir(parents=True,exist_ok=True);TABLE=ROOT/'assets/modern_coffee_table_01/modern_coffee_table_01.gltf';CONTROLLER=Path('/workspace/sub01-home-private/reference-controller-r11/output/controller-r11-display-lod.glb')
assert hashlib.sha256(CONTROLLER.read_bytes()).hexdigest()=='1a312ae7bdafd73d837a96b0562d5467624abd2bc0b163856bbb7422f9a11e7e'
manifest=json.loads((ROOT/'source-manifest.json').read_text());entry=next(a for a in manifest if a['asset']=='modern_coffee_table_01')
for f in entry['files']:assert hashlib.sha256((ROOT/'assets'/f['file']).read_bytes()).hexdigest()==f['sha256']
bpy.ops.wm.read_factory_settings(use_empty=True);scene=bpy.context.scene

def points(objects):return [o.matrix_world@v.co for o in objects for v in o.data.vertices]
def bounds(objects):
 p=points(objects);return [[min(v[i]for v in p)for i in range(3)],[max(v[i]for v in p)for i in range(3)]]
def load(path):
 before=set(bpy.data.objects);bpy.ops.import_scene.gltf(filepath=str(path));obs=sorted([o for o in set(bpy.data.objects)-before if o.type=='MESH'],key=lambda o:o.name)
 for o in obs:m=o.matrix_world.copy();o.parent=None;o.matrix_world=m
 return obs
def place(obs,x,y,bottom,angle):
 b=bounds(obs);origin=Vector(((b[0][0]+b[1][0])/2,(b[0][1]+b[1][1])/2,b[0][2]));T=Matrix.Translation(Vector((x,y,bottom)))@Matrix.Rotation(angle,4,'Z')@Matrix.Translation(-origin)
 for o in obs:o.matrix_world=T@o.matrix_world
 bpy.context.view_layer.update()
def export(obs,path):
 bpy.ops.object.select_all(action='DESELECT')
 for o in obs:o.select_set(True)
 bpy.context.view_layer.objects.active=obs[0];bpy.ops.export_scene.gltf(filepath=str(path),export_format='GLB',use_selection=True,export_animations=False,export_apply=True)
def ue_bounds(obs):
 p=[Vector((p.x,-p.y,p.z))*100 for p in points(obs)];return [[min(v[i]for v in p)for i in range(3)],[max(v[i]for v in p)for i in range(3)]]
table=load(TABLE);assert len(table)==1;table[0].name='GamingCoffeeTable_000';table[0].data.name='GamingCoffeeTable_Mesh_000';place(table,-2.59,.05,.02505,0);tb=bounds(table);assert abs((tb[1][2]-tb[0][2])-.39)<1.e-5;export(table,OUT/'genuine-coffee-table.glb')
(OUT/'table-only-source-report.json').write_text(json.dumps({'schema':'sub01.genuine-coffee-table-source.v1','source':entry,'table_world_bounds_UE_cm':ue_bounds(table),'floor_feet_bottom_cm':2.505,'source_physical_dimensions_preserved_1_to_1':True,'table_node':'GamingCoffeeTable_000','retire_only_original_table_node':275,'source_output_sha256':hashlib.sha256((OUT/'genuine-coffee-table.glb').read_bytes()).hexdigest(),'native_imported':False,'source_vertex_count':len(table[0].data.vertices)},indent=2))
controller=load(CONTROLLER);cb=bounds(controller);assert .12<cb[1][0]-cb[0][0]<.20;place(controller,-2.58,-.22,tb[1][2],.30)
# Join by existing PBR assignment only, preserving every actual world-space
# source vertex to <=1 micrometre; no remeshing, decimation or new prop geometry.
source=points(controller);original_count=len(source);groups={}
for o in controller:
 assert len(o.data.materials)>=1 and all(o.data.materials),o.name
 # R11 is already a single source mesh with six genuine PBR sections.
 # Preserve its material slots; no unnecessary regrouping or fake default slot.
 key=tuple(m.name for m in o.data.materials)
 groups.setdefault(key,[]).append(o)
merged=[]
for i,(material,objects)in enumerate(sorted(groups.items())):
 bpy.ops.object.select_all(action='DESELECT')
 for o in objects:o.select_set(True)
 bpy.context.view_layer.objects.active=objects[0]
 if len(objects)>1:bpy.ops.object.join()
 o=bpy.context.view_layer.objects.active;o.name='GamingDisplayController_'+str(i).zfill(3);o.data.name=o.name+'_Mesh';merged.append(o)
assert len(points(merged))==original_count
kd=KDTree(original_count)
for i,p in enumerate(points(merged)):kd.insert(p,i)
kd.balance();error=max(kd.find(p)[2]for p in source);assert error<=1.e-6,error
# Exact existing controller bottom rests on measured genuine table surface.
mesh=table[0].data;mesh.calc_loop_triangles();tree=BVHTree.FromPolygons([table[0].matrix_world@v.co for v in mesh.vertices],[tuple(t.vertices)for t in mesh.loop_triangles],all_triangles=True,epsilon=0);low=min(points(merged),key=lambda p:p.z);hit,normal,index,distance=tree.ray_cast(low+Vector((0,0,.02)),Vector((0,0,-1)),.1);assert hit is not None;gap=low.z-hit.z;assert abs(gap)<1.e-5,gap
export(merged,OUT/'genuine-display-controller.glb');export(table+merged,OUT/'genuine-coffee-table-with-controller.glb');bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'genuine-coffee-table-with-controller.blend'))
# Neutral source stage is not exported or represented as the actual house.
bpy.ops.mesh.primitive_plane_add(size=10,location=(-2.5,0,.025));stage=bpy.context.object;stage.name='REVIEW_ONLY';mat=bpy.data.materials.new('Source studio floor');mat.diffuse_color=(.15,.15,.15,1);stage.data.materials.append(mat)
world=bpy.data.worlds.new('Source studio');world.use_nodes=True;world.node_tree.nodes['Background'].inputs[1].default_value=.35;scene.world=world
for loc,power in[((-3.3,-1.5,2.8),350),((-1,2,2),200)]:
 bpy.ops.object.light_add(type='AREA',location=loc);o=bpy.context.object;o.data.energy=power;o.data.size=2;o.rotation_euler=(Vector((-2.59,0,.3))-o.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.object.camera_add(location=(-4,-1.8,1.6));camera=bpy.context.object;scene.camera=camera;camera.rotation_euler=(Vector((-2.59,0,.3))-camera.location).to_track_quat('-Z','Y').to_euler();camera.data.type='ORTHO';camera.data.ortho_scale=1.8
scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=24;scene.cycles.use_denoising=True;scene.render.resolution_x=1280;scene.render.resolution_y=960;scene.render.resolution_percentage=100;scene.render.image_settings.file_format='PNG';scene.view_settings.view_transform='AgX';scene.render.filepath=str(OUT/'genuine-table-controller-source-review.png');bpy.ops.render.render(write_still=True)
report={'schema':'sub01.genuine-coffee-table-controller-source.v1','table_source':entry,'controller_source_sha256':hashlib.sha256(CONTROLLER.read_bytes()).hexdigest(),'table_world_bounds_UE_cm':ue_bounds(table),'controller_world_bounds_UE_cm':ue_bounds(merged),'controller_joined_PBR_groups':len(merged),'controller_original_vertices_preserved':original_count,'controller_world_vertex_max_error_m':error,'controller_support_witness':{'controller_lowest_glTF_to_Blender_point_m':list(low),'actual_table_triangle':index,'actual_table_hit_Blender_m':list(hit),'vertical_gap_m':gap},'table_physical_dimensions_preserved_1_to_1':True,'new_feet_bottom_cm':2.505,'retire_only_original_table_node':275,'old_source_sha256':'9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b','actual_Game_or_guest_or_input_changed':False,'native_imported':False,'display_controller_is_source_WIP':True,'controller_hand_contact_ready':False,'source_outputs':{p.name:hashlib.sha256(p.read_bytes()).hexdigest()for p in OUT.glob('*.glb')}};(OUT/'table-source-report.json').write_text(json.dumps(report,indent=2));print('GENUINE_TABLE_PACKET_READY',json.dumps(report['source_outputs']),flush=True)
