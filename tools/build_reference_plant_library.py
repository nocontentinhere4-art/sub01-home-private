"""Review licensed varied houseplants; prepare bounded source LODs off the Mac.

Original licensed GLBs stay immutable. This does not place assets in ActualHome.
"""
import bpy,json,hashlib,math,sys
from pathlib import Path
from mathutils import Vector
ROOT=Path('/workspace/sub01-home-private/reference-plants-r1');SRC=ROOT/'source';OUT=ROOT/'output';OUT.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
source=json.loads((SRC/'acquisition.json').read_text());records=[];all_groups=[]
for index,item in enumerate(source['source_originals']):
 path=SRC/(item['slug']+'.glb');assert hashlib.sha256(path.read_bytes()).hexdigest()==item['sha256']
 before=set(bpy.context.scene.objects);bpy.ops.import_scene.gltf(filepath=str(path));objects=[o for o in bpy.context.scene.objects if o not in before];meshes=[o for o in objects if o.type=='MESH']
 original_tri=sum(len(o.data.loop_triangles)if o.data.loop_triangles else sum(len(p.vertices)-2 for p in o.data.polygons)for o in meshes)
 rawparts=[{'name':o.name,'triangles':sum(len(p.vertices)-2 for p in o.data.polygons)}for o in meshes]
 if index==0:
  # The areca alone is56k; retain its authored leaf silhouettes, reduce only
  # redundant interior vertices conservatively. The full original stays pinned.
  for o in meshes:
   triangles=sum(len(p.vertices)-2 for p in o.data.polygons)
   if triangles>1000:
    bpy.context.view_layer.objects.active=o;mod=o.modifiers.new('Source only conservative palm LOD','DECIMATE');mod.ratio=.45;mod.use_collapse_triangulate=True;bpy.ops.object.modifier_apply(modifier=mod.name)
 # Export each species independently with its authored object/material groups.
 bpy.ops.object.select_all(action='DESELECT')
 for o in meshes:o.select_set(True)
 bpy.context.view_layer.objects.active=meshes[0]
 out=OUT/(item['slug']+'-lod.glb');bpy.ops.export_scene.gltf(filepath=str(out),export_format='GLB',use_selection=True,export_cameras=False,export_lights=False)
 triangles=sum(sum(len(p.vertices)-2 for p in o.data.polygons)for o in meshes)
 record={**item,'prepared_sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'prepared_bytes':out.stat().st_size,'prepared_triangles':triangles,'original_triangle_count_from_import':original_tri,'original_parts':rawparts,'decimation':.45 if index==0 else None,'native_installed':False,'source_original_unchanged':hashlib.sha256(path.read_bytes()).hexdigest()==item['sha256']};records.append(record)
 # Move only this review instance after source export; source plant origin/scale
 # in each actual GLB stays authored and suitable for later measured placement.
 top=[o for o in objects if o.parent not in objects]
 for o in top:o.location.x+=(index-2)*1.8
 all_groups.append(meshes)
# A neutral review studio is not the home or an accepted native view.
mat=bpy.data.materials.new('Review neutral ground');mat.use_nodes=True;mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value=(.52,.49,.43,1);mat.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value=.85
bpy.ops.mesh.primitive_plane_add(size=200);bpy.context.object.data.materials.append(mat)
world=bpy.data.worlds.new('Plant source daylight');world.use_nodes=True;world.node_tree.nodes['Background'].inputs[0].default_value=(.72,.76,.8,1);world.node_tree.nodes['Background'].inputs[1].default_value=.28;bpy.context.scene.world=world
for loc,power,size in[((-3,-4,5),1100,5),((4,1,5),650,4)]:
 bpy.ops.object.light_add(type='AREA',location=loc);l=bpy.context.object;l.data.energy=power;l.data.size=size;l.rotation_euler=(Vector((0,0,.9))-l.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.object.camera_add(location=(5,-12,5));cam=bpy.context.object;cam.rotation_euler=(Vector((0,0,.9))-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.type='ORTHO';cam.data.ortho_scale=10.2;bpy.context.scene.camera=cam
scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=24;scene.cycles.use_denoising=True;scene.render.threads_mode='FIXED';scene.render.threads=3;scene.render.resolution_x=1600;scene.render.resolution_y=800;scene.render.resolution_percentage=100;scene.render.image_settings.file_format='PNG';scene.view_settings.view_transform='AgX'
report={'schema':'sub01.reference-plant-library-source.v1','source_license':'CC0-1.0 original Innerscene models, verified primary pages in configured isolated Playwright','plants':records,'prepared_total_triangles':sum(r['prepared_triangles']for r in records),'existing_home_untouched':True,'native_ready':False,'plant_quality_acceptance':False,'placement_collision_acceptance':False}
(OUT/'plant-library-source.json').write_text(json.dumps(report,indent=2)+'\n');bpy.ops.file.pack_all();bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'plant-library-review.blend'));scene.render.filepath=str(OUT/'plant-library-source-review.png');bpy.ops.render.render(write_still=True);print('SOURCE_PLANT_LIBRARY_COMPLETE',json.dumps({'prepared_total_triangles':report['prepared_total_triangles'],'source_only':True}),flush=True)
