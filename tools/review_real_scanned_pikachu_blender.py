"""Pinned MIT real-object scan review; uniform20cm miniature, original mesh/image intact."""
import bpy,json,hashlib,math
from pathlib import Path
from mathutils import Vector
R=Path('/workspace/sub01-home-private/real-scanned-pikachu-r1');O=R/'review';O.mkdir(exist_ok=True);P=R/'source/modelpika_updated.glb';assert hashlib.sha256(P.read_bytes()).hexdigest()=='e42bda19c96673408ca03647099365b8116ddb34ad1d4ee8f97ce3139085da78'
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False);bpy.ops.import_scene.gltf(filepath=str(P));parts=[o for o in bpy.context.scene.objects if o.type=='MESH'];pts=[o.matrix_world@v.co for o in parts for v in o.data.vertices];lo=Vector([min(p[k]for p in pts)for k in range(3)]);hi=Vector([max(p[k]for p in pts)for k in range(3)]);scale=.2/(hi.z-lo.z);root=bpy.data.objects.new('Original scan uniform miniature units',None);bpy.context.collection.objects.link(root)
for o in parts:o.parent=root
root.scale=(scale,)*3;root.location=Vector((-(lo.x+hi.x)*scale/2,-(lo.y+hi.y)*scale/2,-lo.z*scale));bpy.context.view_layer.update();tri=0
for o in parts:o.data.calc_loop_triangles();tri+=len(o.data.loop_triangles)
scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.samples=16;scene.cycles.use_denoising=True;scene.render.resolution_x=720;scene.render.resolution_y=720;scene.render.resolution_percentage=100;scene.world.color=(.18,.18,.18);scene.view_settings.view_transform='AgX'
def point(obj,at):obj.rotation_euler=(Vector(at)-obj.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.object.camera_add(location=(.32,-.48,.27));camera=bpy.context.object;point(camera,(0,0,.1));camera.data.type='ORTHO';camera.data.ortho_scale=.3;scene.camera=camera
for name,loc,power,size in [('key',(.3,-.3,.5),35,.35),('fill',(-.3,-.1,.25),12,.3),('rim',(0,.35,.4),20,.25)]:
 bpy.ops.object.light_add(type='AREA',location=loc);l=bpy.context.object;l.name=name;l.data.energy=power;l.data.shape='DISK';l.data.size=size;point(l,(0,0,.1))
bpy.ops.mesh.primitive_plane_add(size=200,location=(0,0,-.0001));floor=bpy.context.object;mat=bpy.data.materials.new('Neutral reviewfloor');mat.diffuse_color=(.35,.35,.35,1);floor.data.materials.append(mat)
report={'source_sha256':hashlib.sha256(P.read_bytes()).hexdigest(),'source':'https://github.com/paulinamoskwa/detect-pikachu/tree/8d3d026b08e19b89ef4a737a6e73da22d565befb','license':'Repository MIT; character trademark separate; private source review only','meshCount':len(parts),'triangles':tri,'originalDimensions':[hi[i]-lo[i]for i in range(3)],'uniformExternalScale':scale,'miniatureDimensionsM':[(hi[i]-lo[i])*scale for i in range(3)],'heightM':.2,'originalVerticesImagesMaterialsUnchanged':True,'proposedCabinetAnchorUEcm':[-351,60,56.73],'nativeInstalled':False};(O/'source-review.json').write_text(json.dumps(report,indent=2));scene.render.filepath=str(O/'real-scan-20cm-review.png');bpy.ops.render.render(write_still=True);print(json.dumps(report),flush=True)
