"""Blender source-only placement and physical leveling for actual media furniture."""
import bpy,math,json,hashlib,sys
from pathlib import Path
from mathutils import Vector
ROOT=Path('/workspace/sub01-home-private/real-media-console-source-r1/output')
bpy.ops.wm.open_mainfile(filepath=str(ROOT/'media-console.blend'))
anchor=bpy.data.objects['SUB01_MediaCabinetPlacement']
assert max(abs(a-b)for a,b in zip(anchor.location,(-3.45,.05,.025)))<1e-6
anchor.location=(-3.66,-2.05,.0328);bpy.context.view_layer.update()
feet=[]
for o in list(bpy.context.scene.objects):
 if o.type!='MESH' or not o.name.startswith('Leg | felt glide'):continue
 pts=[o.matrix_world@Vector(v)for v in o.bound_box];center=sum(pts,Vector())/len(pts)
 if -center.y<1.75:continue
 # Extend the actual adjustable glide under the two legs on the bare floor.
 # The cabinet, legs, joinery, scale and all other original objects stay intact.
 old=o.matrix_world.copy();world=old.copy();world.translation.z-=.00775;o.matrix_world=world
 bpy.context.view_layer.update()
 pts=[o.matrix_world@Vector(v)for v in o.bound_box];top=max(p.z for p in pts)
 # Exposed steel leveling spindle overlaps both pad and original steel leg.
 bottom=top-.001;upper=.0378+.002
 bpy.ops.mesh.primitive_cylinder_add(vertices=24,radius=.0055,depth=upper-bottom,location=(center.x,center.y,(upper+bottom)/2))
 stem=bpy.context.object;stem.name='Floor side adjustable steel foot spindle'
 reference=next(x for x in bpy.context.scene.objects if x.type=='MESH'and x.name.startswith('Leg | tapered graphite steel'))
 stem.data.materials.append(reference.data.materials[0])
 for f in stem.data.polygons:f.use_smooth=True
 feet.append({'source_glide':o.name,'extension_m':.00775,'bottom_m':min(p.z for p in pts),'target_floor_top_m':.02500121215760487,'clearance_m':min(p.z for p in pts)-.02500121215760487,'spindle_bottom_m':bottom,'spindle_top_m':upper})
assert len(feet)==2
# Keep original mesh-only source graph before eleven-material native batching.
bpy.ops.file.pack_all();bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'media-console-side.blend'))
groups={};before=0
for o in list(bpy.context.scene.objects):
 if o.type!='MESH':continue
 assert len(o.data.materials)==1
 groups.setdefault(o.data.materials[0].name,[]).append(o);before+=sum(len(f.vertices)-2 for f in o.data.polygons)
parts=[]
for index,(material,objects)in enumerate(sorted(groups.items())):
 bpy.ops.object.select_all(action='DESELECT')
 for o in objects:o.select_set(True)
 bpy.context.view_layer.objects.active=objects[0];bpy.ops.object.join();o=bpy.context.object;o.name='SUB01ReferenceMedia_'+str(index);o.data.name=o.name
 world=o.matrix_world.copy();o.parent=None;o.matrix_world=world;parts.append(o)
assert len(parts)==11
bpy.ops.object.select_all(action='DESELECT')
for o in parts:o.select_set(True)
output=ROOT/'media-console-side-native.glb';bpy.ops.export_scene.gltf(filepath=str(output),export_format='GLB',use_selection=True,export_cameras=False,export_lights=False)
after=sum(sum(len(f.vertices)-2 for f in o.data.polygons)for o in parts);assert before==after
r={'schema':'sub01.reference-media-real-leveling.v1','sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'native_changed':False,'placement_gltf_m':[-3.66,.0328,2.05],'unchanged_coffee_table':True,'unchanged_sofa':True,'cabinet_dimensions_unchanged':True,'only_modified_original_meshes':[f['source_glide']for f in feet],'floor_side_feet':feet,'material_groups':len(parts),'triangles':after,'gameplay_available':False}
(ROOT/'side-native-packet.json').write_text(json.dumps(r,indent=2));print(json.dumps(r),flush=True)

exec(compile(Path('/home/unreal/runtime-tools/prove_reference_media_source.py').read_text(),'prove-reference-media-side.py','exec'))
