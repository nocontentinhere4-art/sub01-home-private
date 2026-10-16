"""Rigidly place genuine licensed Gaggia derivative; standalone native-source nodes, no remodel."""
import bpy,json,hashlib,math
from pathlib import Path
from mathutils import Vector,Matrix
R=Path('/workspace/sub01-home-private/real-gaggia-gran-iraida-r1');O=R/'placed-idle-r3';O.mkdir(exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(R/'idle-r2/gaggia-source-review.blend'));scene=bpy.context.scene;parts=sorted([o for o in scene.objects if o.type=='MESH'],key=lambda o:o.name);assert len(parts)==36
signatures={o.name:hashlib.sha256(str(([tuple(v.co)for v in o.data.vertices],[tuple(p.vertices)for p in o.data.polygons])).encode()).hexdigest()for o in parts}
original_names={}
for i,o in enumerate(parts):
 w=o.matrix_world.copy();o.parent=None;o.matrix_world=Matrix.Rotation(-math.pi/2,4,'Z')@w;original_names[f'GaggiaIdle_{i:03}']=o.name;o.name=f'GaggiaIdle_{i:03}';o.data.name=o.name+'_Mesh'
bpy.context.view_layer.update()
def points():return[o.matrix_world@v.co for o in parts for v in o.data.vertices]
p=points();lo=Vector([min(v[i]for v in p)for i in range(3)]);hi=Vector([max(v[i]for v in p)for i in range(3)]);delta=Vector((-1.2405-(lo.x+hi.x)/2,3.46-(lo.y+hi.y)/2,.9225101-lo.z))
for o in parts:o.matrix_world=Matrix.Translation(delta)@o.matrix_world
bpy.context.view_layer.update();p=points();bounds=[[min(v.x for v in p)*100,-max(v.y for v in p)*100,min(v.z for v in p)*100],[max(v.x for v in p)*100,-min(v.y for v in p)*100,max(v.z for v in p)*100]]
for o in parts:assert hashlib.sha256(str(([tuple(v.co)for v in o.data.vertices],[tuple(p.vertices)for p in o.data.polygons])).encode()).hexdigest()==signatures[original_names[o.name]]
bpy.ops.object.select_all(action='DESELECT')
for o in parts:o.select_set(True)
bpy.context.view_layer.objects.active=parts[0];path=O/'gaggia-gran-idle-placed.glb';bpy.ops.export_scene.gltf(filepath=str(path),export_format='GLB',use_selection=True,export_apply=True,export_animations=False);bpy.ops.wm.save_as_mainfile(filepath=str(O/'gaggia-gran-idle-placed.blend'))
report={'schema':'sub01.genuine-gaggia-idle-placement.v1','original_source_sha256':'72acd995c06761ea7470f828c080bedc77d528a61232533dc0240877b5efc098','placed_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'author':'iraida','license':'CC-BY-4.0','mirror_commit':'8d4cfb344f18433804b13f8cb83a0c2381eb9051','part_count':len(parts),'names':original_names,'source_local_geometry_fingerprints':signatures,'unchanged_source_geometry':True,'source_materials_unchanged':True,'rigid_placement_only':True,'uniform_height_calibration_m':.300,'manufacturer_dimensions_numeric':[210,300,280],'manufacturer_unit_caption_inconsistent':True,'not_manufacturer_CAD':True,'bounds_UE_cm':bounds,'front_direction_UE':'+Y','base_target_cm':92.25101,'omitted_source_meshes':['pCylinder34_Coffee_0','pCylinder34_Coffee_dark_0','pCylinder35_Coffee_0','pCylinder35_Coffee_dark_0','polySurface71_Coffee_light_0','polySurface72_Kruzka_1_0','polySurface73_Coffee_light_0'],'cup':'one genuine original empty source cup, moved rigidly under original outlets; support pending independent proof','native_imported':False,'interaction_ready':False};(O/'source-report.json').write_text(json.dumps(report,indent=2));print('GAGGIA_PLACED_SOURCE',report['placed_sha256'],bounds,flush=True)
