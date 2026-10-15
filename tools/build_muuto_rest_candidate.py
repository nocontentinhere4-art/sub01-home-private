"""Private official Muuto Rest source, material-only changes + rigid house fit."""
import bpy,json,hashlib,math
from pathlib import Path
from mathutils import Vector,Matrix
ROOT=Path('/workspace/sub01-home-private/manufacturer-muuto-rest-r1');OUT=ROOT/'candidate-r3';OUT.mkdir(exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(ROOT/'output-metric-uv-r2/official-muuto-rest-3-source.blend'));scene=bpy.context.scene;original=[o for o in scene.objects if o.type=='MESH'];assert len(original)==1
before=[o.matrix_world@v.co for o in original for v in o.data.vertices];normal=ROOT/'Hearth6-derived-normal.png'
mat=bpy.data.materials['hearth'];bs=next(n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
for link in list(bs.inputs['Normal'].links):mat.node_tree.links.remove(link)
tex=mat.node_tree.nodes.new('ShaderNodeTexImage');tex.image=bpy.data.images.load(str(normal),check_existing=True);tex.image.colorspace_settings.name='Non-Color';nm=mat.node_tree.nodes.new('ShaderNodeNormalMap');mat.node_tree.links.new(tex.outputs['Color'],nm.inputs['Color']);mat.node_tree.links.new(nm.outputs['Normal'],bs.inputs['Normal'])
# Fit rigidly: front−179.5cm; preserve the full actual manufacturer depth.
depth=max(v.y for v in before)-min(v.y for v in before);cx=-1.795+depth/2
T=Matrix.Translation(Vector((cx,-.1,.02505)))@Matrix.Rotation(-math.pi/2,4,'Z')
for o in original:o.matrix_world=T@o.matrix_world
# Split exact original material primitives only; no remesh/bevel/surface edits.
bpy.ops.object.select_all(action='DESELECT');o=original[0];o.select_set(True);bpy.context.view_layer.objects.active=o;bpy.ops.object.mode_set(mode='EDIT');bpy.ops.mesh.select_all(action='SELECT');bpy.ops.mesh.separate(type='MATERIAL');bpy.ops.object.mode_set(mode='OBJECT')
parts=sorted([o for o in scene.objects if o.type=='MESH'],key=lambda o:o.material_slots[0].material.name);assert len(parts)==2
for i,o in enumerate(parts):o.name=f'MuutoRest_{i:03}';o.data.name=o.name+'_Mesh';assert len(o.material_slots)==1
bpy.ops.object.select_all(action='DESELECT')
for o in parts:o.select_set(True)
bpy.context.view_layer.objects.active=parts[0];bpy.ops.export_scene.gltf(filepath=str(OUT/'muuto-rest-3-candidate.glb'),export_format='GLB',use_selection=True,export_animations=False,export_apply=True)
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'muuto-rest-3-candidate.blend'))
world=[o.matrix_world@v.co for o in parts for v in o.data.vertices];bounds=[[min(p[i]for p in world)for i in range(3)],[max(p[i]for p in world)for i in range(3)]]
# The separately genuine Around source retains exact physical dimensions.
around=Path('/workspace/sub01-home-private/manufacturer-around-large-r1/placed-dark-r3/muuto-around-large-dark.glb');assert hashlib.sha256(around.read_bytes()).hexdigest()=='34c7b528c0587426ab847bd202007c4365a959023f40b2150ebff730540947c5'
old=set(bpy.data.objects);bpy.ops.import_scene.gltf(filepath=str(around));tables=[o for o in set(bpy.data.objects)-old if o.type=='MESH']
for o in tables:pass # already in exact final placement
bpy.context.view_layer.update();bpy.ops.object.select_all(action='DESELECT')
for o in parts+tables:o.select_set(True)
bpy.context.view_layer.objects.active=parts[0];bpy.ops.export_scene.gltf(filepath=str(OUT/'muuto-rest-around-combined.glb'),export_format='GLB',use_selection=True,export_animations=False,export_apply=True)
bpy.ops.mesh.primitive_plane_add(size=10,location=(-1.7,0,.025));plane=bpy.context.object;m=bpy.data.materials.new('source floor');m.diffuse_color=(.12,.12,.12,1);plane.data.materials.append(m)
worldlight=bpy.data.worlds.new('Muuto source light');worldlight.use_nodes=True;worldlight.node_tree.nodes['Background'].inputs[1].default_value=.35;scene.world=worldlight
for loc,power in [((-3.2,-2.4,3),420),((.2,2.8,2.6),250)]:
 bpy.ops.object.light_add(type='AREA',location=loc);light=bpy.context.object;light.data.energy=power;light.data.size=2.6;light.rotation_euler=(Vector((-1.6,0,.4))-light.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.object.camera_add(location=(-4.5,-3.1,2));camera=bpy.context.object;camera.rotation_euler=(Vector((-1.7,0,.35))-camera.location).to_track_quat('-Z','Y').to_euler();camera.data.type='ORTHO';camera.data.ortho_scale=3.5;scene.camera=camera
scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=16;scene.cycles.use_denoising=True;scene.render.resolution_x=960;scene.render.resolution_y=720;scene.render.resolution_percentage=100;scene.render.filepath=str(OUT/'muuto-rest-around-source-review.png');bpy.ops.render.render(write_still=True)
report={'schema':'sub01.muuto-rest-candidate.v1','source_original_obj_sha256':'0d4a22c20014c5b699e60fd1b2452359272bbe4e41e5f9b81d825d802ca8c1ee','source_archive_sha256':'fcfaf520cd9a48157bef3c3ef2a790a303f337e450fe028cbdb448eea47b1fff','source_author':'Muuto official manufacturer architecture download, not CC0','geometry_edits':'NONE: original surface/face partition and rigid mm→m fit only','source_vertex_count':4083,'source_polygon_faces':4879,'parts':[o.name for o in parts],'materials':[o.material_slots[0].material.name for o in parts],'bounds_Blender_m':bounds,'bounds_UE_cm':[[bounds[0][0]*100,-bounds[1][1]*100,bounds[0][2]*100],[bounds[1][0]*100,-bounds[0][1]*100,bounds[1][2]*100]],'source_photographs':['Hearth 6.jpg','Oak.jpg'],'normal_texture_derived_from_actual_photo':{'tile_review_assumption_m':.25,'height_strength_m':.000018,'sha256':hashlib.sha256(normal.read_bytes()).hexdigest()},'sofa_glb_sha256':hashlib.sha256((OUT/'muuto-rest-3-candidate.glb').read_bytes()).hexdigest(),'around_source_sha256':hashlib.sha256(around.read_bytes()).hexdigest(),'around_candidate_translation_UE_cm':[0,0,0],'retire_only_whole_original_sofa_actors':[172,173,174,175],'native_imported':False,'seating_contact_ready':False};(OUT/'source-report.json').write_text(json.dumps(report,indent=2));print('MUUTO_CANDIDATE_READY',report['sofa_glb_sha256'],flush=True)
