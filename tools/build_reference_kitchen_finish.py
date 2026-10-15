"""Source-only warm oak/cream stone finish; original R7 geometry stays byte-exact.

Run Blender only on the authorized Runpod. The human's supplied kitchen image
is a styling reference, never used as a texture or described as a photograph.
"""
import bpy,sys,json,hashlib,copy,struct,math
from pathlib import Path
from mathutils import Vector
ROOT=Path('/workspace/sub01-home-private')
OLD=ROOT/'kitchen-lowerfit-source-20261015/output/native-kitchen.glb'
SHA='accd954c120a60f4eb68bd869fe2f1b578517880d71b82e673af5834c32fb79d'
OUT=ROOT/'reference-kitchen-finish-r2/output';OUT.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,'/home/unreal/runtime-tools')
from home_asset_audit import read_gltf
assert hashlib.sha256(OLD.read_bytes()).hexdigest()==SHA
original,blob=read_gltf(OLD);doc=copy.deepcopy(original)
# Existing photographed oak already has metric vertical UVs on the door fronts.
# Preserve UVs, all source vertices/indices/normals and all eight hinge matrices.
wood=doc['materials'][0];assert wood['name']=='SUB01_RealKitchen_CC0_Oak'
wood['name']='KFOak00';p=wood['pbrMetallicRoughness'];p['baseColorFactor']=[.38,.315,.235,1];p['roughnessFactor']=.70;wood['normalTexture']['scale']=.34
for i,m in enumerate(doc['materials'][1:],1):
 m['name']='KFMetal'+str(i);m['pbrMetallicRoughness'].update(baseColorFactor=[.016,.019,.021,1],metallicFactor=.30,roughnessFactor=.42)
def write_glb(path,d,b):
 text=json.dumps(d,separators=(',',':')).encode();text+=b' '*(-len(text)%4);b=bytes(b);b+=b'\0'*(-len(b)%4)
 path.write_bytes(struct.pack('<III',0x46546c67,2,12+8+len(text)+8+len(b))+struct.pack('<II',len(text),0x4e4f534a)+text+struct.pack('<II',len(b),0x004e4942)+b)
variant=OUT/'kitchen-finish-152.glb';write_glb(variant,doc,blob)
again,bb=read_gltf(variant);check=copy.deepcopy(again);check['materials']=copy.deepcopy(original['materials']);assert check==original and bytes(bb)==bytes(blob)
sourceproof={'schema':'sub01.reference-kitchen-finish-source.v1','actual_r7_source_sha256':SHA,'variant_sha256':hashlib.sha256(variant.read_bytes()).hexdigest(),'all_nonmaterial_gltf_json_exact':True,'all_binary_geometry_uv_images_exact':True,'eight_hinges_exact':True,'source_nodes_exact':len(original['nodes']),'source_meshes_exact':len(original['meshes']),'new_layout':False,'original_cook_sink_positions_unchanged':True,'material_changes':doc['materials'],'native_imported':False,'runtime_hinges_verified':False}
(OUT/'material-only-source-proof.json').write_text(json.dumps(sourceproof,indent=2)+'\n')
bpy.ops.wm.read_factory_settings(use_empty=True)
home='/workspace/sub01-private-recovered-project/Sub01HomeLab/SourceAssets/full-home.glb'
bpy.ops.import_scene.gltf(filepath=home)
# Frozen source node order survives import as exact names, with no new home layout.
hd,_=read_gltf(Path(home));by={o.name:o for o in bpy.context.scene.objects}
def original_node(i):
 name=hd['nodes'][i]['name'];matches=[o for o in bpy.context.scene.objects if o.type=='MESH'and o.name==name]
 assert len(matches)==1,(i,name,len(matches));return matches[0]
for i in(63,178,66):
 o=original_node(i);o.hide_render=True;o.hide_viewport=True
