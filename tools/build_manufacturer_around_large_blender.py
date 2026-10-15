"""Official manufacturer Muuto Around Large, exact source centimetres, private review only."""
import bpy,sys,json,hashlib,zipfile,math
from pathlib import Path
from mathutils import Vector
ROOT=Path('/workspace/sub01-home-private/manufacturer-around-large-r1');OUT=ROOT/'output';OUT.mkdir(parents=True,exist_ok=True);ZIP=ROOT/'Around-Coffee-Table-3D.zip';assert hashlib.sha256(ZIP.read_bytes()).hexdigest()=='03d5946d49858acf67accadc841bd5246039951f7d9ee9486e7373154d94a58e'
with zipfile.ZipFile(ZIP)as z:
 for name in ['Around-3D/Around-Large-3D/OBJ/Around_Large.obj','Around-3D/Around-Large-3D/OBJ/Around_Large.mtl','Around-3D/Textures/Oak.jpg']:
  data=z.read(name);p=ROOT/'source'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
obj=ROOT/'source/Around-3D/Around-Large-3D/OBJ/Around_Large.obj';assert b'centimeters as units'in obj.read_bytes()[:150]
bpy.ops.wm.read_factory_settings(use_empty=True);bpy.ops.wm.obj_import(filepath=str(obj),global_scale=.01,forward_axis='NEGATIVE_Z',up_axis='Y');parts=[o for o in bpy.context.scene.objects if o.type=='MESH'];assert parts
points=[o.matrix_world@v.co for o in parts for v in o.data.vertices];lo=Vector([min(v[i]for v in points)for i in range(3)]);hi=Vector([max(v[i]for v in points)for i in range(3)]);dimensions=hi-lo;assert .70<dimensions.x<.75 and .70<dimensions.y<.75 and .35<dimensions.z<.40,('Source cm/Y-up dimensions unexpected',list(dimensions))
# Rigid centring and actual source lowest-foot support, no asset/proportion rescale.
delta=Vector((-2.59-(lo.x+hi.x)/2,.05-(lo.y+hi.y)/2,.02505-lo.z));original=[]
material=bpy.data.materials.new('MAOak00');material.use_nodes=True;p=material.node_tree.nodes.get('Principled BSDF');p.inputs['Roughness'].default_value=.42;p.inputs['Metallic'].default_value=0;image=bpy.data.images.load(str(ROOT/'source/Around-3D/Textures/Oak.jpg'));image.colorspace_settings.name='sRGB';image.pack();texture=material.node_tree.nodes.new('ShaderNodeTexImage');texture.image=image;material.node_tree.links.new(texture.outputs['Color'],p.inputs['Base Color'])
for i,o in enumerate(parts):
 assert o.data.uv_layers,'Manufacturer OBJ has no original UVs';o.data.calc_loop_triangles();original.append({'originalName':o.name,'originalVertices':len(o.data.vertices),'originalTriangles':len(o.data.loop_triangles),'originalMaterialNames':[m.name for m in o.data.materials],'uvLayers':[u.name for u in o.data.uv_layers]});world=o.matrix_world.copy();world.translation+=delta;o.matrix_world=world;o.name='MuutoAroundLarge_'+str(i).zfill(2);o.data.materials.clear();o.data.materials.append(material)
 for polygon in o.data.polygons:polygon.material_index=0
points=[o.matrix_world@v.co for o in parts for v in o.data.vertices];lo2=[min(v[i]for v in points)for i in range(3)];hi2=[max(v[i]for v in points)for i in range(3)];assert abs(lo2[2]-.02505)<1e-7
bpy.ops.object.select_all(action='DESELECT')
for o in parts:o.select_set(True)
bpy.context.view_layer.objects.active=parts[0];bpy.ops.export_scene.gltf(filepath=str(OUT/'muuto-around-large.glb'),export_format='GLB',use_selection=True,export_cameras=False,export_lights=False,export_extras=True)
# Discard unused legacy MTL image placeholders; source archive remains untouched.
for unused in list(bpy.data.images):
 if unused!=image:bpy.data.images.remove(unused)
