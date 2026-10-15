"""Private modern fallback: genuine Haven CC0 model, PBR recolor and authored pillows.
No base-sofa remeshing, deformation, new procedural furniture or fake block props.
"""
import bpy,json,math,hashlib
from pathlib import Path
from mathutils import Vector,Matrix
ROOT=Path('/workspace/sub01-home-private/reference-gaming-lounge-r1');OUT=ROOT/'haven-output-r2';OUT.mkdir(parents=True,exist_ok=True);SOURCE=Path('/home/unreal/runtime-tools/gaming-haven-source.glb')
PALETTE=json.loads((ROOT/'haven-palette-r2/palette.json').read_text())
assert hashlib.sha256(SOURCE.read_bytes()).hexdigest()=='acad7fd3d9431929c303b1ae5cd476d7a108ce352a99ddf40e4e78ea7b9f2643'
bpy.ops.wm.read_factory_settings(use_empty=True);scene=bpy.context.scene;bpy.ops.import_scene.gltf(filepath=str(SOURCE));base=sorted([o for o in scene.objects if o.type=='MESH'],key=lambda o:o.name);assert len(base)==27

def bounds(obs):
 pts=[o.matrix_world@v.co for o in obs for v in o.data.vertices];return [[min(v[i]for v in pts)for i in range(3)],[max(v[i]for v in pts)for i in range(3)]]
