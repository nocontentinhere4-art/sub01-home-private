"""Real licensed iraida Gran Gaggia model, original materials/geometry; isolated source review."""
import bpy,json,math,hashlib
from pathlib import Path
from mathutils import Vector,Matrix
ROOT=Path('/workspace/sub01-home-private/real-gaggia-gran-iraida-r1');OUT=ROOT/'output';OUT.mkdir(exist_ok=True)
source=ROOT/'source/original-gaggia-gran.glb';assert hashlib.sha256(source.read_bytes()).hexdigest()=='72acd995c06761ea7470f828c080bedc77d528a61232533dc0240877b5efc098'
bpy.ops.wm.read_factory_settings(use_empty=True);scene=bpy.context.scene;bpy.ops.import_scene.gltf(filepath=str(source));parts=sorted([o for o in scene.objects if o.type=='MESH'],key=lambda o:o.name)
def bounds(obs):
 pts=[o.matrix_world@v.co for o in obs for v in o.data.vertices];return [[min(p[i]for p in pts)for i in range(3)],[max(p[i]for p in pts)for i in range(3)]]
original=bounds(parts);print('ORIGINAL_GAGGIA_IMPORTED_BOUNDS',original,flush=True)
# Keep original complete source and original graph. Render normalization is an external review-only transform.
lo,hi=map(Vector,original);span=hi.z-lo.z;scale=.297/span;centre=(lo+hi)/2
root=bpy.data.objects.new('ReviewExternalOnly',None);scene.collection.objects.link(root)
for o in [o for o in scene.objects if o!=root and o.parent is None]:o.parent=root
root.matrix_world=Matrix.Scale(scale,4);bpy.context.view_layer.update();lo,hi=map(Vector,bounds(parts));centre=(lo+hi)/2;span=max(hi-lo)
source_objects=[o for o in scene.objects if o.type!='LIGHT'and o.type!='CAMERA'];bpy.ops.object.select_all(action='DESELECT')
for o in source_objects:o.select_set(True)
bpy.ops.export_scene.gltf(filepath=str(OUT/'gaggia-complete-review.glb'),export_format='GLB',use_selection=True,export_apply=True,export_animations=False)
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'gaggia-source-review.blend'))
world=bpy.data.worlds.new('SourceStudio');world.use_nodes=True;world.node_tree.nodes['Background'].inputs[0].default_value=(.20,.22,.24,1);world.node_tree.nodes['Background'].inputs[1].default_value=.5;scene.world=world
for delta,power,size in [((-.6,-.8,1.1),10,.7),((.8,.3,.7),14,.5),((-.4,.7,.4),6,.4)]:
 bpy.ops.object.light_add(type='AREA',location=centre+Vector(delta)*span);l=bpy.context.object;l.data.energy=power;l.data.size=size;l.rotation_euler=(centre-l.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.mesh.primitive_plane_add(size=3,location=(centre.x,centre.y,lo.z-.00001));floor=bpy.context.object;m=bpy.data.materials.new('DiagnosticFloor');m.diffuse_color=(.13,.14,.15,1);floor.data.materials.append(m)
bpy.ops.object.camera_add();camera=bpy.context.object;camera.data.type='ORTHO';camera.data.ortho_scale=span*1.3;scene.camera=camera
scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=16;scene.cycles.use_denoising=True;scene.render.resolution_x=960;scene.render.resolution_y=960;scene.render.resolution_percentage=100
for name,delta in [('front',(0,-2,.55)),('three-quarter',(1.2,-1.8,.8))]:
 camera.location=centre+Vector(delta)*span;camera.rotation_euler=(centre-camera.location).to_track_quat('-Z','Y').to_euler();scene.render.filepath=str(OUT/(name+'.png'));bpy.ops.render.render(write_still=True)
report={'schema':'sub01.real-gaggia-source-review.v1','source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'author':'iraida','license':'CC-BY-4.0','original_bounds_m':original,'external_review_height_m':.297,'external_review_scale':scale,'physical_dimensions_verified':False,'geometry_materials_original':True,'parts':[{'name':o.name,'bounds_m':bounds([o]),'triangles':sum(len(p.vertices)-2 for p in o.data.polygons),'materials':[m.name if m else None for m in o.data.materials]}for o in parts],'runtime_edited':False,'native_imported':False,'note':'Two cups and coffee streams exist as separate authored source meshes; candidate inclusion awaits review.'};(OUT/'source-report.json').write_text(json.dumps(report,indent=2));print('GAGGIA_SOURCE_REVIEW_READY',flush=True)