bpy.ops.file.pack_all();bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'muuto-around-large.blend'))
report={'schema':'sub01.manufacturer-around-large-source-review.v1','source':'Official Muuto Around Coffee Table Large OBJ/MTL + official Oak.jpg downloaded through public manufacturer portal','sourceURL':'https://www.muuto.com/product/Around-Coffee-Table--AROTABLR/AROTABLR01/','officialVerifiedPhysicalDimensionsCm':{'height':36,'diameter':72},'officialProduct':'Oak old60032/newAROTABLR01; dimensions independently viewed via configured Playwright by parent','downloadURL':'https://download.muuto.com/digitalshowroom/#/product/628654978823581?tag=573684022989939','license':'Manufacturer asset; no CC0 claim. Private review source only; redistribution/publication permission unverified.','sourceZipSha256':hashlib.sha256(ZIP.read_bytes()).hexdigest(),'originalObjSha256':hashlib.sha256(obj.read_bytes()).hexdigest(),'sourceUnitsComment':'centimeters','unitsConversionOnly':.01,'rawSourcePhysicalDimensionsM':list(dimensions),'rigidTranslationBlenderM':list(delta),'boundsBlenderM':[lo2,hi2],'boundsUEcm':[[100*lo2[0],-100*hi2[1],100*lo2[2]],[100*hi2[0],-100*lo2[1],100*hi2[2]]],'parts':original,'triangles':sum(x['originalTriangles']for x in original),'originalGeometryAndUVPreserved':True,'finish':'Manufacturer original Oak.jpg, existing source UV; standard satin roughness factor .42, no synthesized geometry or grain','floorTopUEcm':2.505,'nativeImportPermitted':False,'visualAccepted':False,'placementAndRoutesAccepted':False,'files':{name:hashlib.sha256((OUT/name).read_bytes()).hexdigest()for name in ['muuto-around-large.glb','muuto-around-large.blend']}};(OUT/'source-report.json').write_text(json.dumps(report,indent=2)+'\n');print('SOURCE_READY='+json.dumps(report),flush=True)
# Source-only neutral photographic review; floor/lights/camera are not exported assets.
bpy.ops.mesh.primitive_plane_add(size=200,location=(0,0,.025));floor=bpy.context.object;floor.name='REVIEW_ONLY_Ground';m=bpy.data.materials.new('REVIEW_ONLY_WarmGrey');m.diffuse_color=(.19,.18,.165,1);m.use_nodes=True;m.node_tree.nodes.get('Principled BSDF').inputs['Roughness'].default_value=.85;floor.data.materials.append(m)
scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=48;scene.cycles.use_denoising=True;scene.render.threads_mode='FIXED';scene.render.threads=2;scene.render.resolution_x=1280;scene.render.resolution_y=960;scene.render.resolution_percentage=100;scene.world=bpy.data.worlds.new('REVIEW_ONLY_Studio');scene.world.use_nodes=True;scene.world.node_tree.nodes['Background'].inputs[0].default_value=(.70,.75,.85,1);scene.world.node_tree.nodes['Background'].inputs[1].default_value=.45
center=Vector((-2.59,.05,.20))
for name,offset,energy,size,color in [('Key',(-.4,-1.1,1.8),420,1.5,(1,.89,.76)),('Fill',(1.1,.5,1.2),180,1.4,(.82,.91,1)),('Rim',(-1,.8,1.5),260,1.2,(1,.95,.88))]:
 data=bpy.data.lights.new(name,'AREA');data.energy=energy;data.shape='DISK';data.size=size;data.color=color;o=bpy.data.objects.new(name,data);scene.collection.objects.link(o);o.location=center+Vector(offset);o.rotation_euler=(center-o.location).to_track_quat('-Z','Y').to_euler()
camera=bpy.data.cameras.new('Review');camera.lens=57;co=bpy.data.objects.new('Review',camera);scene.collection.objects.link(co);scene.camera=co
for name,offset in [('manufacturer-large-three-quarter',(.95,-1.25,.90)),('manufacturer-large-rim-detail',(.60,-.85,.58))]:
 co.location=center+Vector(offset);co.rotation_euler=(center-co.location).to_track_quat('-Z','Y').to_euler();scene.render.filepath=str(OUT/(name+'.png'));bpy.ops.render.render(write_still=True)
print('RENDERS_DONE',flush=True)
