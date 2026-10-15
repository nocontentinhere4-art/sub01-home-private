"""Manufacturer original stained dark brown finish; geometry and placement unchanged."""
import bpy,json,hashlib,zipfile
from pathlib import Path
ROOT=Path('/workspace/sub01-home-private/manufacturer-around-large-r1');BASE=ROOT/'placed-r2';OUT=ROOT/'placed-dark-r3';OUT.mkdir(parents=True,exist_ok=True)
assert hashlib.sha256((BASE/'muuto-around-large.blend').read_bytes()).hexdigest()=='883cb85432c7cee7a0248e6c415805f407e3e1c61716013ca1b10d1ec76b158c';bpy.ops.wm.open_mainfile(filepath=str(BASE/'muuto-around-large.blend'));parts=[o for o in bpy.context.scene.objects if o.type=='MESH'];assert len(parts)==1;original={o.name:([tuple(v.co)for v in o.data.vertices],[tuple(v.uv)for v in o.data.uv_layers.active.data],tuple(x for row in o.matrix_world for x in row))for o in parts}
with zipfile.ZipFile(ROOT/'Around-Coffee-Table-3D.zip')as z:data=z.read('Around-3D/Textures/Stained Dark Brown.jpg')
texture=OUT/'manufacturer-original-stained-dark-brown.jpg';texture.write_bytes(data);im=bpy.data.images.load(str(texture));im.colorspace_settings.name='sRGB';im.pack()
for o in parts:
 assert len(o.data.materials)==1;m=o.data.materials[0];m.name='MADark00';nodes=[n for n in m.node_tree.nodes if n.type=='TEX_IMAGE'];assert len(nodes)==1;nodes[0].image=im
 assert original[o.name]==([tuple(v.co)for v in o.data.vertices],[tuple(v.uv)for v in o.data.uv_layers.active.data],tuple(x for row in o.matrix_world for x in row))
for unused in list(bpy.data.images):
 if unused!=im:bpy.data.images.remove(unused)
bpy.ops.object.select_all(action='DESELECT')
for o in parts:o.select_set(True)
bpy.context.view_layer.objects.active=parts[0];bpy.ops.export_scene.gltf(filepath=str(OUT/'muuto-around-large-dark.glb'),export_format='GLB',use_selection=True,export_cameras=False,export_lights=False);bpy.ops.file.pack_all();bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'muuto-around-large-dark.blend'));r=json.loads((BASE/'source-report.json').read_text());r.update(schema='sub01.manufacturer-around-large-original-dark-finish.v1',originalFinish='Exact Stained Dark Brown.jpg from original official manufacturer ZIP',originalFinishImageSha256=hashlib.sha256(data).hexdigest(),finish='Manufacturer original Stained Dark Brown.jpg, original UV; no synthetic tint/geometry modifications',originalGeometryUVAndPlacementExactlyUnchanged=True,files={n:hashlib.sha256((OUT/n).read_bytes()).hexdigest()for n in['muuto-around-large-dark.glb','muuto-around-large-dark.blend']},nativeImportPermitted=False,visualAccepted=False);(OUT/'source-report.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r),flush=True)
