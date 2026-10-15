"""Private official manufacturer source inspection, no furniture geometry edits."""
import bpy,json,hashlib,math
from pathlib import Path
from mathutils import Vector,Matrix
ROOT=Path('/workspace/sub01-home-private/manufacturer-muuto-rest-r1');OUT=ROOT/'output-metric-uv-r2';OUT.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True);scene=bpy.context.scene
source=ROOT/'Rest-3-Seater-Wood-Base.obj'
bpy.ops.wm.obj_import(filepath=str(source),forward_axis='NEGATIVE_Z',up_axis='Y',use_split_objects=True,use_split_groups=True)
objects=[o for o in scene.objects if o.type=='MESH'];assert objects
proof=[]
for o in objects:
 proof.append({'name':o.name,'position_sha256':hashlib.sha256(str([tuple(v.co)for v in o.data.vertices]).encode()).hexdigest(),'vertices':len(o.data.vertices),'source_faces':len(o.data.polygons)})
 o.scale*=.001
bpy.context.view_layer.update();points=[o.matrix_world@v.co for o in objects for v in o.data.vertices];lo=Vector([min(p[i]for p in points)for i in range(3)]);hi=Vector([max(p[i]for p in points)for i in range(3)]);T=Matrix.Translation(Vector((-(lo.x+hi.x)/2,-(lo.y+hi.y)/2,-lo.z)))
for o in objects:o.matrix_world=T@o.matrix_world
# Manufacturer Rhino UVs have strongly stretched islands; reproject only
# the material coordinates metrically. Every source vertex/face stays intact.
# Photo tile width .25m is a documented review assumption, not a measured swatch.
for obj in objects:
 uv=obj.data.uv_layers.active or obj.data.uv_layers.new(name='MetricSourceCloth')
 for poly in obj.data.polygons:
  normal=(obj.matrix_world.to_3x3().inverted().transposed()@poly.normal).normalized();axis=max(range(3),key=lambda a:abs(normal[a]))
  for loop_index in poly.loop_indices:
   pos=obj.matrix_world@obj.data.vertices[obj.data.loops[loop_index].vertex_index].co
   uv.data[loop_index].uv=((pos.y,pos.z)if axis==0 else(pos.x,pos.z)if axis==1 else(pos.x,pos.y))
   uv.data[loop_index].uv/=.25
for m in bpy.data.materials:
 if not m.use_nodes:continue
 bs=next(n for n in m.node_tree.nodes if n.type=='BSDF_PRINCIPLED');bs.inputs['Metallic'].default_value=0;bs.inputs['Transmission Weight'].default_value=0;bs.inputs['Alpha'].default_value=1;bs.inputs['Roughness'].default_value=.78 if m.name=='hearth'else.38
 if 'Sheen Weight'in bs.inputs:bs.inputs['Sheen Weight'].default_value=0
 # The OBJ's legacy texture filenames differ from the archive's actual names.
 path=ROOT/('Hearth 6.jpg' if m.name=='hearth' else 'Oak.jpg')
 if m.name not in ('hearth','oak'):raise RuntimeError('Unknown manufacturer material '+m.name)
 image=bpy.data.images.load(str(path),check_existing=True);image.colorspace_settings.name='sRGB';tex=m.node_tree.nodes.new('ShaderNodeTexImage');tex.image=image;m.node_tree.links.new(tex.outputs['Color'],bs.inputs['Base Color'])
 # Real photographic weave drives a conservative material normal, no geometry.
 if m.name=='hearth':
  bump=m.node_tree.nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.12;bump.inputs['Distance'].default_value=.00015;m.node_tree.links.new(tex.outputs['Color'],bump.inputs['Height']);m.node_tree.links.new(bump.outputs['Normal'],bs.inputs['Normal'])
for o in objects:
 for p in o.data.polygons:p.use_smooth=True
for o in objects:o.select_set(True)
bpy.context.view_layer.objects.active=objects[0];bpy.ops.export_scene.gltf(filepath=str(OUT/'official-muuto-rest-3-source.glb'),export_format='GLB',use_selection=True,export_animations=False,export_apply=True)
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'official-muuto-rest-3-source.blend'))
bpy.ops.mesh.primitive_plane_add(size=8);plane=bpy.context.object;mat=bpy.data.materials.new('diagnostic floor');mat.diffuse_color=(.12,.12,.12,1);plane.data.materials.append(mat)
world=bpy.data.worlds.new('Neutral manufacturer source review');world.use_nodes=True;world.node_tree.nodes['Background'].inputs[1].default_value=.35;scene.world=world
for loc,power in [((1.2,-2.5,3),400),((-2,1.5,2.5),250)]:
 bpy.ops.object.light_add(type='AREA',location=loc);light=bpy.context.object;light.data.energy=power;light.data.size=2.5;light.rotation_euler=(Vector((0,0,.4))-light.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.object.camera_add(location=(2.8,-3.2,1.65));camera=bpy.context.object;camera.rotation_euler=(Vector((0,0,.35))-camera.location).to_track_quat('-Z','Y').to_euler();camera.data.type='ORTHO';camera.data.ortho_scale=2.9;scene.camera=camera
scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=16;scene.cycles.use_denoising=True;scene.render.resolution_x=960;scene.render.resolution_y=720;scene.render.resolution_percentage=100;scene.render.filepath=str(OUT/'official-muuto-rest-3-source.png');bpy.ops.render.render(write_still=True)
report={'schema':'sub01.official-manufacturer-source-review.v1','manufacturer':'Muuto','model':'Rest Sofa3Seater woodbase','source_archive_sha256':'fcfaf520cd9a48157bef3c3ef2a790a303f337e450fe028cbdb448eea47b1fff','license':'Official public architecture download; NOT asserted CC0','original_source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'source_parts':proof,'source_dimensions_m':list(hi-lo),'unit_conversion_mm_to_m':.001,'geometry_modified':False,'UV_modified':'world-metric dominant-axis projection; .25m photo tile review assumption; original Rhino coordinates retained in recoverable source','source_texture_names':['Hearth 6.jpg','Oak.jpg'],'material_normal':'0.15mm photographic texture bump/strength.12 for offline review; no geometry displacement','roughness':{'hearth':.78,'oak':.38},'native_imported':False,'output_sha256':hashlib.sha256((OUT/'official-muuto-rest-3-source.glb').read_bytes()).hexdigest()};(OUT/'source-report.json').write_text(json.dumps(report,indent=2));print('MUUTO_SOURCE_READY',report['output_sha256'],flush=True)
