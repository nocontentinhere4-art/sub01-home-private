"""Real licensed iraida Gran Gaggia model, original materials/geometry; isolated source review."""
import bpy,json,math,hashlib
from pathlib import Path
from mathutils import Vector,Matrix
ROOT=Path('/workspace/sub01-home-private/real-gaggia-gran-iraida-r1');OUT=ROOT/'idle-r2';OUT.mkdir(exist_ok=True)
source=ROOT/'source/original-gaggia-gran.glb';assert hashlib.sha256(source.read_bytes()).hexdigest()=='72acd995c06761ea7470f828c080bedc77d528a61232533dc0240877b5efc098'
bpy.ops.wm.read_factory_settings(use_empty=True);scene=bpy.context.scene;bpy.ops.import_scene.gltf(filepath=str(source));parts=sorted([o for o in scene.objects if o.type=='MESH'],key=lambda o:o.name)
def bounds(obs):
 pts=[o.matrix_world@v.co for o in obs for v in o.data.vertices];return [[min(p[i]for p in pts)for i in range(3)],[max(p[i]for p in pts)for i in range(3)]]
original=bounds(parts);print('ORIGINAL_GAGGIA_IMPORTED_BOUNDS',original,flush=True)
# Keep original complete source and original graph. Render normalization is an external review-only transform.
lo,hi=map(Vector,original);span=hi.z-lo.z;scale=.300/span;centre=(lo+hi)/2
root=bpy.data.objects.new('ReviewExternalOnly',None);scene.collection.objects.link(root)
for o in [o for o in scene.objects if o!=root and o.parent is None]:o.parent=root
root.matrix_world=Matrix.Scale(scale,4);bpy.context.view_layer.update();lo,hi=map(Vector,bounds(parts));centre=(lo+hi)/2;span=max(hi-lo)
# CC-BY derivative: no frozen brewing streams or floating coffee surfaces; one genuine empty source cup.
omitted=[]
for o in list(parts):
 if o.name.startswith(('pCylinder34_Coffee','pCylinder35_Coffee','polySurface71_Coffee_light','polySurface72_Kruzka_1','polySurface73_Coffee_light')):
  omitted.append(o.name);parts.remove(o);bpy.data.objects.remove(o,do_unlink=True)
cup=next(o for o in parts if o.name=='polySurface69_Kruzhka_2_0')
points=[cup.matrix_world@v.co for v in cup.data.vertices];zmin=min(p.z for p in points);foot=[p for p in points if p.z<zmin+.0005];footcentre=sum(foot,Vector())/len(foot)
# Both original authored outlet paths guide the horizontal empty-cup placement, without inventing flow geometry.
stream_centres=[]
# Source review r1 bounds measured for original two streams; scale ratio only, same original body pose.
for x,y in [(.09205462783575058,-.24110161513090134),(.092021144926548,-.27260226011276245)]:stream_centres.append(Vector((x,y,0))*(.300/.297))
target=sum(stream_centres,Vector())/2;delta=Vector((target.x-footcentre.x,target.y-footcentre.y,0));cup_horizontal_delta=delta.copy();cup.matrix_world=Matrix.Translation(delta)@cup.matrix_world;bpy.context.view_layer.update()
# True source grate ray support for every actual lowest cup foot vertex.
from mathutils.bvhtree import BVHTree
verts=[];polys=[]
for o in parts:
 if o==cup:continue
 start=len(verts);verts.extend(o.matrix_world@v.co for v in o.data.vertices);polys.extend([start+i for i in p.vertices]for p in o.data.polygons)
BV=BVHTree.FromPolygons(verts,polys,all_triangles=False);cp=[cup.matrix_world@v.co for v in cup.data.vertices];low=min(p.z for p in cp);feet=[p for p in cp if p.z<low+.0005];ray=[];ray_misses=0
for p in feet:
 hit=BV.ray_cast(p+Vector((0,0,.0001)),Vector((0,0,-1)),.02)
 if hit[0]is None:ray_misses+=1;continue
 # Perforated source grate has open holes; retain truthful diagnostics, not automatic support acceptance.
 if hit[0].z<p.z-.005:ray_misses+=1;continue
 ray.append(hit[0].z-p.z)
lift=max(ray)+.00001 if ray else 0.;cup.matrix_world=Matrix.Translation(Vector((0,0,lift)))@cup.matrix_world;bpy.context.view_layer.update()
print('EMPTY_CUP_TRUE_GRATE_RAYS',len(ray),'LIFT_M',lift,flush=True)
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
for name,delta in [('front',(2,0,.4)),('three-quarter',(1.8,1.2,.7))]:
 camera.location=centre+Vector(delta)*span;camera.rotation_euler=(centre-camera.location).to_track_quat('-Z','Y').to_euler();scene.render.filepath=str(OUT/(name+'.png'));bpy.ops.render.render(write_still=True)
report={'schema':'sub01.real-gaggia-source-review.v1','source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'author':'iraida','license':'CC-BY-4.0','original_bounds_m':original,'external_review_height_m':.300,'external_review_scale':scale,'physical_dimensions_verified':False,'official_manual_numeric_dimensions_mm':[210,300,280],'official_manual_caption_inconsistent_unit':'cm label with millimetre numeric values; interpret as millimetres, not CAD-dimension acceptance','omitted_source_nodes':omitted,'empty_cup_foot_ray_count':len(ray),'empty_cup_rigid_horizontal_delta_m':list(cup_horizontal_delta),'empty_cup_hole_or_missing_ray_count':ray_misses,'empty_cup_support_proven':False,'empty_cup_support_note':'Independent true grate support polygon + COM and full BVH still required; no acceptance from sampled rays alone','empty_cup_vertical_contact_lift_m':lift,'geometry_materials_original':True,'parts':[{'name':o.name,'bounds_m':bounds([o]),'triangles':sum(len(p.vertices)-2 for p in o.data.polygons),'materials':[m.name if m else None for m in o.data.materials]}for o in parts],'runtime_edited':False,'native_imported':False,'note':'CC-BY derivative: omitted four static coffee stream parts, both coffee liquid surfaces and one second cup; genuine original blue empty cup moved rigidly under both source outlets onto true source grate. Shape/UV/material unedited.'};(OUT/'source-report.json').write_text(json.dumps(report,indent=2));print('GAGGIA_SOURCE_REVIEW_READY',flush=True)
