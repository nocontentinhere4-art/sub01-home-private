"""Blender source from actual GROHE Concetto CAD tessellation, no invented shape."""
import bpy,json,hashlib,math
from pathlib import Path
from mathutils import Vector,Matrix
ROOT=Path('/workspace/sub01-home-private/official-grohe-concetto-r1');OUT=ROOT/'output';OUT.mkdir(exist_ok=True)
data=json.loads((ROOT/'tessellated-cad.json').read_text());bpy.ops.wm.read_factory_settings(use_empty=True);scene=bpy.context.scene
chrome=bpy.data.materials.new('GroheOfficialChrome');chrome.use_nodes=True;bs=chrome.node_tree.nodes.get('Principled BSDF');bs.inputs['Base Color'].default_value=(.64,.68,.72,1);bs.inputs['Metallic'].default_value=1;bs.inputs['Roughness'].default_value=.16
parts=[]
for p in data['parts']:
 mesh=bpy.data.meshes.new(p['name']+'_Mesh');mesh.from_pydata(p['vertices_m'],[],p['faces']);mesh.update();obj=bpy.data.objects.new(p['name'],mesh);scene.collection.objects.link(obj);obj.data.materials.append(chrome)
 for poly in mesh.polygons:poly.use_smooth=True
 parts.append(obj)
# Keep exact CAD coordinates and physical millimetre conversion. Placement is separate.
points=[v.co for o in parts for v in o.data.vertices];lo=Vector([min(p[i]for p in points)for i in range(3)]);hi=Vector([max(p[i]for p in points)for i in range(3)]);centre=(lo+hi)/2;span=max(hi-lo)
bpy.ops.object.select_all(action='DESELECT')
for o in parts:o.select_set(True)
bpy.context.view_layer.objects.active=parts[0]
bpy.ops.export_scene.gltf(filepath=str(OUT/'grohe-concetto-official-cad.glb'),export_format='GLB',use_selection=True,export_apply=True,export_animations=False)
# External rigid placement only: genuine CAD +X outlet rotates toward native +Y basin.
rigid=Matrix.Translation(Vector((-2.70000005,3.78999996,.9225101)))@Matrix.Rotation(-math.pi/2,4,'Z')
old_transforms={o.name:o.matrix_world.copy()for o in parts}
for o in parts:o.matrix_world=rigid@o.matrix_world
bpy.context.view_layer.update()
bpy.ops.export_scene.gltf(filepath=str(OUT/'grohe-concetto-placed.glb'),export_format='GLB',use_selection=True,export_apply=True,export_animations=False)
placed_points=[o.matrix_world@v.co for o in parts for v in o.data.vertices]
placed_bounds_ue=[[min(p.x for p in placed_points)*100,-max(p.y for p in placed_points)*100,min(p.z for p in placed_points)*100],[max(p.x for p in placed_points)*100,-min(p.y for p in placed_points)*100,max(p.z for p in placed_points)*100]]
for o in parts:o.matrix_world=old_transforms[o.name]
bpy.context.view_layer.update()
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'grohe-concetto-official-cad.blend'))
world=bpy.data.worlds.new('Studio');world.use_nodes=True;world.node_tree.nodes['Background'].inputs[0].default_value=(.30,.32,.34,1);world.node_tree.nodes['Background'].inputs[1].default_value=.25;scene.world=world
for rel,power,size in [((-.6,-.6,.8),8,.55),((.6,.2,.5),12,.45),((-.2,.6,.3),5,.25)]:
 bpy.ops.object.light_add(type='AREA',location=centre+Vector(rel)*span);light=bpy.context.object;light.data.energy=power;light.data.size=size;light.rotation_euler=(centre-light.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.mesh.primitive_plane_add(size=3,location=(centre.x,centre.y,lo.z-.00001));floor=bpy.context.object;mat=bpy.data.materials.new('DiagnosticFloor');mat.diffuse_color=(.13,.14,.15,1);floor.data.materials.append(mat)
bpy.ops.object.camera_add(location=centre+Vector((1.3,-1.9,1.0))*span);camera=bpy.context.object;camera.rotation_euler=(centre-camera.location).to_track_quat('-Z','Y').to_euler();camera.data.type='ORTHO';camera.data.ortho_scale=span*1.30;scene.camera=camera
scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=16;scene.cycles.use_denoising=True;scene.render.resolution_x=960;scene.render.resolution_y=960;scene.render.resolution_percentage=100;scene.render.filepath=str(OUT/'official-grohe-source-review.png');bpy.ops.render.render(write_still=True)
report={k:v for k,v in data.items()if k!='parts'};report.update(glb_sha256=hashlib.sha256((OUT/'grohe-concetto-official-cad.glb').read_bytes()).hexdigest(),placed_glb_sha256=hashlib.sha256((OUT/'grohe-concetto-placed.glb').read_bytes()).hexdigest(),placed_bounds_UE_cm=placed_bounds_ue,placed_mount_UE_cm=[-270.000005,-378.999996,92.25101],placed_outlet_direction_UE='+Y',part_count=len(parts),material='Chrome PBR, finish based on official product photograph; shader authored, CAD geometry genuine',native_imported=False,active_game_changed=False);(OUT/'source-report.json').write_text(json.dumps(report,indent=2));print('GROHE_BLENDER_SOURCE_READY',flush=True)