def signature(obj):return hashlib.sha256(str([tuple(v.co)for v in obj.data.vertices]).encode()).hexdigest()
def tint(material,name,color):
 mat=material.copy();mat.name=name;mat.use_nodes=True;shader=next(n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED');socket=shader.inputs['Base Color']
 if socket.is_linked:
  role='Gray'if name.startswith('GamingPillow_0_')else'Accent'if name.startswith('GamingPillow_1_')else'Navy';palette=PALETTE['maps'][role];path=Path(palette['path']);assert hashlib.sha256(path.read_bytes()).hexdigest()==palette['sha256']
  for link in list(socket.links):mat.node_tree.links.remove(link)
  image=bpy.data.images.load(str(path),check_existing=True);image.colorspace_settings.name='sRGB';texture=mat.node_tree.nodes.new('ShaderNodeTexImage');texture.image=image;mat.node_tree.links.new(texture.outputs['Color'],socket)
  # Source white sheen was appropriate to oatmeal, but washes a dark dye out.
  # Tint it to the actual decoded dyed texture mean; same source roughness,
  # normal, sheen roughness and UV mapping remain untouched.
  if 'Sheen Tint'in shader.inputs:
   for link in list(shader.inputs['Sheen Tint'].links):mat.node_tree.links.remove(link)
   shader.inputs['Sheen Tint'].default_value=(*palette['sheen_linear_mean'],1)
 else:socket.default_value=(*color,1)
 return mat
# Copy the actual original three-piece feather cushion/welt assembly before
# recoloring the full base. Each lumbar pillow remains a rigid .58 source copy.
authored=[o for o in base if o.name.startswith('Left | feather back cushion')];assert len(authored)==3
pillows=[];pillow_proof=[]
for index,(x,y,angle,color)in enumerate([(-.53,-.10,.09,(.65,.70,.76)),(.56,-.09,-.12,(.011,.04,.095))]):
 copies=[];original_bounds=bounds(authored);origin=Vector(((original_bounds[0][0]+original_bounds[1][0])/2,(original_bounds[0][1]+original_bounds[1][1])/2,original_bounds[0][2]));local=Matrix.Translation(Vector((x,y,.510)))@Matrix.Rotation(angle,4,'Z')@Matrix.Scale(.58,4)@Matrix.Translation(-origin)
 for j,source in enumerate(authored):
  obj=source.copy();obj.data=source.data.copy();scene.collection.objects.link(obj);world=source.matrix_world.copy();obj.parent=None;obj.matrix_world=local@world;obj.name='GamingLoosePillow_'+str(index).zfill(2)+'_'+str(j).zfill(3);obj.data.name=obj.name+'_Mesh';assert signature(obj)==signature(source)
  for slot in obj.material_slots:
   if slot.material:slot.material=tint(slot.material,'GamingPillow_'+str(index)+'_'+str(j),color)
  copies.append(obj)
 pillows+=copies;pillow_proof.append({'source_components':[o.name for o in authored],'rigid_uniform_scale':.58,'source_position_attributes_exact':True,'copies':[o.name for o in copies]})
materials={}
for obj in base:
 for slot in obj.material_slots:
  mat=slot.material
  if mat and ('Oatmeal'in mat.name or 'Linen cord'in mat.name):
   if mat.name not in materials:materials[mat.name]=tint(mat,'GamingNavy_'+str(len(materials)),(.07,.11,.17)if'Oatmeal'in mat.name else(.03,.045,.07))
   slot.material=materials[mat.name]
old_bounds=bounds(base);origin=Vector(((old_bounds[0][0]+old_bounds[1][0])/2,(old_bounds[0][1]+old_bounds[1][1])/2,old_bounds[0][2]));T=Matrix.Translation(Vector((-1.445,-.10,.02505)))@Matrix.Rotation(-math.pi/2,4,'Z')@Matrix.Translation(-origin)
proof=[]
for i,obj in enumerate(base):
 original=signature(obj);world=obj.matrix_world.copy();obj.parent=None;obj.matrix_world=T@world;obj.name='GamingHaven_'+str(i).zfill(3);obj.data.name=obj.name+'_Mesh';assert signature(obj)==original;proof.append({'node':obj.name,'source_local_vertex_signature':original,'local_geometry_exact':True})
for obj in pillows:obj.matrix_world=T@obj.matrix_world
bpy.context.view_layer.update();source_objects=base+pillows
# Grouping by retained material is left explicit in source; importer may join
# static same-PBR groups with independent world-corner verification.
bpy.ops.object.select_all(action='DESELECT')
for obj in source_objects:obj.select_set(True)
bpy.context.view_layer.objects.active=base[0];bpy.ops.export_scene.gltf(filepath=str(OUT/'genuine-navy-haven-with-pillows.glb'),export_format='GLB',use_selection=True,export_animations=False,export_apply=True);bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'genuine-navy-haven-with-pillows.blend'))
world_pts=[o.matrix_world@v.co for o in source_objects for v in o.data.vertices];ue=[Vector((p.x,-p.y,p.z))*100 for p in world_pts];ue_bounds=[[min(p[i]for p in ue)for i in range(3)],[max(p[i]for p in ue)for i in range(3)]]
# Add the separately approved real table/controller for a coherent source view.
# The Haven-only export above remains independently integrable.
combined_table=ROOT/'table-output/genuine-coffee-table-with-controller.glb'
assert combined_table.is_file();before=set(bpy.data.objects);bpy.ops.import_scene.gltf(filepath=str(combined_table));table_objects=[o for o in set(bpy.data.objects)-before if o.type=='MESH']
bpy.ops.object.select_all(action='DESELECT')
for o in source_objects+table_objects:o.select_set(True)
bpy.context.view_layer.objects.active=base[0];bpy.ops.export_scene.gltf(filepath=str(OUT/'genuine-gaming-lounge-combined.glb'),export_format='GLB',use_selection=True,export_animations=False,export_apply=True)
# Neutral diagnostic stage only. It is never exported with the furniture.
bpy.ops.mesh.primitive_plane_add(size=10,location=(-1.5,0,.025));stage=bpy.context.object;mat=bpy.data.materials.new('Neutral source stage');mat.diffuse_color=(.14,.14,.15,1);stage.data.materials.append(mat)
world=bpy.data.worlds.new('Source studio');world.use_nodes=True;world.node_tree.nodes['Background'].inputs[1].default_value=.35;scene.world=world
for loc,power in[((-3.2,-2.4,3),420),((.2,2.8,2.6),250)]:
 bpy.ops.object.light_add(type='AREA',location=loc);o=bpy.context.object;o.data.energy=power;o.data.size=2.6;o.rotation_euler=(Vector((-1.4,0,.6))-o.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.object.camera_add(location=(-4.4,-3.2,2.1));camera=bpy.context.object;scene.camera=camera;camera.rotation_euler=(Vector((-1.445,0,.5))-camera.location).to_track_quat('-Z','Y').to_euler();camera.data.type='ORTHO';camera.data.ortho_scale=3.9
scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=16;scene.cycles.use_denoising=True;scene.render.resolution_x=960;scene.render.resolution_y=720;scene.render.resolution_percentage=100;scene.render.image_settings.file_format='PNG';scene.view_settings.view_transform='AgX';scene.render.filepath=str(OUT/'genuine-navy-haven-source-review.png');bpy.ops.render.render(write_still=True)
report={'schema':'sub01.genuine-haven-gaming-source.v1','source':'https://www.innerscene.com/tools/library/3d-parts/haven-224-oatmeal-two-seat-sofa-40262c27','license':'CC0-1.0','original_source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'source_model_is_authored_not_claimed_photogrammetry':True,'base_source_local_geometry_exact':proof,'pillows_from_genuine_original_feather_cushion_and_welts':pillow_proof,'base_physical_dimensions_unchanged':True,'navy_material_change':'portable dyed albedo with source luminance variation; white oatmeal sheen tint replaced by decoded dyed albedo mean; original linen UVs/roughness/normals retained','portable_palette_proof':PALETTE,'combined_table_source_sha256':hashlib.sha256(combined_table.read_bytes()).hexdigest(),'world_bounds_UE_cm':ue_bounds,'floor_feet_bottom_cm':2.505,'seat_surface_requires_new_actual_binding':True,'retire_only_original_sofa_nodes':[172,173,174,175],'source_output_sha256':hashlib.sha256((OUT/'genuine-navy-haven-with-pillows.glb').read_bytes()).hexdigest(),'active_Game_or_input_changed':False,'native_imported':False,'seating_contact_ready':False};(OUT/'haven-source-report.json').write_text(json.dumps(report,indent=2));print('GENUINE_HAVEN_READY',report['source_output_sha256'],flush=True)
