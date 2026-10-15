"""Isolated CC0 source anatomy review; no retarget or acceptance claim."""
import bpy,json,hashlib
from pathlib import Path
from mathutils import Vector
root=Path('/workspace/sub01-home-private/human-base-hands-r1');source=root/'source/human-base-meshes-bundle-v1.4.1/human_base_meshes_bundle.blend';out=root/'review-r2';out.mkdir(exist_ok=False)
bpy.ops.wm.read_factory_settings(use_empty=True)
with bpy.data.libraries.load(str(source),link=False)as(src,dst):dst.objects=['Hand  - Realistic']
o=dst.objects[0];bpy.context.scene.collection.objects.link(o);o.hide_render=False;o.hide_viewport=False;o.hide_set(False);bpy.context.view_layer.update();original_modifiers=[]
for m in o.modifiers:
 if m.type=='MULTIRES':
  original_modifiers.append({'name':m.name,'levels':m.levels,'render_levels':m.render_levels,'total_levels':m.total_levels});m.levels=min(3,m.total_levels);m.render_levels=min(3,m.total_levels)
mat=bpy.data.materials.new('Neutral anatomy review only');mat.use_nodes=True;bsdf=mat.node_tree.nodes.get('Principled BSDF');bsdf.inputs['Base Color'].default_value=(.49,.28,.19,1);bsdf.inputs['Roughness'].default_value=.5;bsdf.inputs['Subsurface Weight'].default_value=.08;o.data.materials.clear();o.data.materials.append(mat)
for p in o.data.polygons:p.use_smooth=True
s=bpy.context.scene;world=bpy.data.worlds.new('Neutral studio');world.use_nodes=True;world.node_tree.nodes['Background'].inputs[0].default_value=(.15,.16,.18,1);world.node_tree.nodes['Background'].inputs[1].default_value=.4;s.world=world
points=[o.matrix_world@Vector(v)for v in o.bound_box];target=sum(points,Vector())/8
bpy.ops.object.camera_add();camera=bpy.context.object;camera.data.type='ORTHO';camera.data.ortho_scale=.33;s.camera=camera
lights=[]
for energy,size in [(90,1.2),(40,.9)]:bpy.ops.object.light_add(type='AREA');light=bpy.context.object;light.data.energy=energy;light.data.size=size;lights.append(light)
s.render.engine='CYCLES';s.cycles.device='CPU';s.cycles.samples=32;s.cycles.use_denoising=True;s.render.resolution_x=750;s.render.resolution_y=1000;s.render.resolution_percentage=100;s.render.image_settings.file_format='PNG';s.view_settings.view_transform='AgX'
rows=[]
for view,direction in [('side-a',Vector((.15,-.65,.08))),('side-b',Vector((-.15,.65,.08)))]:
 camera.location=target+direction;camera.rotation_euler=(target-camera.location).to_track_quat('-Z','Y').to_euler()
 for light,offset in zip(lights,[direction.normalized()+Vector((-.35,0,.55)),Vector((.3,.1,.8))]):light.location=target+offset;light.rotation_euler=(target-light.location).to_track_quat('-Z','Y').to_euler()
 s.render.filepath=str(out/('official-realistic-hand-'+view+'.png'));bpy.ops.render.render(write_still=True);rows.append(s.render.filepath)
bpy.ops.object.select_all(action='DESELECT');o.select_set(True);bpy.context.view_layer.objects.active=o
bpy.ops.export_scene.gltf(filepath=str(out/'official-realistic-hand-review.glb'),export_format='GLB',use_selection=True,export_apply=True)
report={'source_blend_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'source_object':o.name,'source_author':o.asset_data.author,'source_license':o.asset_data.license,'source_description':o.asset_data.description,'source_base_vertices':len(o.data.vertices),'source_base_faces':len(o.data.polygons),'original_multires':original_modifiers,'review_multires_level':min(3,original_modifiers[0]['total_levels']),'material':'Neutral diagnostic skin material; not a scanned skin texture','shape_changes':False,'armature_or_weights_present':False,'rigging_and_owner_contact_fit_pending':True,'images':rows,'glb_sha256':hashlib.sha256((out/'official-realistic-hand-review.glb').read_bytes()).hexdigest(),'native_imported':False,'visual_accepted':False}
(out/'review-report.json').write_text(json.dumps(report,indent=2)+'\n');print('OFFICIAL_REAL_HAND_SOURCE_REVIEW',json.dumps(report),flush=True)
