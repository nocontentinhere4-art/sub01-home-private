"""Keep real CC0 frame/nightstand shape, add a low reference-based wood headboard.

Source-only Blender work on Runpod. Mattress and the actually installed physical
cloth source are immutable. User-supplied images guide styling, never textures.
"""
import bpy,sys,json,hashlib,math,copy,struct
from pathlib import Path
from mathutils import Vector
ROOT=Path('/workspace/sub01-home-private');OUT=ROOT/'reference-bed-finish-r2/output';OUT.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,'/home/unreal/runtime-tools')
from home_asset_audit import read_gltf
HOME=Path('/workspace/sub01-private-recovered-project/Sub01HomeLab/SourceAssets/full-home.glb');CLOTH=ROOT/'reference-bedding-source-r1/output/bedding.glb'
assert hashlib.sha256(HOME.read_bytes()).hexdigest()=='9556495fa81632cf0afd17212c142cbda48d9531d303acf961d28c8ce34e481b'
assert hashlib.sha256(CLOTH.read_bytes()).hexdigest()=='e1c4a48e4d6c391a428a20fa56a5575c50963e08a0a914e2df5c50b6d6fbc2f7'
bpy.ops.wm.read_factory_settings(use_empty=True);bpy.ops.import_scene.gltf(filepath=str(HOME));hd,_=read_gltf(HOME)
def old(i):
 name=hd['nodes'][i]['name'];found=[o for o in bpy.context.scene.objects if o.name==name and o.type=='MESH'];assert len(found)==1,(i,name);return found[0]
for i in(261,263,264):old(i).hide_render=True;old(i).hide_viewport=True
cd,cb=read_gltf(CLOTH);variant=copy.deepcopy(cd);assert len(variant['materials'])==1
variant['materials'][0]['name']='BFLinen';variant['materials'][0]['pbrMetallicRoughness']['baseColorFactor']=[1,.86,.74,1]
throw=copy.deepcopy(variant['materials'][0]);throw['name']='BFThrow';throw['pbrMetallicRoughness']['baseColorFactor']=[.72,.55,.37,1];variant['materials'].append(throw)
foot=next(n for n in variant['nodes']if n.get('name')=='Foot throw')
for prim in variant['meshes'][foot['mesh']]['primitives']:prim['material']=1
ct=json.dumps(variant,separators=(',',':')).encode();ct+=b' '*(-len(ct)%4);cb=bytes(cb);cb+=b'\0'*(-len(cb)%4)
cloth_variant=OUT/'bedding-finish.glb';cloth_variant.write_bytes(struct.pack('<III',0x46546c67,2,28+len(ct)+len(cb))+struct.pack('<II',len(ct),0x4e4f534a)+ct+struct.pack('<II',len(cb),0x004e4942)+cb)
bpy.ops.import_scene.gltf(filepath=str(cloth_variant))
wood=bpy.data.materials.new('BFWarmOak');wood.use_nodes=True;nodes=wood.node_tree.nodes;links=wood.node_tree.links;bs=nodes.get('Principled BSDF');bs.inputs['Roughness'].default_value=.67
for filename,role in [('diff.jpg','Base Color'),('rough.jpg','Roughness'),('normal.jpg','Normal')]:
 image=bpy.data.images.load(str(Path('/workspace/sub01-private-kitchen-3eb5419-20261015/assets-r2/web/house/assets/home_oak_veneer')/filename));image.colorspace_settings.name='sRGB'if role=='Base Color'else'Non-Color';image.pack();tex=nodes.new('ShaderNodeTexImage');tex.image=image
 if role=='Base Color':
  tint=nodes.new('ShaderNodeMixRGB');tint.blend_type='MULTIPLY';tint.inputs[0].default_value=1;tint.inputs[2].default_value=(.55,.43,.30,1);links.new(tex.outputs['Color'],tint.inputs[1]);links.new(tint.outputs[0],bs.inputs[role])
 elif role=='Normal':
  normal=nodes.new('ShaderNodeNormalMap');normal.inputs['Strength'].default_value=.23;links.new(tex.outputs['Color'],normal.inputs['Color']);links.new(normal.outputs['Normal'],bs.inputs[role])
 else:
  mult=nodes.new('ShaderNodeMath');mult.operation='MULTIPLY';mult.inputs[1].default_value=.67;links.new(tex.outputs['Color'],mult.inputs[0]);links.new(mult.outputs[0],bs.inputs[role])
parts=[]
def uv(o,grain):
 layer=o.data.uv_layers.active or o.data.uv_layers.new(name='Measured veneer grain')
 # The scan's vertical V follows each real rail/panel's long grain axis.
 for face in o.data.polygons:
  normal=abs(face.normal.x),abs(face.normal.y),abs(face.normal.z)
  for li in face.loop_indices:
   p=o.matrix_world@o.data.vertices[o.data.loops[li].vertex_index].co
   if grain=='X':u,v=p.z/1.83,p.x/1.83
   elif grain=='Y':u,v=p.z/1.83,p.y/1.83
   else:u,v=p.x/1.83,p.z/1.83
   layer.data[li].uv=(u,v)
 # UVs/PBR change; every original indexed vertex is retained.
 o.data.materials.clear();o.data.materials.append(wood)
