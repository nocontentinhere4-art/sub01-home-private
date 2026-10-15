"""Complete genuine CC0 Syngonium/pot, uniform40cm; source-only close front/back review."""
import bpy,json,hashlib,math
from pathlib import Path
from mathutils import Vector
R=Path('/workspace/sub01-home-private/real-kitchen-syngonium-r1');S=R/'source';O=R/'output';O.mkdir(exist_ok=True);source=S/'potted_plant_02_2k.gltf';raw=json.loads(source.read_text());bpy.ops.wm.read_factory_settings(use_empty=True);bpy.ops.import_scene.gltf(filepath=str(source));parts=[o for o in bpy.context.scene.objects if o.type=='MESH'];assert parts
pts=[o.matrix_world@v.co for o in parts for v in o.data.vertices];lo=Vector([min(p[k]for p in pts)for k in range(3)]);hi=Vector([max(p[k]for p in pts)for k in range(3)]);scale=.4/(hi.z-lo.z);anchor=Vector((-.82,3.55,.92251));translation=Vector((anchor.x-(lo.x+hi.x)*scale/2,anchor.y-(lo.y+hi.y)*scale/2,anchor.z-lo.z*scale));root=bpy.data.objects.new('Whole authored plant uniform40cm only',None);bpy.context.collection.objects.link(root)
original=[]
for i,o in enumerate(parts):
 w=o.matrix_world.copy();original.append({'originalName':o.name,'vertices':len(o.data.vertices),'triangles':sum(len(p.vertices)-2 for p in o.data.polygons)});o.parent=root;o.matrix_world=w;o.name='SKPlant%02d'%i
root.scale=(scale,)*3;root.location=translation;bpy.context.view_layer.update();materials=[]
for i,m in enumerate({m.name:m for o in parts for m in o.data.materials if m}.values()):
 s=m.node_tree.nodes.get('Principled BSDF');materials.append({'originalName':m.name,'ownedName':'SK%02d'%i,'useBackfaceCulling':m.use_backface_culling,'principledPresent':s is not None});m.name='SK%02d'%i
for o in parts:
 w=o.matrix_world.copy();o.parent=None;o.matrix_world=w
bpy.data.objects.remove(root,do_unlink=True)
bpy.ops.object.select_all(action='DESELECT')
for o in parts:o.select_set(True)
bpy.context.view_layer.objects.active=parts[0];bpy.ops.export_scene.gltf(filepath=str(O/'genuine-kitchen-syngonium.glb'),export_format='GLB',use_selection=True,export_cameras=False,export_lights=False);bpy.ops.file.pack_all();bpy.ops.wm.save_as_mainfile(filepath=str(O/'genuine-kitchen-syngonium.blend'));p=[o.matrix_world@v.co for o in parts for v in o.data.vertices];bounds=[[min(v[k]for v in p)for k in range(3)],[max(v[k]for v in p)for k in range(3)]]
r={'schema':'sub01.genuine-kitchen-syngonium-source.v1','sourceURL':'https://polyhaven.com/a/potted_plant_02','author':'Rico Cilliers','license':'CC0-1.0','sourceFiles':json.loads((S/'source-files.json').read_text()),'originalGltfMaterials':raw['materials'],'completeOriginalPlantAndPotRetained':True,'originalMeshes':original,'ownedMaterials':materials,'uniformScale':scale,'originalDimensionsM':list(hi-lo),'placedDimensionsM':[(hi[k]-lo[k])*scale for k in range(3)],'translationBlenderM':list(translation),'boundsBlenderM':bounds,'boundsUEcm':[[100*bounds[0][0],-100*bounds[1][1],100*bounds[0][2]],[100*bounds[1][0],-100*bounds[0][1],100*bounds[1][2]]],'originalGeometryUVPBRNoTintOrDecimation':True,'retireOnlyOriginalHomeNodes':[216,217,218,219],'nativeInstalled':False,'physicalContactAccepted':False,'sourceSHA256':hashlib.sha256((O/'genuine-kitchen-syngonium.glb').read_bytes()).hexdigest()};(O/'source-report.json').write_text(json.dumps(r,indent=2)+'\n')
# Review-only neutral support; never included in source asset export.
bpy.ops.mesh.primitive_plane_add(size=200,location=(0,0,.9225));floor=bpy.context.object;mat=bpy.data.materials.new('Review only neutral support');mat.diffuse_color=(.42,.40,.36,1);floor.data.materials.append(mat)
scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=24;scene.cycles.use_denoising=True;scene.render.resolution_x=800;scene.render.resolution_y=900;scene.render.resolution_percentage=100;scene.render.image_settings.file_format='PNG';scene.view_settings.view_transform='AgX';world=bpy.data.worlds.new('Neutral daylight');world.use_nodes=True;world.node_tree.nodes['Background'].inputs[0].default_value=(.7,.75,.8,1);world.node_tree.nodes['Background'].inputs[1].default_value=.25;scene.world=world;target=Vector((-.82,3.55,1.12))
for pos,power,size in [((-.1,2.7,2),70,.7),((-1.4,3.8,1.9),35,.6)]:
 bpy.ops.object.light_add(type='AREA',location=pos);o=bpy.context.object;o.data.energy=power;o.data.size=size;o.rotation_euler=(target-o.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.object.camera_add();cam=bpy.context.object;scene.camera=cam;cam.data.type='ORTHO';cam.data.ortho_scale=.58
for name,pos in [('front',(-.15,2.65,1.42)),('back',(-1.49,4.45,1.42))]:
 cam.location=pos;cam.rotation_euler=(target-cam.location).to_track_quat('-Z','Y').to_euler();scene.render.filepath=str(O/('genuine-syngonium-'+name+'.png'));bpy.ops.render.render(write_still=True)
print(json.dumps(r),flush=True)