bpy.ops.import_scene.gltf(filepath=str(variant))
# Restore cabinet photo textures with a subtle satin finish in the actual scene.
mat=bpy.data.materials.new('KFCreamStone');mat.use_nodes=True
bs=mat.node_tree.nodes.get('Principled BSDF');bs.inputs['Base Color'].default_value=(.76,.738,.688,1);bs.inputs['Roughness'].default_value=.44
# The original slab and cutout stay geometrically identical; no fake slab over it.
slab=original_node(65);slab.data.materials.clear();slab.data.materials.append(mat)
black=bpy.data.materials.new('KFMatteBlackTap');black.use_nodes=True;bs=black.node_tree.nodes.get('Principled BSDF');bs.inputs['Base Color'].default_value=(.012,.016,.018,1);bs.inputs['Metallic'].default_value=.25;bs.inputs['Roughness'].default_value=.42
for i in(69,70,71):o=original_node(i);o.data.materials.clear();o.data.materials.append(black)
bpy.ops.object.select_all(action='DESELECT')
for i in(65,69,70,71):original_node(i).select_set(True)
bpy.context.view_layer.objects.active=slab
bpy.ops.export_scene.gltf(filepath=str(OUT/'counter-tap-finish.glb'),export_format='GLB',use_selection=True,export_cameras=False,export_lights=False)
# A manufactured under-cabinet U extrusion replaces the old 430mm-deep light box.
# 24x12mm channel, 1.2mm wall; fits 80mm behind the actual upper front doors.
metal=bpy.data.materials.new('KFLEDChannel');metal.use_nodes=True;s=metal.node_tree.nodes.get('Principled BSDF');s.inputs['Base Color'].default_value=(.11,.12,.13,1);s.inputs['Metallic'].default_value=.82;s.inputs['Roughness'].default_value=.36
em=bpy.data.materials.new('KFWarmDiffuser');em.use_nodes=True;s=em.node_tree.nodes.get('Principled BSDF');s.inputs['Base Color'].default_value=(1,.9,.73,1);s.inputs['Roughness'].default_value=.65;s.inputs['Emission Color'].default_value=(1,.724,.46,1);s.inputs['Emission Strength'].default_value=5
# Cross-section polygon is a real continuous U, rather than intersecting filler boxes.
profile=[(-.012,0),(.012,0),(.012,-.012),(.0108,-.012),(.0108,-.0012),(-.0108,-.0012),(-.0108,-.012),(-.012,-.012)]
vertices=[(x,3.61+y,1.699+z)for x in(-3.71,-.69)for y,z in profile];N=len(profile);faces=[tuple(range(N-1,-1,-1)),tuple(range(N,2*N))]+[(i,(i+1)%N,(i+1)%N+N,i+N)for i in range(N)]
mesh=bpy.data.meshes.new('KFLEDChannel');mesh.from_pydata(vertices,[],faces);mesh.update();channel=bpy.data.objects.new('KFLEDChannel',mesh);bpy.context.collection.objects.link(channel);channel.data.materials.append(metal)
bevel=channel.modifiers.new('Extrusion edge radius 0.3mm','BEVEL');bevel.width=.0003;bevel.segments=2;bpy.context.view_layer.objects.active=channel;channel.select_set(True);bpy.ops.object.modifier_apply(modifier=bevel.name);channel.select_set(False)
# Diffuser is a shaped acrylic cover. Separate end caps seal both profile ends.
ledparts=[channel]
def box(name,loc,dim,material,radius):
 bpy.ops.mesh.primitive_cube_add(size=1,location=loc);o=bpy.context.object;o.name=name;o.dimensions=dim;bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
 mod=o.modifiers.new('Manufactured edge radius','BEVEL');mod.width=radius;mod.segments=3;bpy.ops.object.modifier_apply(modifier=mod.name);o.data.materials.append(material);return o
ledparts.append(box('KFDiffuser',(-2.20,3.61,1.6875),(3.018,.020,.0018),em,.0005))
for x in(-3.7105,-.6895):ledparts.append(box('KFEndCap', (x,3.61,1.693),(.001,.024,.012),metal,.0003))
# Only this new measured LED assembly is exported. All existing cabinetwork uses
# the original byte-exact 152-part packet + per-component finish overrides.
bpy.ops.object.select_all(action='DESELECT')
for o in ledparts:o.select_set(True)
bpy.context.view_layer.objects.active=channel
led=OUT/'under-cabinet-led.glb';bpy.ops.export_scene.gltf(filepath=str(led),export_format='GLB',use_selection=True,export_cameras=False,export_lights=False)
finish={'schema':'sub01.reference-kitchen-finish-application.v1','source_sha256':SHA,'variant_sha256':sourceproof['variant_sha256'],'cabinet_152_geometry_replace':False,'cabinet_finish_only':True,'retained_source_nodes':{'65':'cream stone same slab and sink cutout','69':'matte black existing faucet spout','70':'matte black existing faucet base','71':'matte black existing lever'},'replace_old_light_visual_only':66,'new_led_sha256':hashlib.sha256(led.read_bytes()).hexdigest(),'led_source_bounds_m':[[-3.711,3.598,1.6858],[-.689,3.622,1.699]],'led_no_physics_required':True,'light':{'temperature_K':2900,'continuous_diffuser':True,'actual_source_emission_strength':5,'native_lighting_verified':False},'native_fixture_rebind_required_before_led_activation':True,'existing_66_fixture_runtime_preserved_until_verified_rebind':True,'counter_tap_sha256':hashlib.sha256((OUT/'counter-tap-finish.glb').read_bytes()).hexdigest(),'native_ready':False}
(OUT/'finish-application.json').write_text(json.dumps(finish,indent=2)+'\n')
# Actual full source scene, same home, same shelf/counter height, honest context.
for o in bpy.context.scene.objects:
 if o.type=='LIGHT':o.hide_render=True
world=bpy.data.worlds.new('Kitchen source daylight');world.use_nodes=True;world.node_tree.nodes['Background'].inputs[0].default_value=(.48,.52,.60,1);world.node_tree.nodes['Background'].inputs[1].default_value=.25;bpy.context.scene.world=world
for name,loc,power,size,target,color in [('Actual window soft daylight',(-1.8,1.4,2.4),250,2.4,(-2.2,3.6,1.3),(1,.95,.87)),('Interior warm bounce',(-.2,1.8,2.45),65,2,(-2.2,3.6,1.25),(1,.83,.64))]:
 bpy.ops.object.light_add(type='AREA',location=loc);o=bpy.context.object;o.name=name;o.data.energy=power;o.data.shape='DISK';o.data.size=size;o.data.color=color;o.rotation_euler=(Vector(target)-o.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.object.camera_add(location=(-1.95,.9,1.45));cam=bpy.context.object;cam.rotation_euler=(Vector((-2.2,3.58,1.25))-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.lens=26;bpy.context.scene.camera=cam
scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=16;scene.cycles.use_denoising=True;scene.render.threads_mode='FIXED';scene.render.threads=3;scene.render.resolution_x=1100;scene.render.resolution_y=825;scene.render.resolution_percentage=100;scene.render.image_settings.file_format='PNG';scene.view_settings.view_transform='AgX'
bpy.ops.file.pack_all();bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'reference-kitchen-finish.blend'))
scene.render.filepath=str(OUT/'reference-kitchen-full-source-review.png');bpy.ops.render.render(write_still=True)
print('SOURCE_FINISH_COMPLETE',json.dumps(sourceproof),flush=True)