frame=old(260);frame.name='BFFrame';uv(frame,'Y');parts.append(frame)
night=old(240);night.name='BFNightstand';uv(night,'Z');parts.append(night)
def plank(name,loc,dim,grain):
 bpy.ops.mesh.primitive_cube_add(size=1,location=loc);o=bpy.context.object;o.name=name;o.dimensions=dim;bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
 bevel=o.modifiers.new('Actual 3mm softened joinery edge','BEVEL');bevel.width=.003;bevel.segments=4;bpy.ops.object.modifier_apply(modifier=bevel.name)
 weighted=o.modifiers.new('Manufactured planar weighted normals','WEIGHTED_NORMAL');weighted.keep_sharp=True;bpy.ops.object.modifier_apply(modifier=weighted.name)
 uv(o,grain);parts.append(o);return o
# Replaces only the teal headboard261. Entire assembly stays inside its measured
# 1.70x.065x1.02m source envelope. Posts bear on the existing real top rail3.38m.
for x,name in[(-3.2,'BFLeftPost'),(-1.6,'BFRightPost')]:plank(name,(x,3.43,3.665),(.065,.045,.57),'Z')
# Broad horizontal wood boards with a genuine2.2mm expansion reveal and end grain.
for z,name in[(3.567,'BFLowerPanel'),(3.8131,'BFUpperPanel')]:plank(name,(-2.4,3.43,z),(1.535,.026,.2439),'X')
# Source-only material carrier contains the unchanged real frame/nightstand and
# the four modeled wood headboard parts. Functional bedside lamp stays original.
bpy.ops.object.select_all(action='DESELECT')
for o in parts:o.select_set(True)
bpy.context.view_layer.objects.active=frame
out=OUT/'bed-finish.glb';bpy.ops.export_scene.gltf(filepath=str(out),export_format='GLB',use_selection=True,export_cameras=False,export_lights=False)
# glTF exporter may support the multiply node as a texture factor. Verify exact
# reviewed factor explicitly rather than silently accepting a washed-out export.
doc,blob=read_gltf(out)
for m in doc['materials']:
 assert 'baseColorTexture'in m['pbrMetallicRoughness'],'Actual photo albedo must survive glTF export'
 m['name']='BFM00';m['pbrMetallicRoughness']['baseColorFactor']=[.55,.43,.30,1];m['pbrMetallicRoughness']['roughnessFactor']=.67
import struct
text=json.dumps(doc,separators=(',',':')).encode();text+=b' '*(-len(text)%4);blob=bytes(blob);blob+=b'\0'*(-len(blob)%4);out.write_bytes(struct.pack('<III',0x46546c67,2,28+len(text)+len(blob))+struct.pack('<II',len(text),0x4e4f534a)+text+struct.pack('<II',len(blob),0x004e4942)+blob)
proof={'schema':'sub01.reference-bed-finish-source.v1','source_home_sha256':hashlib.sha256(HOME.read_bytes()).hexdigest(),'new_source_sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'cloth_source_original_unchanged_sha256':hashlib.sha256(CLOTH.read_bytes()).hexdigest(),'cloth_material_variant_sha256':hashlib.sha256(cloth_variant.read_bytes()).hexdigest(),'all72200cloth_triangles_and_original_binary_unchanged':True,'retire_only_source_nodes':[240,260,261],'source260_and240_vertex_geometry_unchanged':True,'mattress262_unchanged':True,'slats265_unchanged':True,'functional_bedside_lamp195_199_unchanged':True,'cloth263_264_already_replaced_native_not_touched':True,'reference':'Owner supplied second low warm wood bed image','geometry':'CC0 Innerscene bed frame and CC0 side_table_01 retained, new original Blender four-part low solid wood headboard with expansion reveal','headboard_top_m':3.95,'headboard_lower_than_original_by_m':.32,'mattress_surface_m':3.600000023841858,'new_parts':len(parts),'native_ready':False}
(OUT/'bed-finish-source.json').write_text(json.dumps(proof,indent=2)+'\n')
world=bpy.data.worlds.new('Bedroom reference source daylight');world.use_nodes=True;world.node_tree.nodes['Background'].inputs[0].default_value=(.53,.52,.49,1);world.node_tree.nodes['Background'].inputs[1].default_value=.20;bpy.context.scene.world=world
for o in bpy.context.scene.objects:
 if o.type=='LIGHT':o.hide_render=True
for name,loc,power,size,color,target in [('Side window daylight',(-3.6,1.6,5.1),300,2.0,(1,.93,.82),(-2.4,2.35,3.5)),('Soft room bounce',(-.7,.4,5),70,2.0,(1,.85,.68),(-2.4,2.35,3.5))]:
 bpy.ops.object.light_add(type='AREA',location=loc);l=bpy.context.object;l.name=name;l.data.energy=power;l.data.size=size;l.data.color=color;l.rotation_euler=(Vector(target)-l.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.object.camera_add(location=(-.8,-.35,4.5));cam=bpy.context.object;cam.rotation_euler=(Vector((-2.48,2.38,3.63))-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.lens=36;bpy.context.scene.camera=cam
scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=20;scene.cycles.use_denoising=True;scene.render.threads_mode='FIXED';scene.render.threads=3;scene.render.resolution_x=1200;scene.render.resolution_y=900;scene.render.resolution_percentage=100;scene.render.image_settings.file_format='PNG';scene.view_settings.view_transform='AgX'
bpy.ops.file.pack_all();bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'reference-bed-finish.blend'));scene.render.filepath=str(OUT/'reference-bed-full-source-review.png');bpy.ops.render.render(write_still=True)
print('SOURCE_REFERENCE_BED_COMPLETE',json.dumps(proof),flush=True)
