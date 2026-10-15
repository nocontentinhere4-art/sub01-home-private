"""Private unmodified complete source review. No mesh/material/scale edits or LOD."""
import bpy,json,hashlib,math
from pathlib import Path
from mathutils import Vector
ROOT=Path('/workspace/sub01-home-private/ps5-datsketch-original-r1');OUT=ROOT/'review';OUT.mkdir(exist_ok=True)
raw=(ROOT/'scene.gltf').read_bytes();doc=json.loads(raw);assert len(doc['meshes'])==24 and len(doc['materials'])==13 and not doc.get('images')
bpy.ops.wm.read_factory_settings(use_empty=True);scene=bpy.context.scene;bpy.ops.import_scene.gltf(filepath=str(ROOT/'scene.gltf'));objects=[o for o in scene.objects if o.type=='MESH'];assert len(objects)==24
points=[o.matrix_world@v.co for o in objects for v in o.data.vertices];lo=Vector([min(p[i]for p in points)for i in range(3)]);hi=Vector([max(p[i]for p in points)for i in range(3)]);center=(lo+hi)/2;span=max(hi-lo)
# Preserve entire imported source in editable file BEFORE any review stage.
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'original-source.blend'))
bpy.ops.mesh.primitive_plane_add(size=span*8,location=(center.x,center.y,lo.z-span*.003));plane=bpy.context.object;m=bpy.data.materials.new('Neutral review floor');m.diffuse_color=(.14,.14,.14,1);plane.data.materials.append(m)
w=bpy.data.worlds.new('Neutral source inspection');w.use_nodes=True;w.node_tree.nodes['Background'].inputs[1].default_value=.4;scene.world=w
for offset,power in [((1,-1.4,1.3),900),((-1,1,.8),700)]:
 bpy.ops.object.light_add(type='AREA',location=center+Vector(offset)*span);light=bpy.context.object;light.data.energy=power*span**2;light.data.size=span*1.5;light.rotation_euler=(center-light.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.object.camera_add();camera=bpy.context.object;scene.camera=camera;camera.data.type='ORTHO';camera.data.ortho_scale=span*1.35
scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=16;scene.cycles.use_denoising=True;scene.render.resolution_x=720;scene.render.resolution_y=960;scene.render.resolution_percentage=100
for label,offset in [('front',(1,-1.7,.5)),('rear',(-1,1.7,.5))]:
 camera.location=center+Vector(offset)*span;camera.rotation_euler=(center-camera.location).to_track_quat('-Z','Y').to_euler();scene.render.filepath=str(OUT/(label+'.png'));bpy.ops.render.render(write_still=True)
report={'schema':'sub01.original-datsketch-ps5-review.v1','raw_gltf_sha256':hashlib.sha256(raw).hexdigest(),'raw_bin_sha256':hashlib.sha256((ROOT/'scene.bin').read_bytes()).hexdigest(),'asset_metadata_original':doc['asset'],'primary_current_license':'CC-BY-ND-4.0 verified official artist Sketchfab page','historical_embedded_license':'CC-BY-4.0; conflicting with current primary, not asserted current BY license','complete_original_meshes':len(objects),'original_materials':len(doc['materials']),'mesh_PBR_TRS_source_modified':False,'bounds_Blender_imported_units':[list(lo),list(hi)],'dimensions_Blender_imported_units':list(hi-lo),'native_imported':False,'redistribution_authorized':False};(OUT/'source-review.json').write_text(json.dumps(report,indent=2));print('ORIGINAL_PS5_SOURCE_REVIEW_READY',flush=True)
